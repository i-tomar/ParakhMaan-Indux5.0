"""Durable local queue for an edge node: results survive restarts and network outages."""
import json
import os
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    local_id TEXT UNIQUE NOT NULL,
    captured_at TEXT NOT NULL,
    image BLOB NOT NULL,
    metadata TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING',     -- PENDING, SYNCED, FAILED
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at REAL NOT NULL DEFAULT 0,
    last_error TEXT,
    central_inspection_id TEXT,
    synced_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_outbox_status ON outbox (status, next_attempt_at);
"""


class Outbox:
    def __init__(self, path: str):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._lock = threading.Lock()

    def add(self, image: bytes, metadata: Dict[str, Any]) -> str:
        local_id = uuid.uuid4().hex
        captured_at = datetime.now(timezone.utc).isoformat()
        payload = {**metadata, "local_id": local_id, "captured_at": captured_at}
        with self._lock:
            self._conn.execute(
                "INSERT INTO outbox (local_id, captured_at, image, metadata) VALUES (?, ?, ?, ?)",
                (local_id, captured_at, image, json.dumps(payload)),
            )
        return local_id

    def due(self, limit: int) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, local_id, image, metadata, attempts FROM outbox "
                "WHERE status = 'PENDING' AND next_attempt_at <= ? ORDER BY id LIMIT ?",
                (time.time(), limit),
            ).fetchall()
        return [{"id": r[0], "local_id": r[1], "image": r[2], "metadata": r[3], "attempts": r[4]} for r in rows]

    def mark_synced(self, row_id: int, inspection_id: Optional[str]) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE outbox SET status='SYNCED', central_inspection_id=?, synced_at=?, last_error=NULL WHERE id=?",
                (inspection_id, datetime.now(timezone.utc).isoformat(), row_id),
            )

    def mark_retry(self, row_id: int, attempts: int, error: str) -> None:
        backoff = min(300.0, 2.0 ** min(attempts, 8))
        with self._lock:
            self._conn.execute(
                "UPDATE outbox SET attempts=?, next_attempt_at=?, last_error=? WHERE id=?",
                (attempts, time.time() + backoff, error[:500], row_id),
            )

    def mark_failed(self, row_id: int, error: str) -> None:
        with self._lock:
            self._conn.execute("UPDATE outbox SET status='FAILED', last_error=? WHERE id=?", (error[:500], row_id))

    def prune(self, keep_synced: int) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM outbox WHERE status='SYNCED' AND id NOT IN "
                "(SELECT id FROM outbox WHERE status='SYNCED' ORDER BY id DESC LIMIT ?)",
                (keep_synced,),
            )

    def counts(self) -> Dict[str, int]:
        with self._lock:
            rows = self._conn.execute("SELECT status, COUNT(*) FROM outbox GROUP BY status").fetchall()
        counts = {"PENDING": 0, "SYNCED": 0, "FAILED": 0}
        counts.update({status: n for status, n in rows})
        return counts

    def recent(self, status: Optional[str], limit: int) -> List[Dict[str, Any]]:
        sql = ("SELECT local_id, captured_at, status, attempts, last_error, central_inspection_id, metadata "
               "FROM outbox {} ORDER BY id DESC LIMIT ?")
        with self._lock:
            if status:
                rows = self._conn.execute(sql.format("WHERE status = ?"), (status, limit)).fetchall()
            else:
                rows = self._conn.execute(sql.format(""), (limit,)).fetchall()
        items = []
        for r in rows:
            meta = json.loads(r[6])
            items.append({
                "local_id": r[0], "captured_at": r[1], "status": r[2], "attempts": r[3], "last_error": r[4],
                "central_inspection_id": r[5], "outcome": meta.get("outcome"),
                "detections": len(meta.get("detections", [])),
            })
        return items
