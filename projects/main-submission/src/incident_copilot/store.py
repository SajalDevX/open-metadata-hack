"""SQLite persistence for incident briefs — upsert by incident_id, list recent, fetch by id."""
import json
import os
import sqlite3
import time


_SCHEMA = """
CREATE TABLE IF NOT EXISTS incidents (
    incident_id TEXT PRIMARY KEY,
    policy_state TEXT NOT NULL,
    delivery_status TEXT NOT NULL,
    primary_output TEXT NOT NULL,
    payload_hash TEXT,
    brief_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    slack_thread_ts TEXT
);
CREATE INDEX IF NOT EXISTS idx_incidents_updated_at ON incidents(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_incidents_thread_ts ON incidents(slack_thread_ts);
"""


class IncidentStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        parent = os.path.dirname(os.path.abspath(db_path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        conn = self._connect()
        conn.executescript(_SCHEMA)
        try:
            conn.execute("ALTER TABLE incidents ADD COLUMN slack_thread_ts TEXT")
        except sqlite3.OperationalError:
            pass  # column already exists on pre-migration databases
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_incidents_thread_ts ON incidents(slack_thread_ts)"
        )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        return conn

    def save_brief(
        self,
        brief: dict,
        delivery_status: str,
        primary_output: str,
        payload_hash: str | None = None,
    ) -> None:
        incident_id = brief["incident_id"]
        policy_state = brief.get("policy_state", "allowed")
        now = time.time()
        brief_json = json.dumps(brief, sort_keys=True, separators=(",", ":"), default=str)

        conn = self._connect()
        existing = conn.execute(
            "SELECT created_at FROM incidents WHERE incident_id = ?", (incident_id,)
        ).fetchone()
        created_at = existing["created_at"] if existing else now

        conn.execute(
            """
            INSERT INTO incidents
                (incident_id, policy_state, delivery_status, primary_output,
                 payload_hash, brief_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(incident_id) DO UPDATE SET
                policy_state = excluded.policy_state,
                delivery_status = excluded.delivery_status,
                primary_output = excluded.primary_output,
                payload_hash = excluded.payload_hash,
                brief_json = excluded.brief_json,
                updated_at = excluded.updated_at
            """,
            (
                incident_id, policy_state, delivery_status, primary_output,
                payload_hash, brief_json, created_at, now,
            ),
        )

    def fetch_by_id(self, incident_id: str) -> dict | None:
        row = self._connect().execute(
            "SELECT * FROM incidents WHERE incident_id = ?", (incident_id,)
        ).fetchone()
        return self._row_to_dict(row) if row else None

    def list_recent(self, limit: int = 50) -> list[dict]:
        rows = self._connect().execute(
            "SELECT * FROM incidents ORDER BY updated_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def count(self) -> int:
        return int(self._connect().execute("SELECT COUNT(*) FROM incidents").fetchone()[0])

    def rca_summary(self, limit: int = 500) -> dict:
        """Return incidents bucketed by signal_type for the aggregated RCA dashboard."""
        rows = self._connect().execute(
            "SELECT brief_json, policy_state, created_at FROM incidents ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()

        buckets: dict[str, dict] = {}
        for row in rows:
            brief = json.loads(row["brief_json"])
            refs = (brief.get("what_failed") or {}).get("evidence_refs") or []
            signal = next((r[4:] for r in refs if r.startswith("rca:")), "unknown")
            bucket = buckets.setdefault(signal, {"signal_type": signal, "count": 0, "approval_required": 0, "recent_incidents": []})
            bucket["count"] += 1
            if row["policy_state"] == "approval_required":
                bucket["approval_required"] += 1
            if len(bucket["recent_incidents"]) < 5:
                bucket["recent_incidents"].append({
                    "incident_id": brief.get("incident_id"),
                    "policy_state": row["policy_state"],
                    "created_at": row["created_at"],
                })

        return {
            "total_incidents": sum(b["count"] for b in buckets.values()),
            "signal_types": sorted(buckets.values(), key=lambda b: b["count"], reverse=True),
        }

    def save_thread_ts(self, incident_id: str, thread_ts: str) -> None:
        cur = self._connect().execute(
            "UPDATE incidents SET slack_thread_ts = ? WHERE incident_id = ?",
            (thread_ts, incident_id),
        )
        if cur.rowcount == 0:
            raise KeyError(f"save_thread_ts: no incident with id {incident_id!r}")

    def fetch_by_thread_ts(self, thread_ts: str) -> dict | None:
        row = self._connect().execute(
            "SELECT * FROM incidents WHERE slack_thread_ts = ?", (thread_ts,)
        ).fetchone()
        return self._row_to_dict(row) if row else None

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict:
        d = dict(row)
        d["brief"] = json.loads(d.pop("brief_json"))
        return d
