"""Persistent operational alerts, health evaluation, and daily paper reports."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Optional

from notifier import send_telegram
from paper_ledger import TradingLedger
from security import mask_text, redact_sensitive


SEVERITIES = {"info": 10, "warning": 20, "critical": 30}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: Optional[datetime] = None) -> str:
    return (value or _now()).isoformat()


def _parse(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


class OperationalStore:
    def __init__(self, path: str = "data/operations.sqlite3", cooldown_seconds: int = 900):
        self.path = path
        self.cooldown_seconds = max(0, int(cooldown_seconds))
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
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS operational_alerts (
                    alert_id TEXT PRIMARY KEY,
                    dedup_key TEXT NOT NULL,
                    category TEXT NOT NULL,
                    severity TEXT NOT NULL CHECK(severity IN ('info','warning','critical')),
                    message TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('active','resolved')),
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    last_notified_at TEXT,
                    occurrence_count INTEGER NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_active_alert_dedup ON operational_alerts(dedup_key) WHERE status = 'active'"
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS daily_reports (
                    report_date TEXT NOT NULL,
                    environment TEXT NOT NULL,
                    generated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    notified_at TEXT,
                    PRIMARY KEY(report_date, environment)
                )
                """
            )

    def raise_alert(
        self,
        *,
        dedup_key: str,
        category: str,
        severity: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        if severity not in SEVERITIES:
            raise ValueError("severity must be info, warning, or critical")
        observed = now or _now()
        observed_at = _iso(observed)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute(
                "SELECT * FROM operational_alerts WHERE dedup_key = ? AND status = 'active'",
                (dedup_key,),
            ).fetchone()
            should_notify = False
            if current:
                last_notified = _parse(current["last_notified_at"])
                should_notify = last_notified is None or observed - last_notified >= timedelta(seconds=self.cooldown_seconds)
                severity = max((severity, current["severity"]), key=lambda item: SEVERITIES[item])
                connection.execute(
                    """
                    UPDATE operational_alerts
                    SET category = ?, severity = ?, message = ?, details_json = ?,
                        last_seen_at = ?, last_notified_at = ?, occurrence_count = occurrence_count + 1
                    WHERE alert_id = ?
                    """,
                    (
                        category, severity, mask_text(message), json.dumps(redact_sensitive(details or {}), ensure_ascii=False, sort_keys=True),
                        observed_at, observed_at if should_notify else current["last_notified_at"], current["alert_id"],
                    ),
                )
                alert_id = current["alert_id"]
            else:
                alert_id = hashlib.sha256(f"{dedup_key}|{observed_at}".encode("utf-8")).hexdigest()
                should_notify = True
                connection.execute(
                    "INSERT INTO operational_alerts VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, 1)",
                    (
                        alert_id, dedup_key, category, severity, mask_text(message),
                        json.dumps(redact_sensitive(details or {}), ensure_ascii=False, sort_keys=True),
                        observed_at, observed_at, observed_at,
                    ),
                )
        return {"alert_id": alert_id, "dedup_key": dedup_key, "severity": severity, "should_notify": should_notify}

    def resolve(self, dedup_key: str, now: Optional[datetime] = None) -> bool:
        with self._connection() as connection:
            cursor = connection.execute(
                "UPDATE operational_alerts SET status = 'resolved', last_seen_at = ? WHERE dedup_key = ? AND status = 'active'",
                (_iso(now), dedup_key),
            )
        return cursor.rowcount > 0

    def list_alerts(self, *, status: Optional[str] = None, limit: int = 200) -> list[Dict[str, Any]]:
        where, params = "", []
        if status:
            if status not in {"active", "resolved"}:
                raise ValueError("invalid status")
            where, params = "WHERE status = ?", [status]
        params.append(max(1, min(int(limit), 1000)))
        with self._connection() as connection:
            rows = connection.execute(
                f"SELECT * FROM operational_alerts {where} ORDER BY last_seen_at DESC LIMIT ?", params
            ).fetchall()
        return [{**dict(row), "details": json.loads(row["details_json"])} for row in rows]

    def save_report(self, report: Dict[str, Any], environment: str = "paper", notified: bool = False) -> Dict[str, Any]:
        report_date = report["report_date"]
        generated_at = report.get("generated_at") or _iso()
        with self._connection() as connection:
            existing = connection.execute(
                "SELECT notified_at FROM daily_reports WHERE report_date = ? AND environment = ?",
                (report_date, environment),
            ).fetchone()
            notified_at = (_iso() if notified else (existing["notified_at"] if existing else None))
            connection.execute(
                """
                INSERT INTO daily_reports VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(report_date, environment) DO UPDATE SET
                    generated_at=excluded.generated_at, payload_json=excluded.payload_json,
                    notified_at=COALESCE(excluded.notified_at, daily_reports.notified_at)
                """,
                (report_date, environment, generated_at, json.dumps(report, ensure_ascii=False, sort_keys=True), notified_at),
            )
        return {**report, "notified_at": notified_at}


def get_store() -> OperationalStore:
    return OperationalStore(
        os.getenv("OPERATIONS_DB_PATH", "data/operations.sqlite3"),
        int(os.getenv("OPERATIONS_ALERT_COOLDOWN_SEC", "900")),
    )


def emit_operational_alert(
    *, dedup_key: str, category: str, severity: str, message: str,
    details: Optional[Dict[str, Any]] = None, store: Optional[OperationalStore] = None,
    notifier: Optional[Callable[[str, str], bool]] = None,
) -> Dict[str, Any]:
    store = store or get_store()
    result = store.raise_alert(
        dedup_key=dedup_key, category=category, severity=severity,
        message=message, details=details,
    )
    if result["should_notify"]:
        (notifier or send_telegram)(f"[{severity.upper()}] {message}", "paper")
    return result


def evaluate_paper_health(
    audit: Dict[str, Any], *, now: Optional[datetime] = None,
    max_data_delay_seconds: int = 900, store: Optional[OperationalStore] = None,
    notifier: Optional[Callable[[str, str], bool]] = None,
) -> Dict[str, Any]:
    store = store or get_store()
    current = now or _now()
    raised = []

    def check(condition, key, category, severity, message, details=None):
        if condition:
            raised.append(emit_operational_alert(
                dedup_key=key, category=category, severity=severity,
                message=message, details=details, store=store, notifier=notifier,
            ))
        else:
            store.resolve(key, current)

    running = bool(audit.get("running"))
    worker_alive = bool((audit.get("worker") or {}).get("alive"))
    check(running and not worker_alive, "paper.worker.down", "worker", "critical", "Paper worker is not running")
    updated = _parse(audit.get("last_update"))
    delay = (current - updated).total_seconds() if updated else None
    check(running and (delay is None or delay > max_data_delay_seconds), "paper.data.delayed", "data", "warning", "Paper market data update is delayed", {"delay_seconds": delay})
    consistency = audit.get("consistency") or {}
    check(not consistency.get("ok", True), "paper.state.inconsistent", "state", "critical", "Paper state consistency check failed", consistency)
    integrity = audit.get("ledger_integrity") or {}
    check(not integrity.get("ok", True), "paper.ledger.integrity", "ledger", "critical", "Trading ledger integrity check failed", integrity)
    return {"ok": not raised, "raised": raised, "active_alerts": store.list_alerts(status="active", limit=100)}


def sync_paper_operational_events(state: Dict[str, Any], store: Optional[OperationalStore] = None) -> None:
    store = store or get_store()
    session_id = state.get("session_id") or "unknown"
    seen = set(state.get("ops_seen_event_keys") or [])
    for event in (state.get("order_events") or [])[-50:]:
        status = event.get("status")
        order_id = event.get("order_id") or "unknown"
        event_key = f"order.{status}.{order_id}"
        if event_key in seen:
            continue
        if status == "rejected":
            emit_operational_alert(
                dedup_key=f"order.rejected.{order_id}", category="order", severity="warning",
                message=f"Paper order rejected: {event.get('symbol', '-')}", details=event,
                store=store,
            )
            seen.add(event_key)
        elif status == "filled":
            emit_operational_alert(
                dedup_key=f"order.filled.{order_id}", category="fill", severity="info",
                message=f"Paper order filled: {event.get('symbol', '-')}", details=event,
                store=store,
            )
            seen.add(event_key)
    rejected = (state.get("risk_status") or {}).get("rejected") or []
    if rejected:
        emit_operational_alert(
            dedup_key=f"risk.block.{session_id}", category="risk", severity="warning",
            message="Paper risk policy blocked execution", details={"reasons": rejected}, store=store,
        )
    else:
        store.resolve(f"risk.block.{session_id}")
    state["ops_seen_event_keys"] = sorted(seen)[-5000:]


def build_daily_report(
    ledger: TradingLedger, *, report_date: Optional[str] = None,
    environment: str = "paper", now: Optional[datetime] = None,
) -> Dict[str, Any]:
    current = now or _now()
    day = report_date or current.date().isoformat()
    events = ledger.list_events(limit=5000)
    selected = [
        event for event in events
        if event["environment"] == environment and _parse(event["occurred_at"]).date().isoformat() == day
    ]
    fills = [event for event in selected if event["event_type"] == "order_filled"]
    rejections = [event for event in selected if event["event_type"] == "order_rejected"]
    realized = sum(float(event["payload"].get("realized_pnl", 0.0) or 0.0) for event in fills)
    wins = sum(float(event["payload"].get("realized_pnl", 0.0) or 0.0) > 0 for event in fills)
    return {
        "report_date": day,
        "generated_at": _iso(current),
        "environment": environment,
        "orders": sum(event["event_type"] == "order_pending" for event in selected),
        "fills": len(fills),
        "rejections": len(rejections),
        "realized_pnl": realized,
        "win_rate": wins / len(fills) if fills else 0.0,
        "event_count": len(selected),
    }


def generate_daily_report(*, notify: bool = False) -> Dict[str, Any]:
    ledger = TradingLedger(os.getenv("TRADING_LEDGER_PATH", "data/trading_ledger.sqlite3"))
    store = get_store()
    report = build_daily_report(ledger)
    notified = False
    if notify:
        message = (
            f"Paper daily report {report['report_date']}\n"
            f"fills={report['fills']} rejected={report['rejections']} "
            f"PnL={report['realized_pnl']:.2f} win_rate={report['win_rate']:.1%}"
        )
        notified = send_telegram(message, channel="paper")
    return store.save_report(report, notified=notified)
