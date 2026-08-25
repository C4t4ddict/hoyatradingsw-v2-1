import json
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import paper_live
from backend.app.services import account_service, overview_service, risk_service


UTC = timezone.utc


class ApiConsistencyTests(unittest.TestCase):
    @patch("backend.app.services.overview_service.build_signal_summary")
    @patch("backend.app.services.overview_service.get_market_brief")
    @patch("backend.app.services.overview_service.summarize", return_value={"total_trades": 1})
    @patch("backend.app.services.overview_service.read_events", return_value=[])
    def test_overview_returns_the_ml_signal_contract_used_by_ui(self, _events, _summary, brief, build):
        brief.return_value = {"top": [{"title": "event"}], "long_score": 2.0, "short_score": 1.0}
        build.return_value = {"decision": {"bias": "neutral"}, "scores": {"long_score": 0.0}}

        payload = overview_service.get_overview_payload()

        self.assertIn("ml_signal", payload)
        self.assertNotIn("ml_pred", payload)
        build.assert_called_once_with(brief.return_value["top"][0], brief.return_value)

    @patch("backend.app.services.risk_service.get_live_control_store")
    @patch("backend.app.services.risk_service.health")
    def test_risk_payload_normalizes_fields_consumed_by_ui(self, health, live_store):
        health.return_value = {
            "dry_run": True,
            "risk_guard": {
                "spot": {"daily_loss_limit_usdt": 30, "max_consecutive_losses": 3},
                "futures": {"daily_loss_limit_usdt": 20, "max_consecutive_losses": 2},
            },
            "max_concurrent_positions": {"spot": 5, "futures": 3},
            "execution_policy": {},
        }
        live_store.return_value.status.return_value = {"mode": "paper"}

        payload = risk_service.get_risk_payload()

        self.assertTrue(payload["risk_guard"]["futures"]["enabled"])
        self.assertEqual(payload["risk_guard"]["futures"]["daily_loss_limit_usdt"], 20)
        self.assertEqual(payload["risk_guard"]["futures"]["max_open_positions"], 3)
        self.assertEqual(payload["execution_policy"]["live_control"]["mode"], "paper")

    @patch("backend.app.services.account_service.account_status")
    def test_account_service_forwards_request_authentication(self, status):
        status.return_value = {"ok": True}
        account_service.get_account_payload("futures", "request-token")
        status.assert_called_once_with(market_type="futures", x_webhook_token="request-token")


class NeutralFallbackTests(unittest.TestCase):
    def test_neutral_signal_always_holds_even_with_legacy_agreement_scores(self):
        selection = paper_live.select_ml_execution_policy(
            {"bias": "neutral"},
            {"up_5m": 0.9, "up_15m": 0.9, "intel_long_score": 10, "intel_short_score": 0},
            {"result": {"trades": []}},
            now=datetime(2026, 1, 1, tzinfo=UTC),
        )
        self.assertTrue(selection["hold"])
        self.assertEqual(selection["fallback_mode"], "neutral_wait_quality_gate")
        self.assertEqual(selection["position_mode"], "flat")

    def test_loss_cooldown_expires_without_rearming_on_same_trades(self):
        now = datetime(2026, 1, 1, tzinfo=UTC)
        state = {"result": {"trades": [{"pnl": -1}, {"pnl": -2}]}}
        first = paper_live.select_ml_execution_policy({"bias": "long"}, {}, state, now=now)
        after = paper_live.select_ml_execution_policy({"bias": "long"}, {}, state, now=now + timedelta(hours=25))

        self.assertTrue(first["hold"])
        self.assertFalse(after["hold"])
        self.assertEqual(after["position_mode"], "long")


class AtomicPaperStateTests(unittest.TestCase):
    def test_failed_atomic_write_preserves_previous_valid_state(self):
        directory = Path.cwd() / "data"
        path_object = directory / f"test-state-{uuid.uuid4().hex}.json"
        path = str(path_object)
        try:
            paper_live.save_state({"running": False, "metrics": {"virtual_balance": 100}}, path)
            with patch("paper_live._replace_state_file", side_effect=RuntimeError("interrupted")):
                with self.assertRaises(RuntimeError):
                    paper_live.save_state({"running": True, "metrics": {"virtual_balance": 1}}, path)

            self.assertEqual(paper_live.load_state(path)["metrics"]["virtual_balance"], 100)
            self.assertEqual(list(Path(directory).glob("*.tmp")), [])
        finally:
            path_object.unlink(missing_ok=True)

    @patch("paper_live._is_pid_alive", return_value=True)
    @patch("paper_live.os.getpid", return_value=999)
    def test_second_worker_cannot_acquire_live_lock(self, _pid, _alive):
        lock_path = Path.cwd() / "data" / f"test-worker-{uuid.uuid4().hex}.lock"
        try:
            lock_path.write_text(json.dumps({"pid": 123}), encoding="utf-8")
            self.assertFalse(paper_live._acquire_lock(str(lock_path)))
        finally:
            lock_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
