# Watcher startup

## Purpose

Ryujin needs one watcher per host project, shared by its active AI-agent sessions.

## Current behavior

### Current implementation
[`ensure_watcher.py`](../tools/ensure_watcher.py) is the shared startup helper. It checks the project's watcher lock and starts a detached watcher only when needed. A newly launched watcher reports readiness after its event listener and startup scan are active. Startup errors are returned to the caller, with diagnostics in `.state/watcher.log`.

[`watcher_lock.py`](../tools/watcher_lock.py) provides an operating-system file lock at `.state/watcher.lock`. The watcher holds it for its full lifetime, including when started manually. Concurrent startup attempts can therefore produce only one active watcher per project. The lock file stays in place; the operating system releases the lock if its process exits.

[`watch_llm_wiki.py`](../tools/watch_llm_wiki.py) creates `llm-wiki/` when needed and starts listening before scanning notes. Since 2026-10-28, shared [source reconciliation](../tools/source_sync.py) compares content/prompt hashes, queues new or changed topic notes, skips unchanged notes and marks deleted sources inactive. Index and log pages remain historical/navigation records and do not generate primary extraction jobs. The coalescing queue keeps one job row per path. Claim and Stop also reconcile synchronously, so extraction does not depend on watcher debounce. Restart a running watcher after upgrading its code; startup scanning recovers edits made while it was stopped.

Claude Code and Codex use `SessionStart`; Cursor uses `sessionStart` and `workspaceOpen`. All call the same helper. The first Stop now requests a [capture review](wiki-maintenance.md#stop-capture-review) independently of queue contents, followed by extraction.

All hook commands now use [`run_hook.sh`](../tools/run_hook.sh). Claude Code supplies its root through `CLAUDE_PROJECT_DIR`; Cursor supplies `CURSOR_PROJECT_DIR`; Codex resolves the Git root of its session working directory. The bootstrap resolves its own project location and finds `uv` on `PATH`, falling back to standard user and Homebrew installation locations. It forwards arguments and stdin to `uv run --project <project>/tools --locked <script>`. No hook command contains a developer-specific checkout or home-directory path. Codex's current bootstrap assumes a Git project, and the bootstrap requires a POSIX shell; native Windows command integration remains unimplemented.

### Watcher lifecycle
Startup hooks return promptly with `{}`. The detached watcher uses the helper's Python interpreter, the host project as its working directory, disconnected stdin, and redirected stdout and stderr. Temporary startup-handshake files are removed by the helper. There is no session-end shutdown hook: one chat closing must not stop the project's shared watcher.

If the watcher exits, the next startup invocation can launch it again using the same lock file. There is no automatic restart loop or operating-system service.

## Code locations

[ensure_watcher.py](../tools/ensure_watcher.py) starts or reuses the watcher; [watcher_lock.py](../tools/watcher_lock.py) owns the lifetime lock; [watch_llm_wiki.py](../tools/watch_llm_wiki.py) listens and reconciles through [source_sync.py](../tools/source_sync.py). Client configuration and bootstrap paths appear above. See [the architecture map](architecture.md).

## Constraints

One watcher is shared across chats. Client shutdown must not stop it. POSIX shell and uv are required for configured commands; Codex resolves a Git root. Operating-system locks protect concurrent startup, while source hashes prevent unchanged notes from creating new jobs. No automatic process supervisor is installed.

## Decisions and reasoning

### Optional operating-system supervision
A supervisor owns the watcher process and applies a restart policy when it exits. Ryujin would configure an existing service manager instead of implementing its own permanent monitoring process:

- macOS: a per-user [`launchd` LaunchAgent](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html), with a project-specific job label, command, working directory, log paths and `KeepAlive` policy. Its lifetime is tied to the logged-in user. A supervised watcher must stay in the foreground; it must not detach itself from `launchd`.
- Linux installations using systemd: a [service](https://freedesktop.org/software/systemd/man/latest/systemd.service.html) with a restart policy such as `Restart=on-failure`, a restart delay and start-rate limits.
- Windows: a registered service using [Service Control Manager failure actions](https://learn.microsoft.com/en-us/windows/win32/api/winsvc/ns-winsvc-service_failure_actionsw). A plain Python script needs service integration; naming it in a configuration is not sufficient by itself.

If supervision is adopted, client hooks should ask the service manager to start the project's job. They should not also launch a separate detached watcher. Installation would generate the machine-specific service definition; removal would unregister it. No supervisor is currently installed by Ryujin.

Process-exit recovery does not by itself detect a watcher that is alive but hung. It also does not recover missed filesystem events; startup reconciliation is still required. On 2026-10-27, the user chose to skip supervision and implement startup hooks with a shared helper instead. Supervision remains deferred.

## Verification

### Documented client behaviour
- [Claude Code](https://code.claude.com/docs/en/hooks#sessionstart) supports `SessionStart`, including new and resumed sessions. A launcher should finish promptly: the first model response waits for startup hooks. Background child processes need redirected stdout and stderr so they do not retain the hook's output streams.
- [Codex](https://learn.chatgpt.com/docs/hooks) supports `SessionStart`. Non-managed hook definitions require trust. Codex cancels unfinished asynchronous hooks when a session ends, so an asynchronous hook is not a persistent service supervisor.
- [Cursor](https://cursor.com/docs/hooks) supports `sessionStart` for new conversations and `workspaceOpen` for workspace lifecycle events. `sessionStart` is fire-and-forget and does not block the agent on readiness.

These are documented capabilities. The configured commands and watcher integration were tested on macOS. Automatic dispatch of the new startup hooks has not yet been observed in the three clients. After the portability changes on 2026-10-27, Codex's native hook listing parsed the configuration without errors and reported both startup and Stop hooks as enabled but modified. Their updated definitions require trust review before Codex will run them automatically.


The five integration tests in [`test_watcher_startup.py`](../tools/tests/test_watcher_startup.py) cover eight simultaneous helpers, duplicate manual launches, live Markdown edits, independent projects, restart after exit, offline-note scanning, missing wiki directories and startup failure reporting. The portability test runs every configured startup and Stop command in a relocated project with spaces in its path, from a nested working directory and with a minimal `PATH`. They use temporary projects and do not add manual-test events to the project's hook log. Windows locking and process-detachment branches have not been exercised on Windows.

## Ownership

Codex updated this page and its capture-workflow reference on 2026-10-28 at Horia's request. The source does not assign an ongoing watcher owner or identify the historical implementer of every startup component.

## Open questions

Automatic startup-hook dispatch remains unverified separately from configured-command tests. Native Windows command integration and Windows runtime checks are incomplete. Supervision remains deferred.

## Change history

- 2026-10-27: Shared startup, singleton locking, offline reconciliation and portable commands were implemented; supervision was deferred. See [the dated ledger](log.md).
- 2026-10-28: Hash reconciliation excludes index/log from primary extraction. Standardized this topic and linked the new queue-independent capture review; this documentation change does not itself verify additional clients.
