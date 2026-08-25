import csv
from contextlib import closing
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import paper_live
from paper_ledger import TradingLedger


class LedgerIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.path = self.root / "ledger.sqlite3"
        self.ledger = TradingLedger(str(self.path))

    def tearDown(self):
        self.directory.cleanup()

    def append(self, event_id, payload=None):
        return self.ledger.append_event(
            event_id=event_id,
            session_id="session-1",
            event_type="order_pending",
            payload=payload or {"order_id": event_id},
            strategy_version="strategy@commit",
        )

    def test_hash_chain_detects_payload_tampering(self):
        self.append("one")
        self.append("two")
        self.assertTrue(self.ledger.verify_integrity()["ok"])

        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("UPDATE trading_events SET payload_json = ? WHERE event_id = ?", ('{"tampered": true}', "one"))
            connection.commit()
        check = self.ledger.verify_integrity()

        self.assertFalse(check["ok"])
        self.assertIn("event_hash_mismatch", {row["reason"] for row in check["failures"]})

    def test_backup_restore_keeps_valid_snapshot_and_rollback(self):
        self.append("one")
        backup = self.root / "backup.sqlite3"
        self.ledger.backup(str(backup))
        self.append("two")

        result = self.ledger.restore_backup(str(backup))

        restored = TradingLedger(str(self.path))
        self.assertTrue(restored.verify_integrity()["ok"])
        self.assertEqual(len(restored.list_events(session_id="session-1")), 1)
        self.assertTrue(Path(result["rollback_backup"]).exists())

    def test_csv_export_contains_chain_and_version_metadata(self):
        self.append("one")
        destination = self.root / "ledger.csv"
        self.ledger.export_csv(str(destination))

        with destination.open(encoding="utf-8") as handle:
            row = next(csv.DictReader(handle))
        self.assertEqual(row["strategy_version"], "strategy@commit")
        self.assertTrue(row["event_hash"])


class SessionRecoveryTests(unittest.TestCase):
    def test_reconciliation_recovers_pending_orders_from_ledger(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = TradingLedger(str(Path(directory) / "ledger.sqlite3"))
            pending = {"order_id": "order-1", "symbol": "BTC/USDT", "side": "buy"}
            ledger.append_event(
                event_id="order-1", session_id="session-1",
                event_type="order_pending", payload=pending,
            )
            state = {"session_id": "session-1", "event_engine": {"pending_orders": []}}

            recovered = paper_live.reconcile_session_state(state, ledger)

            self.assertTrue(recovered["reconciliation"]["ok"])
            self.assertTrue(recovered["reconciliation"]["pending_order_mismatch"])
            self.assertEqual(recovered["event_engine"]["pending_orders"], [pending])

    @patch("paper_live._persist_session_snapshot")
    @patch("paper_live.start_background_worker", return_value=123)
    @patch("paper_live._release_lock")
    def test_resume_applies_config_update_and_removes_unreachable_branch(self, _release, _worker, _snapshot):
        with tempfile.TemporaryDirectory() as directory, \
                patch("paper_live.LEDGER_PATH", str(Path(directory) / "ledger.sqlite3")):
            state_path = str(Path(directory) / "state.json")
            paper_live.save_state({
                "session_id": "session-resume",
                "running": False,
                "paused": True,
                "config": {"initial_usdt": 1000.0, "leverage": 1.0},
                "config_snapshot": {"initial_usdt": 1000.0, "leverage": 1.0},
                "metrics": {"virtual_balance": 1000.0, "starting_balance": 1000.0, "trades": 0},
                "result": {"initial_usdt": 1000.0, "final_usdt": 1000.0, "trades": [], "total_trades": 0},
            }, state_path)

            resumed = paper_live.resume_session({"leverage": 2.0}, state_path)

            self.assertTrue(resumed["running"])
            self.assertFalse(resumed["paused"])
            self.assertEqual(resumed["config"]["leverage"], 2.0)
            self.assertEqual(resumed["config_snapshot"]["leverage"], 2.0)
            event_types = {row["event_type"] for row in TradingLedger(paper_live.LEDGER_PATH).list_events()}
            self.assertIn("config_changed", event_types)
            self.assertIn("session_resumed", event_types)


if __name__ == "__main__":
    unittest.main()
