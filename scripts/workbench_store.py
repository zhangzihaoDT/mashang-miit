"""Transactional task ledger and immutable candidate snapshots for one local worker."""
import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from workbench_source import WorkbenchError, validate_url


def now():
    return datetime.now(timezone.utc).isoformat()


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY, idempotency_key TEXT UNIQUE NOT NULL,
                    url TEXT NOT NULL, retry_of TEXT REFERENCES tasks(task_id),
                    status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    error TEXT, candidate_id TEXT);
                CREATE TABLE IF NOT EXISTS candidates (
                    candidate_id TEXT PRIMARY KEY, task_id TEXT UNIQUE NOT NULL REFERENCES tasks(task_id),
                    revision INTEGER NOT NULL, review_status TEXT NOT NULL,
                    content_hash TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS evidence (
                    evidence_id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(task_id),
                    metadata TEXT NOT NULL);
            ''')

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        return db

    def create(self, url, key, retry_of=None):
        validate_url(url)
        if not isinstance(key, str) or not 1 <= len(key) <= 200:
            raise WorkbenchError('invalid_idempotency_key', '需要 1–200 字符幂等键')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            prior = db.execute('SELECT * FROM tasks WHERE idempotency_key=?', (key,)).fetchone()
            if prior:
                if prior['url'] != url or prior['retry_of'] != retry_of:
                    raise WorkbenchError('idempotency_conflict', '该幂等键已用于不同请求', 409)
                return dict(prior)
            if retry_of:
                old = db.execute('SELECT * FROM tasks WHERE task_id=?', (retry_of,)).fetchone()
                if not old:
                    raise WorkbenchError('not_found', '任务不存在', 404)
                if old['status'] not in ('failed', 'partial_success'):
                    raise WorkbenchError('not_retryable', '仅失败或部分成功任务可以重试', 409)
            task_id, stamp = uuid.uuid4().hex, now()
            db.execute('INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?,?)',
                       (task_id, key, url, retry_of, 'queued', stamp, stamp, None, None))
            return dict(db.execute('SELECT * FROM tasks WHERE task_id=?', (task_id,)).fetchone())

    def recover(self):
        with self.connect() as db:
            db.execute("UPDATE tasks SET status='failed',updated_at=?,error=? WHERE status='running'",
                       (now(), encode({'code': 'worker_interrupted', 'message': '采集进程中断，可重试', 'retryable': True})))

    def claim(self):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT * FROM tasks WHERE status='queued' ORDER BY created_at LIMIT 1").fetchone()
            if row:
                db.execute("UPDATE tasks SET status='running',updated_at=? WHERE task_id=?", (now(), row['task_id']))
                return dict(row)

    def complete(self, task_id, payload, evidence):
        body, candidate_id, stamp = encode(payload), uuid.uuid4().hex, now()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT status FROM tasks WHERE task_id=?', (task_id,)).fetchone()
            if not row or row['status'] != 'running':
                raise WorkbenchError('task_state_conflict', '任务已完成或中断', 409)
            db.execute('INSERT INTO candidates VALUES (?,?,?,?,?,?,?)',
                       (candidate_id, task_id, 1, 'pending_review', hashlib.sha256(body.encode()).hexdigest(), body, stamp))
            for item in evidence:
                db.execute('INSERT INTO evidence VALUES (?,?,?)', (uuid.uuid4().hex, task_id, encode(item)))
            db.execute("UPDATE tasks SET status='succeeded',candidate_id=?,updated_at=? WHERE task_id=?", (candidate_id, stamp, task_id))
        return candidate_id

    def fail(self, task_id, error):
        with self.connect() as db:
            db.execute("UPDATE tasks SET status='failed',updated_at=?,error=? WHERE task_id=? AND status='running'",
                       (now(), encode(error), task_id))

    def tasks(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT * FROM tasks ORDER BY created_at DESC LIMIT 100')]

    def task(self, task_id):
        with self.connect() as db:
            row = db.execute('SELECT * FROM tasks WHERE task_id=?', (task_id,)).fetchone()
            if not row:
                raise WorkbenchError('not_found', '任务不存在', 404)
            return dict(row)

    def inbox(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT candidate_id,task_id,revision,review_status,content_hash,created_at FROM candidates ORDER BY created_at DESC LIMIT 100')]

    def candidate(self, candidate_id):
        with self.connect() as db:
            row = db.execute('SELECT * FROM candidates WHERE candidate_id=?', (candidate_id,)).fetchone()
            if not row:
                raise WorkbenchError('not_found', '候选不存在', 404)
            result = dict(row)
            result['payload'] = json.loads(result['payload'])
            result['evidence'] = [dict(r) | {'metadata': json.loads(r['metadata'])} for r in
                                  db.execute('SELECT * FROM evidence WHERE task_id=?', (row['task_id'],))]
            return result

    def evidence(self, evidence_id):
        with self.connect() as db:
            row = db.execute('SELECT * FROM evidence WHERE evidence_id=?', (evidence_id,)).fetchone()
            if not row:
                raise WorkbenchError('not_found', '证据不存在', 404)
            return dict(row) | {'metadata': json.loads(row['metadata'])}
