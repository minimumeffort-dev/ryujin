from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import re
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest


TOOLS_DIR = Path(__file__).resolve().parents[1]


class WatcherStartupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="ryujin-watcher-test-")
        self.projects = []
        self.stopped_pids = set()
        self.project = self.make_project("project with spaces")

    def make_project(self, name):
        project = Path(self.temporary.name) / name
        tools = project / "tools"
        tools.mkdir(parents=True)
        for filename in (
            "paths.py",
            "watcher_lock.py",
            "ensure_watcher.py",
            "watch_llm_wiki.py",
            "queue_store.py",
            "schema.sql",
            "queue_hook.py",
            "run_hook.sh",
            "pyproject.toml",
            "uv.lock",
        ):
            shutil.copy2(TOOLS_DIR / filename, tools / filename)
        extraction = tools / "extraction"
        extraction.mkdir()
        shutil.copy2(TOOLS_DIR / "extraction" / "validate.py", extraction / "validate.py")
        self.projects.append(project)
        return project

    def launch(self, project=None):
        project = project or self.project
        return subprocess.run(
            [sys.executable, str(project / "tools" / "ensure_watcher.py")],
            input='{"hook_event_name":"SessionStart","source":"startup"}',
            capture_output=True,
            text=True,
            cwd=self.temporary.name,
            env={**os.environ, "PATH": os.defpath},
            timeout=10,
        )

    def pids(self, project):
        log = project / ".state" / "watcher.log"
        if not log.exists():
            return []
        return [int(pid) for pid in re.findall(r"Watching .* \(PID (\d+)\)", log.read_text())]

    def stop(self, project):
        for pid in self.pids(project):
            if pid in self.stopped_pids:
                continue
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            self.stopped_pids.add(pid)

    def tearDown(self):
        for project in self.projects:
            self.stop(project)
        time.sleep(0.1)
        self.temporary.cleanup()

    def jobs(self, project=None):
        project = project or self.project
        path = project / ".state" / "ryujin.sqlite3"
        with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as database:
            return dict(database.execute("SELECT path, revision FROM jobs"))

    def assert_started(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {})

    def test_concurrent_startup_and_manual_launch_share_one_watcher(self):
        notes = self.project / "llm-wiki"
        notes.mkdir()
        (notes / "existing.md").write_text("Existing knowledge")
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(lambda _: self.launch(), range(8)))
        for result in results:
            self.assert_started(result)
        self.assertEqual(len(self.pids(self.project)), 1)
        self.assertIn("existing.md", self.jobs())

        manual = subprocess.run(
            [sys.executable, str(self.project / "tools" / "watch_llm_wiki.py")],
            capture_output=True,
            text=True,
            timeout=3,
        )
        self.assertEqual(manual.returncode, 0, manual.stderr)
        self.assert_started(self.launch())
        self.assertEqual(len(self.pids(self.project)), 1)
        self.assertEqual(list((self.project / ".state").glob("watcher-start-*.json")), [])

        original_revision = self.jobs()["existing.md"]
        (notes / "existing.md").write_text("Updated knowledge")
        (notes / "new.MD").write_text("New knowledge")
        (notes / "ignored.txt").write_text("Not a Markdown note")
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            jobs = self.jobs()
            if jobs.get("existing.md", 0) > original_revision and "new.MD" in jobs:
                break
            time.sleep(0.05)
        self.assertGreater(jobs["existing.md"], original_revision)
        self.assertIn("new.MD", jobs)
        self.assertNotIn("ignored.txt", jobs)

    def test_projects_have_independent_watchers(self):
        other = self.make_project("another project")
        self.assert_started(self.launch())
        self.assert_started(self.launch(other))
        self.assertNotEqual(self.pids(self.project), self.pids(other))
        self.assertTrue((self.project / "llm-wiki").is_dir())
        self.assertTrue((other / "llm-wiki").is_dir())

    def test_next_startup_recovers_after_exit_and_scans_offline_notes(self):
        self.assert_started(self.launch())
        old_pid = self.pids(self.project)[0]
        self.stop(self.project)
        time.sleep(0.2)
        (self.project / "llm-wiki" / "offline.md").write_text("Written while stopped")
        self.assert_started(self.launch())
        self.assertNotEqual(self.pids(self.project)[-1], old_pid)
        self.assertIn("offline.md", self.jobs())

    def test_startup_failure_is_reported_and_temporary_files_are_removed(self):
        (self.project / "tools" / "schema.sql").write_text("INVALID SQL;")
        result = self.launch()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Watcher failed to start", result.stderr)
        self.assertIn("OperationalError", (self.project / ".state" / "watcher.log").read_text())
        self.assertEqual(list((self.project / ".state").glob("watcher-start-*.json")), [])

    @unittest.skipIf(os.name == "nt", "Hook bootstrap currently requires a POSIX shell")
    def test_hook_commands_work_in_a_relocated_project_from_subdirectories(self):
        uv = shutil.which("uv") or str(Path.home() / ".local" / "bin" / "uv")
        setup = subprocess.run(
            [uv, "sync", "--project", str(self.project / "tools"), "--locked", "--offline", "--python", sys.executable],
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(setup.returncode, 0, setup.stderr)
        subprocess.run(["git", "init", "--quiet", str(self.project)], check=True)
        nested = self.project / "src" / "nested"
        nested.mkdir(parents=True)
        notes = self.project / "llm-wiki"
        notes.mkdir()
        (notes / "portable.md").write_text("Portable project knowledge")
        environment = {
            **os.environ,
            "PATH": os.defpath,
            "UV_OFFLINE": "1",
            "CLAUDE_PROJECT_DIR": str(self.project),
            "CURSOR_PROJECT_DIR": str(self.project),
        }

        for client, filename in (
            ("claude", ".claude/settings.json"),
            ("codex", ".codex/hooks.json"),
            ("cursor", ".cursor/hooks.json"),
        ):
            config = json.loads((TOOLS_DIR.parent / filename).read_text())
            self.assertNotIn(str(TOOLS_DIR.parent), json.dumps(config))
            for event, groups in config["hooks"].items():
                for group in groups:
                    for handler in group.get("hooks", [group]):
                        result = subprocess.run(
                            ["sh", "-c", handler["command"]],
                            input=json.dumps({"hook_event_name": event, "status": "completed"}),
                            cwd=nested,
                            env=environment,
                            capture_output=True,
                            text=True,
                            timeout=10,
                        )
                        self.assertEqual(result.returncode, 0, result.stderr)
                        output = json.loads(result.stdout)
                        if event.lower() == "stop":
                            if client == "cursor":
                                self.assertIn("followup_message", output)
                            else:
                                self.assertEqual(output["decision"], "block")
                        else:
                            self.assertEqual(output, {})
        self.assertEqual(len(self.pids(self.project)), 1)


if __name__ == "__main__":
    unittest.main()
