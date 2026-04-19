"""Simple SQLite-backed retry queue for failed Slack deliveries.

Lives in the same DB file as IncidentStore (different table). Idempotent enqueue,
per-row attempt counter, exponential backoff via `not_before` timestamp.
"""
import os
import sqlite3
import time


_SCHEMA = """
CREATE TABLE IF NOT EXISTS delivery_queue (
    incident_id TEXT PRIMARY KEY,
    reason TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    not_before REAL NOT NULL,
    enqueued_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_delivery_queue_not_before ON delivery_queue(not_before);
"""


class DeliveryQueue:
    def __init__(self, db_path: str):
        self.db_path = db_path
        parent = os.path.dirname(os.path.abspath(db_path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._connect().executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        return conn

    def enqueue(self, incident_id: str, reason: str) -> None:
        now = time.time()
        self._connect().execute(
            """
            INSERT INTO delivery_queue (incident_id, reason, attempts, not_before, enqueued_at, updated_at)
            VALUES (?, ?, 0, ?, ?, ?)
            ON CONFLICT(incident_id) DO NOTHING
            """,
            (incident_id, reason, now, now, now),
        )

    def pending(self, limit: int = 50, max_attempts: int = 5, now: float | None = None) -> list[dict]:
        ts = time.time() if now is None else now
        rows = self._connect().execute(
            """
            SELECT * FROM delivery_queue
            WHERE attempts < ? AND not_before <= ?
            ORDER BY not_before ASC
            LIMIT ?
            """,
            (max_attempts, ts, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def mark_success(self, incident_id: str) -> None:
        self._connect().execute("DELETE FROM delivery_queue WHERE incident_id = ?", (incident_id,))

    def mark_failed(self, incident_id: str, last_error: str, backoff_seconds: float = 30.0) -> None:
        now = time.time()
        self._connect().execute(
            """
            UPDATE delivery_queue
            SET attempts = attempts + 1,
                last_error = ?,
                not_before = ?,
                updated_at = ?
            WHERE incident_id = ?
            """,
            (last_error, now + backoff_seconds, now, incident_id),
        )
