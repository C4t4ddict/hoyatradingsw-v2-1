import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from operations import (
    OperationalStore,
    build_daily_report,
    emit_operational_alert,
    evaluate_paper_health,
    sync_paper_operational_events,
)
from paper_ledger import TradingLedger


UTC = timezone.utc


class OperationalAlertTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.store = OperationalStore(str(Path(self.directory.name) / "operations.sqlite3"), cooldown_seconds=60)

    def tearDown(self):
        self.directory.cleanup()

    def test_duplicate_alert_is_suppressed_until_cooldown(self):
        start = datetime(2026, 1, 1, tzinfo=UTC)
        first = self.store.raise_alert(
            dedup_key="worker.down", category="worker", severity="warning", message="down", now=start,
        )
        duplicate = self.store.raise_alert(
            dedup_key="worker.down", category="worker", severity="critical", message="still down",
            now=start + timedelta(seconds=30),
        )
        later = self.store.raise_alert(
            dedup_key="worker.down", category="worker", severity="critical", message="still down",
            now=start + timedelta(seconds=61),
        )

        self.assertTrue(first["should_notify"])
        self.assertFalse(duplicate["should_notify"])
        self.assertTrue(later["should_notify"])
        row = self.store.list_alerts(status="active")[0]
        self.assertEqual(row["occurrence_count"], 3)
        self.assertEqual(row["severity"], "critical")

    def test_emit_calls_notifier_only_when_dedup_allows(self):
        delivered = []
        notifier = lambda message, channel: delivered.append((message, channel)) or True
        for _ in range(2):
            emit_operational_alert(
                dedup_key="risk.block", category="risk", severity="warning", message="blocked",
                store=self.store, notifier=notifier,
            )
        self.assertEqual(len(delivered), 1)

    def test_health_raises_and_resolves_worker_and_delay_alerts(self):
        now = datetime(2026, 1, 1, 12, tzinfo=UTC)
        unhealthy = {
            "running": True,
            "worker": {"alive": False},
            "last_update": (now - timedelta(hours=1)).isoformat(),
            "consistency": {"ok": True},
            "ledger_integrity": {"ok": True},
        }
        health = evaluate_paper_health(unhealthy, now=now, store=self.store, notifier=lambda *_: True)
        self.assertFalse(health["ok"])
        self.assertEqual(len(health["active_alerts"]), 2)

        healthy = {**unhealthy, "worker": {"alive": True}, "last_update": now.isoformat()}
        health = evaluate_paper_health(healthy, now=now, store=self.store, notifier=lambda *_: True)
        self.assertTrue(health["ok"])
        self.assertEqual(health["active_alerts"], [])

    def test_order_event_is_emitted_once_across_repeated_sync(self):
        state = {
            "session_id": "s1",
            "order_events": [{"order_id": "o1", "status": "rejected", "symbol": "BTC/USDT"}],
            "risk_status": {"rejected": []},
        }
        sync_paper_operational_events(state, self.store)
        sync_paper_operational_events(state, self.store)

        alerts = self.store.list_alerts()
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["occurrence_count"], 1)


class DailyReportTests(unittest.TestCase):
    def test_report_aggregates_only_requested_utc_day(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = TradingLedger(str(Path(directory) / "ledger.sqlite3"))
            ledger.append_event(
                event_id="pending", session_id="s1", event_type="order_pending",
                payload={"order_id": "o1"}, occurred_at="2026-01-02T01:00:00+00:00",
            )
            ledger.append_event(
                event_id="fill", session_id="s1", event_type="order_filled",
                payload={"order_id": "o1", "realized_pnl": 12.5}, occurred_at="2026-01-02T02:00:00+00:00",
            )
            ledger.append_event(
                event_id="other-day", session_id="s1", event_type="order_filled",
                payload={"order_id": "o2", "realized_pnl": -99}, occurred_at="2026-01-01T23:00:00+00:00",
            )

            report = build_daily_report(ledger, report_date="2026-01-02")

            self.assertEqual(report["orders"], 1)
            self.assertEqual(report["fills"], 1)
            self.assertEqual(report["realized_pnl"], 12.5)
            self.assertEqual(report["win_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
