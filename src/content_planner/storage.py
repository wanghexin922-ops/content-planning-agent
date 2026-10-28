"""SQLite persistence; one request per mode; atomic plan insert and task lock."""
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path

from .common import PlannerError, dumps, fingerprint
import json


class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), timeout=10)
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS tasks (
            task_key TEXT PRIMARY KEY, request_hash TEXT NOT NULL,
            state TEXT NOT NULL, lock_owner TEXT, lease_until REAL
        );
        CREATE TABLE IF NOT EXISTS plans (
            task_key TEXT PRIMARY KEY REFERENCES tasks(task_key),
            plan_id TEXT UNIQUE NOT NULL, plan TEXT NOT NULL
        );
        ''')
        self.db.commit()

    def close(self):
        self.db.close()

    @contextmanager
    def acquire(self, key, request, initial):
        owner = uuid.uuid4().hex
        digest = fingerprint(request)
        try:
            self.db.execute("BEGIN IMMEDIATE")
            row = self.db.execute("SELECT request_hash,state,lock_owner,lease_until FROM tasks WHERE task_key=?", (key,)).fetchone()
            import time
            now = time.time()
            if row and row[0] != digest:
                raise PlannerError("request_conflict", "同一 request_id 的输入已改变；请使用新的 request_id")
            if row and row[2] and row[3] > now:
                raise PlannerError("request_busy", "相同任务正在执行，请稍后重试")
            state = json.loads(row[1]) if row else initial
            if not row:
                self.db.execute("INSERT INTO tasks VALUES (?,?,?,NULL,NULL)", (key, digest, dumps(state)))
            self.db.execute("UPDATE tasks SET lock_owner=?,lease_until=? WHERE task_key=?", (owner, now + 300, key))
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        try:
            yield state, owner
        finally:
            with self.db:
                self.db.execute("UPDATE tasks SET lock_owner=NULL,lease_until=NULL WHERE task_key=? AND lock_owner=?", (key, owner))

    def checkpoint(self, key, owner, state):
        import time
        with self.db:
            changed = self.db.execute("UPDATE tasks SET state=?,lease_until=? WHERE task_key=? AND lock_owner=?", (dumps(state), time.time()+300, key, owner)).rowcount
            if changed != 1:
                raise PlannerError("lock_lost", "任务执行锁已失效，停止本次执行")

    def get_plan(self, key):
        row = self.db.execute("SELECT plan_id,plan FROM plans WHERE task_key=?", (key,)).fetchone()
        return {"plan_id": row[0], "plan": json.loads(row[1])} if row else None

    def save_plan(self, key, owner, plan):
        plan_id = "plan-" + fingerprint(key)[:16]
        with self.db:
            row = self.db.execute("SELECT lock_owner FROM tasks WHERE task_key=?", (key,)).fetchone()
            if not row or row[0] != owner:
                raise PlannerError("lock_lost", "保存时任务锁已失效")
            self.db.execute("INSERT OR IGNORE INTO plans VALUES (?,?,?)", (key, plan_id, dumps(plan)))
        saved = self.get_plan(key)
        if saved["plan"] != plan:
            raise PlannerError("plan_conflict", "同一请求已保存不同方案，未覆盖")
        return saved
