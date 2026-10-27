"""Numbered, transactional migrations; preserve a consistent pre-upgrade backup."""

from hashlib import sha256
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import time
from uuid import NAMESPACE_URL, uuid5

SCHEMA_VERSION = 2


def digest(text):
    return sha256(text.encode('utf-8')).hexdigest()


def source_kind(source_doc):
    name = Path(source_doc).name.casefold()
    return 'navigation' if name == 'index.md' else 'ledger' if name == 'log.md' else 'topic'


def statements(text):
    pending = ''
    for line in text.splitlines(keepends=True):
        pending += line
        if sqlite3.complete_statement(pending):
            yield pending
            pending = ''
    if pending.strip():
        raise ValueError('Incomplete schema SQL')


def archive_result(database, project_root, source_doc, revision, result_path,
                   accepted_at, *, snapshot=None, source_hash=None, prompt_hash=None):
    path = (project_root / result_path).resolve()
    if not path.is_relative_to(project_root.resolve()):
        raise ValueError('Extraction result must be inside the project')
    text = path.read_text(encoding='utf-8')
    data = json.loads(text)
    run_id = uuid5(NAMESPACE_URL, f'ryujin:extraction:{result_path}').hex
    database.execute(
        '''INSERT INTO knowledge_sources(source_doc,kind,content_hash,active,updated_at)
           VALUES(?,?,?,1,?) ON CONFLICT(source_doc) DO NOTHING''',
        (source_doc, source_kind(source_doc), source_hash, accepted_at),
    )
    database.execute(
        '''INSERT INTO extraction_runs
           (id,source_doc,revision,result_path,result_hash,result_json,source_hash,
            source_snapshot,schema_version,prompt_hash,accepted_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING''',
        (run_id,source_doc,revision,result_path,digest(text),text,source_hash,
         snapshot,data.get('schema_version',1),prompt_hash,accepted_at),
    )
    return run_id


def migrate(database, database_path, schema_path, project_root):
    tables = {row[0] for row in database.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'schema_migrations' in tables:
        version = database.execute('SELECT MAX(version) FROM schema_migrations').fetchone()[0] or 0
        if version > SCHEMA_VERSION:
            raise ValueError(f'Database schema {version} is newer than this tool supports')
        if version == SCHEMA_VERSION:
            return
    # Acquire the writer lock before inspecting the schema again. Concurrent openers
    # either migrate once or observe the committed new version.
    database.execute('BEGIN IMMEDIATE')
    try:
        tables = {row[0] for row in database.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'schema_migrations' in tables and database.execute(
            'SELECT MAX(version) FROM schema_migrations'
        ).fetchone()[0] == SCHEMA_VERSION:
            database.execute('COMMIT')
            return
        legacy = 'graph_nodes' in tables
        saved = {}
        if legacy:
            # A separate read connection backs up the pre-migration WAL snapshot.
            backup_dir = Path(database_path).parent / 'backups'
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup_path = backup_dir / f'pre-v2-{time.time_ns()}.sqlite3'
            with closing(sqlite3.connect(str(database_path))) as source, closing(sqlite3.connect(backup_path)) as target:
                source.backup(target)
            for table in ('graph_nodes','graph_node_sources','graph_edges','graph_aliases'):
                saved[table] = list(database.execute(f'SELECT * FROM {table}'))
            for table in ('graph_edges','graph_aliases','graph_node_sources','graph_nodes'):
                database.execute(f'DROP TABLE {table}')
            columns = {row[1] for row in database.execute('PRAGMA table_info(extraction_results)')}
            for name, definition in (
                ('source_hash','TEXT'), ('schema_version','INTEGER NOT NULL DEFAULT 1'),
                ('extraction_id','TEXT'),
            ):
                if name not in columns:
                    database.execute(f'ALTER TABLE extraction_results ADD COLUMN {name} {definition}')
        for statement in statements(schema_path.read_text(encoding='utf-8')):
            database.execute(statement)
        for table, rows in saved.items():
            if rows:
                placeholders = ','.join('?' for _ in rows[0])
                database.executemany(f'INSERT INTO {table} VALUES({placeholders})', rows)
        for row in database.execute('SELECT * FROM extraction_results').fetchall():
            run_id = archive_result(database, project_root, row['source_doc'], row['revision'],
                                    row['result_path'], row['accepted_at'])
            database.execute('UPDATE extraction_results SET extraction_id=? WHERE source_doc=?',
                             (run_id,row['source_doc']))
        if legacy:
            from engineering_graph import insert_legacy_facts, index_graph
            sources = database.execute('SELECT DISTINCT source_doc FROM graph_node_sources').fetchall()
            for (source_doc,) in sources:
                database.execute(
                    'INSERT OR IGNORE INTO knowledge_sources VALUES(?,?,NULL,1,?)',
                    (source_doc,source_kind(source_doc),time.time()))
                nodes = [dict(row) for row in database.execute(
                    '''SELECT n.id,n.name,n.type,s.description FROM graph_nodes n
                       JOIN graph_node_sources s ON s.node_id=n.id WHERE s.source_doc=?''',
                    (source_doc,))]
                run = database.execute('SELECT extraction_id FROM extraction_results WHERE source_doc=?',
                                       (source_doc,)).fetchone()
                insert_legacy_facts(database, {'source_doc':source_doc,'nodes':nodes},
                                    {node['name']:node['id'] for node in nodes},run[0] if run else None)
            index_graph(database)
        database.execute('INSERT INTO schema_migrations VALUES(?,?)', (SCHEMA_VERSION,time.time()))
        database.execute('COMMIT')
    except BaseException:
        database.execute('ROLLBACK')
        raise
