"""Append-only SQLite ledger for paper-trading decisions and executions."""

from __future__ import annotations

import csv
from contextlib import contextmanager
import json
import os
import sqlite3
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
                    payload_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_trading_events_session ON trading_events(session_id, sequence)"
            )

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
        try:
            with self._connection() as connection:
                connection.execute(
                    """
                    INSERT INTO trading_events(
                        event_id, session_id, environment, event_type,
                        occurred_at, strategy_version, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event_id,
                        session_id,
                        environment,
                        event_type,
                        occurred_at or _utc_now(),
                        strategy_version,
                        json.dumps(payload, ensure_ascii=False, sort_keys=True),
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

    def export_csv(self, destination: str, events: Optional[Iterable[Dict[str, Any]]] = None) -> str:
        parent = os.path.dirname(destination)
        if parent:
            os.makedirs(parent, exist_ok=True)
        rows = list(events) if events is not None else self.list_events(limit=5000)
        fields = [
            "sequence", "event_id", "session_id", "environment", "event_type",
            "occurred_at", "strategy_version", "payload_json",
        ]
        with open(destination, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        return destination
