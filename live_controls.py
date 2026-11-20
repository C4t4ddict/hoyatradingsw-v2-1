"""Fail-closed Paper/Live transition controls with audited double confirmation."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional


FIRST_CONFIRMATION = "I UNDERSTAND LIVE ORDERS"
SECOND_CONFIRMATION = "ENABLE LIVE TRADING"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: Optional[datetime] = None) -> str:
    return (value or _now()).isoformat()


def _parse(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result.astimezone(timezone.utc)


class LiveControlStore:
    def __init__(self, path: str = "data/live_controls.sqlite3", max_cap_usdt: float = 10_000.0):
        self.path = path
        self.max_cap_usdt = max(1.0, float(max_cap_usdt))
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self):
        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS live_control_state (
                    singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                    live_enabled INTEGER NOT NULL,
                    max_order_usdt REAL NOT NULL,
                    enabled_at TEXT,
                    expires_at TEXT,
                    challenge_hash TEXT,
                    challenge_expires_at TEXT,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS settings_history (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    changed_at TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    action TEXT NOT NULL,
                    before_json TEXT NOT NULL,
                    after_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "INSERT OR IGNORE INTO live_control_state VALUES (1, 0, 100.0, NULL, NULL, NULL, NULL, ?)",
                (_iso(),),
            )

    def _row(self, connection) -> Dict[str, Any]:
        return dict(connection.execute("SELECT * FROM live_control_state WHERE singleton = 1").fetchone())

    @staticmethod
    def _public(row: Dict[str, Any], now: Optional[datetime] = None) -> Dict[str, Any]:
        current = now or _now()
        expires = _parse(row.get("expires_at"))
        enabled = bool(row.get("live_enabled")) and bool(expires and current < expires)
        challenge_expires = _parse(row.get("challenge_expires_at"))
        return {
            "mode": "live" if enabled else "paper",
            "live_enabled": enabled,
            "max_order_usdt": float(row.get("max_order_usdt") or 0.0),
            "enabled_at": row.get("enabled_at") if enabled else None,
            "expires_at": row.get("expires_at") if enabled else None,
            "challenge_pending": bool(row.get("challenge_hash") and challenge_expires and current < challenge_expires),
            "challenge_expires_at": row.get("challenge_expires_at") if challenge_expires and current < challenge_expires else None,
            "updated_at": row.get("updated_at"),
        }

    def _history(self, connection, actor: str, action: str, before: Dict[str, Any], after: Dict[str, Any]):
        connection.execute(
            "INSERT INTO settings_history(changed_at, actor, action, before_json, after_json) VALUES (?, ?, ?, ?, ?)",
            (_iso(), actor, action, json.dumps(self._public(before), sort_keys=True), json.dumps(self._public(after), sort_keys=True)),
        )

    def status(self, now: Optional[datetime] = None) -> Dict[str, Any]:
        with self._connection() as connection:
            row = self._row(connection)
            public = self._public(row, now)
            if row["live_enabled"] and not public["live_enabled"]:
                before = dict(row)
                connection.execute(
                    "UPDATE live_control_state SET live_enabled=0, enabled_at=NULL, expires_at=NULL, updated_at=? WHERE singleton=1",
                    (_iso(now),),
                )
                row = self._row(connection)
                self._history(connection, "system", "live_expired", before, row)
                public = self._public(row, now)
        return public

    def request_live_challenge(self, confirmation: str, *, actor: str = "local-user", now: Optional[datetime] = None) -> Dict[str, Any]:
        if confirmation != FIRST_CONFIRMATION:
            raise ValueError("first confirmation phrase does not match")
        current = now or _now()
        token = secrets.token_urlsafe(32)
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        expires = current + timedelta(minutes=5)
        with self._connection() as connection:
            before = self._row(connection)
            connection.execute(
                "UPDATE live_control_state SET challenge_hash=?, challenge_expires_at=?, updated_at=? WHERE singleton=1",
                (digest, _iso(expires), _iso(current)),
            )
            after = self._row(connection)
            self._history(connection, actor, "live_challenge_requested", before, after)
        return {"challenge_token": token, "expires_at": _iso(expires), "required_confirmation": SECOND_CONFIRMATION}

    def confirm_live(
        self, challenge_token: str, confirmation: str, *, actor: str = "local-user",
        duration_minutes: int = 240, now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        if confirmation != SECOND_CONFIRMATION:
            raise ValueError("second confirmation phrase does not match")
        current = now or _now()
        digest = hashlib.sha256(challenge_token.encode("utf-8")).hexdigest()
        duration = max(5, min(int(duration_minutes), 24 * 60))
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            before = self._row(connection)
            challenge_expires = _parse(before.get("challenge_expires_at"))
            if not before.get("challenge_hash") or not secrets.compare_digest(before["challenge_hash"], digest):
                raise ValueError("invalid live challenge")
            if not challenge_expires or current >= challenge_expires:
                raise ValueError("live challenge expired")
            expires = current + timedelta(minutes=duration)
            connection.execute(
                """
                UPDATE live_control_state SET live_enabled=1, enabled_at=?, expires_at=?,
                    challenge_hash=NULL, challenge_expires_at=NULL, updated_at=? WHERE singleton=1
                """,
                (_iso(current), _iso(expires), _iso(current)),
            )
            after = self._row(connection)
            self._history(connection, actor, "live_enabled", before, after)
        return self._public(after, current)

    def disable_live(self, *, actor: str = "local-user") -> Dict[str, Any]:
        with self._connection() as connection:
            before = self._row(connection)
            connection.execute(
                """
                UPDATE live_control_state SET live_enabled=0, enabled_at=NULL, expires_at=NULL,
                    challenge_hash=NULL, challenge_expires_at=NULL, updated_at=? WHERE singleton=1
                """,
                (_iso(),),
            )
            after = self._row(connection)
            self._history(connection, actor, "live_disabled", before, after)
        return self._public(after)

    def set_order_cap(self, max_order_usdt: float, *, actor: str = "local-user") -> Dict[str, Any]:
        value = float(max_order_usdt)
        if value <= 0 or value > self.max_cap_usdt:
            raise ValueError(f"max_order_usdt must be in (0, {self.max_cap_usdt}]")
        with self._connection() as connection:
            before = self._row(connection)
            connection.execute(
                "UPDATE live_control_state SET max_order_usdt=?, updated_at=? WHERE singleton=1",
                (value, _iso()),
            )
            after = self._row(connection)
            self._history(connection, actor, "order_cap_changed", before, after)
        return self._public(after)

    def authorize_order(self, notional_usdt: float, now: Optional[datetime] = None) -> Dict[str, Any]:
        status = self.status(now)
        notional = max(0.0, float(notional_usdt))
        reasons = []
        if not status["live_enabled"]:
            reasons.append("live_not_double_confirmed")
        if notional > status["max_order_usdt"]:
            reasons.append("max_order_usdt_exceeded")
        return {"allowed": not reasons, "notional_usdt": notional, "reasons": reasons, "control": status}

    def history(self, limit: int = 200) -> list[Dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM settings_history ORDER BY sequence DESC LIMIT ?",
                (max(1, min(int(limit), 1000)),),
            ).fetchall()
        return [
            {**dict(row), "before": json.loads(row["before_json"]), "after": json.loads(row["after_json"])}
            for row in rows
        ]


def get_live_control_store() -> LiveControlStore:
    return LiveControlStore(
        os.getenv("LIVE_CONTROL_DB_PATH", "data/live_controls.sqlite3"),
        float(os.getenv("LIVE_CONTROL_MAX_CAP_USDT", "10000")),
    )
