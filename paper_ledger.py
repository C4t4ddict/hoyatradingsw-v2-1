"""Append-only SQLite ledger for paper-trading decisions and executions."""

from __future__ import annotations

import csv
from contextlib import closing, contextmanager
import hashlib
import json
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TradingLedger:
    """Persist immutable trading events with idempotent event identifiers."""

    def __init__(self, path: str = "data/trading_ledger.sqlite3"):
        self.path = path
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS trading_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    session_id TEXT NOT NULL,
                    environment TEXT NOT NULL CHECK(environment IN ('paper', 'live')),
                    event_type TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    strategy_version TEXT,
                    payload_json TEXT NOT NULL,
                    previous_hash TEXT,
                    event_hash TEXT
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_trading_events_session ON trading_events(session_id, sequence)"
            )
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(trading_events)").fetchall()}
            if "previous_hash" not in columns:
                connection.execute("ALTER TABLE trading_events ADD COLUMN previous_hash TEXT")
            if "event_hash" not in columns:
                connection.execute("ALTER TABLE trading_events ADD COLUMN event_hash TEXT")
            counts = connection.execute(
                "SELECT COUNT(*) AS total, COUNT(event_hash) AS hashed FROM trading_events"
            ).fetchone()
            if counts["total"] and counts["hashed"] == 0:
                self._backfill_legacy_hashes(connection)

    def _backfill_legacy_hashes(self, connection: sqlite3.Connection) -> None:
        previous_by_chain = {}
        rows = connection.execute(
            "SELECT * FROM trading_events ORDER BY session_id, environment, sequence"
        ).fetchall()
        for row in rows:
            key = (row["session_id"], row["environment"])
            previous_hash = previous_by_chain.get(key)
            event_hash = self._hash_event(
                event_id=row["event_id"], session_id=row["session_id"],
                environment=row["environment"], event_type=row["event_type"],
                occurred_at=row["occurred_at"], strategy_version=row["strategy_version"],
                payload_json=row["payload_json"], previous_hash=previous_hash,
            )
            connection.execute(
                "UPDATE trading_events SET previous_hash = ?, event_hash = ? WHERE sequence = ?",
                (previous_hash, event_hash, row["sequence"]),
            )
            previous_by_chain[key] = event_hash

    @staticmethod
    def _hash_event(
        *, event_id: str, session_id: str, environment: str, event_type: str,
        occurred_at: str, strategy_version: Optional[str], payload_json: str,
        previous_hash: Optional[str],
    ) -> str:
        canonical = json.dumps({
            "event_id": event_id,
            "session_id": session_id,
            "environment": environment,
            "event_type": event_type,
            "occurred_at": occurred_at,
            "strategy_version": strategy_version,
            "payload_json": payload_json,
            "previous_hash": previous_hash,
        }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def append_event(
        self,
        *,
        event_id: str,
        session_id: str,
        event_type: str,
        payload: Dict[str, Any],
        environment: str = "paper",
        occurred_at: Optional[str] = None,
        strategy_version: Optional[str] = None,
    ) -> bool:
        """Append once; return False when the idempotency key already exists."""
        if environment not in {"paper", "live"}:
            raise ValueError("environment must be paper or live")
        timestamp = occurred_at or _utc_now()
        payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        try:
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                previous = connection.execute(
                    "SELECT event_hash FROM trading_events WHERE session_id = ? AND environment = ? ORDER BY sequence DESC LIMIT 1",
                    (session_id, environment),
                ).fetchone()
                previous_hash = previous["event_hash"] if previous else None
                event_hash = self._hash_event(
                    event_id=event_id, session_id=session_id, environment=environment,
                    event_type=event_type, occurred_at=timestamp,
                    strategy_version=strategy_version, payload_json=payload_json,
                    previous_hash=previous_hash,
                )
                connection.execute(
                    """
                    INSERT INTO trading_events(
                        event_id, session_id, environment, event_type,
                        occurred_at, strategy_version, payload_json, previous_hash, event_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event_id,
                        session_id,
                        environment,
                        event_type,
                        timestamp,
                        strategy_version,
                        payload_json,
                        previous_hash,
                        event_hash,
                    ),
                )
            return True
        except sqlite3.IntegrityError:
            return False

    def has_event(self, event_id: str) -> bool:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT 1 FROM trading_events WHERE event_id = ?", (event_id,)
            ).fetchone()
        return row is not None

    def list_events(
        self,
        *,
        session_id: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: int = 500,
    ) -> list[Dict[str, Any]]:
        clauses, params = [], []
        if session_id:
            clauses.append("session_id = ?")
            params.append(session_id)
        if event_type:
            clauses.append("event_type = ?")
            params.append(event_type)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(max(1, min(int(limit), 5000)))
        with self._connection() as connection:
            rows = connection.execute(
                f"SELECT * FROM trading_events {where} ORDER BY sequence DESC LIMIT ?",
                params,
            ).fetchall()
        return [
            {
                **dict(row),
                "payload": json.loads(row["payload_json"]),
            }
            for row in rows
        ]

    def verify_integrity(self, *, session_id: Optional[str] = None) -> Dict[str, Any]:
        clauses, params = [], []
        if session_id:
            clauses.append("session_id = ?")
            params.append(session_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connection() as connection:
            database_check = connection.execute("PRAGMA integrity_check").fetchone()[0]
            rows = connection.execute(
                f"SELECT * FROM trading_events {where} ORDER BY session_id, environment, sequence",
                params,
            ).fetchall()
        failures, previous_by_chain = [], {}
        for row in rows:
            key = (row["session_id"], row["environment"])
            expected_previous = previous_by_chain.get(key)
            stored_hash = row["event_hash"]
            # Pre-migration rows have no chain hash and remain readable, but are reported.
            if not stored_hash:
                failures.append({"sequence": row["sequence"], "reason": "missing_event_hash"})
                previous_by_chain[key] = None
                continue
            if row["previous_hash"] != expected_previous:
                failures.append({"sequence": row["sequence"], "reason": "previous_hash_mismatch"})
            calculated = self._hash_event(
                event_id=row["event_id"], session_id=row["session_id"],
                environment=row["environment"], event_type=row["event_type"],
                occurred_at=row["occurred_at"], strategy_version=row["strategy_version"],
                payload_json=row["payload_json"], previous_hash=row["previous_hash"],
            )
            if calculated != stored_hash:
                failures.append({"sequence": row["sequence"], "reason": "event_hash_mismatch"})
            previous_by_chain[key] = stored_hash
        return {
            "ok": database_check == "ok" and not failures,
            "database_check": database_check,
            "events_checked": len(rows),
            "failures": failures,
        }

    def backup(self, destination: str) -> str:
        parent = os.path.dirname(destination)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with closing(self._connect()) as source, closing(sqlite3.connect(destination)) as target:
            source.backup(target)
        check = TradingLedger(destination).verify_integrity()
        if not check["ok"]:
            raise ValueError(f"backup integrity check failed: {check['failures']}")
        return destination

    def restore_backup(self, source: str) -> Dict[str, str]:
        if not os.path.isfile(source):
            raise FileNotFoundError(source)
        source_check = TradingLedger(source).verify_integrity()
        if not source_check["ok"]:
            raise ValueError(f"source integrity check failed: {source_check['failures']}")
        parent = os.path.dirname(self.path) or "."
        os.makedirs(parent, exist_ok=True)
        descriptor, staged = tempfile.mkstemp(prefix="ledger-restore-", suffix=".sqlite3", dir=parent)
        os.close(descriptor)
        rollback = f"{self.path}.pre_restore.{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.bak"
        try:
            with closing(sqlite3.connect(source)) as source_connection, closing(sqlite3.connect(staged)) as target:
                source_connection.backup(target)
            if os.path.exists(self.path):
                with closing(self._connect()) as current, closing(sqlite3.connect(rollback)) as rollback_connection:
                    current.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                    current.backup(rollback_connection)
            os.replace(staged, self.path)
            for suffix in ("-wal", "-shm"):
                sidecar = f"{self.path}{suffix}"
                if os.path.exists(sidecar):
                    os.remove(sidecar)
        finally:
            if os.path.exists(staged):
                os.remove(staged)
        return {"restored_from": source, "rollback_backup": rollback if os.path.exists(rollback) else ""}

    def export_csv(self, destination: str, events: Optional[Iterable[Dict[str, Any]]] = None) -> str:
        parent = os.path.dirname(destination)
        if parent:
            os.makedirs(parent, exist_ok=True)
        rows = list(events) if events is not None else self.list_events(limit=5000)
        fields = [
            "sequence", "event_id", "session_id", "environment", "event_type",
            "occurred_at", "strategy_version", "payload_json", "previous_hash", "event_hash",
        ]
        with open(destination, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        return destination
