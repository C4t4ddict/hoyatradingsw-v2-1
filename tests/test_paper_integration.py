import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import paper_live
from backend.app.services import paper_service
from paper_engine import FOUR_HOURS_MS


def _market_history(start_price):
    count = 1220
    final_start = int(datetime.now(timezone.utc).timestamp() * 1000) - FOUR_HOURS_MS
    first = final_start - (count - 1) * FOUR_HOURS_MS
    return [
        [first + index * FOUR_HOURS_MS, start_price + index * 0.1, start_price + index * 0.1 + 1, start_price + index * 0.1 - 1, start_price + index * 0.1, 1000.0]
        for index in range(count)
    ]


class PaperServiceTests(unittest.TestCase):
    @patch("backend.app.services.paper_service.start_paper_session")
    @patch("backend.app.services.paper_service.stop_background_worker")
    def test_default_session_is_safe_long_cash_portfolio(self, _stop, start):
        start.side_effect = lambda config: config
        config = paper_service.start_paper()

        self.assertEqual(config["strategy"], "vol_target_momentum")
        self.assertEqual(config["timeframe"], "4h")
        self.assertEqual(config["position_mode"], "long_cash")
        self.assertEqual(config["leverage"], 1.0)
        self.assertEqual(config["target_volatility"], 0.20)

    @patch("backend.app.services.paper_service.start_paper_session")
    @patch("backend.app.services.paper_service.stop_background_worker")
    def test_unsafe_paper_overrides_are_clamped_to_validated_policy(self, _stop, start):
        start.side_effect = lambda config: config
        config = paper_service.start_paper({
            "market_type": "futures", "symbol": "XRP/USDT:USDT",
            "position_mode": "short", "leverage": 10, "target_volatility": 0.9,
        })

        self.assertEqual(config["market_type"], "spot")
        self.assertEqual(config["symbol"], "BTC/ETH/SOL")
        self.assertEqual(config["position_mode"], "long_cash")
        self.assertEqual(config["leverage"], 1.0)
        self.assertEqual(config["target_volatility"], 0.25)

    @patch("backend.app.services.paper_service.build_signal_summary", return_value={})
    @patch("backend.app.services.paper_service.get_market_brief", return_value={"top": []})
    @patch("backend.app.services.paper_service.load_paper_state")
    def test_payload_exposes_strategy_risk_and_order_events(self, load, _brief, _signal):
        load.return_value = {
            "strategy_decision": {"target_weights": {"BTC/USDT": 0.4}},
            "risk_status": {"pending_count": 1},
            "order_events": [{"status": "pending"}],
            "event_engine": {"pending_orders": [{"order_id": "one"}]},
        }
        payload = paper_service.get_paper_payload()

        self.assertEqual(payload["strategy_decision"]["target_weights"]["BTC/USDT"], 0.4)
        self.assertEqual(payload["risk_status"]["pending_count"], 1)
        self.assertEqual(payload["pending_orders"][0]["order_id"], "one")
        _brief.assert_called_once_with(force_refresh=False)


class PaperLiveIntegrationTests(unittest.TestCase):
    @patch("paper_live._release_lock")
    @patch("paper_live._persist_session_snapshot")
    @patch("paper_live.get_exchange", return_value=object())
    def test_vol_target_update_persists_decision_and_pending_orders(self, _exchange, _snapshot, _release):
        histories = {
            "BTC/USDT": _market_history(100.0),
            "ETH/USDT": _market_history(50.0),
            "SOL/USDT": _market_history(20.0),
        }
        with tempfile.TemporaryDirectory() as directory, \
                patch("paper_live.fetch_ohlcv", side_effect=lambda exchange, symbol, *args, **kwargs: histories[symbol]), \
                patch("paper_live.LEDGER_PATH", str(Path(directory) / "ledger.sqlite3")):
            state_path = str(Path(directory) / "state.json")
            state = {
                "session_id": "session-integration",
                "running": True,
                "paused": False,
                "config": {
                    "mode": "vol_target_momentum",
                    "strategy": "vol_target_momentum",
                    "initial_usdt": 1000.0,
                    "target_volatility": 0.20,
                },
                "metrics": {"virtual_balance": 1000.0, "starting_balance": 1000.0, "trades": 0},
                "result": {"initial_usdt": 1000.0, "final_usdt": 1000.0, "trades": [], "total_trades": 0},
                "config_snapshot": {"mode": "vol_target_momentum", "initial_usdt": 1000.0},
            }
            updated = paper_live._update_vol_target_session(state, state["config"], state_path)

            self.assertEqual(updated["executed_strategy"], "vol_target_momentum")
            self.assertEqual(updated["executed_timeframe"], "4h")
            self.assertTrue(updated["strategy_decision"]["data_quality"]["ok"])
            self.assertTrue(updated["event_engine"]["pending_orders"])
            self.assertTrue(Path(state_path).exists())

    @patch("paper_live._release_lock")
    @patch("paper_live._persist_session_snapshot")
    @patch("paper_live.get_exchange", return_value=object())
    @patch("paper_live.fetch_ohlcv", side_effect=RuntimeError("network unavailable"))
    def test_market_data_failure_holds_without_creating_orders(self, _fetch, _exchange, _snapshot, _release):
        with tempfile.TemporaryDirectory() as directory, \
                patch("paper_live.LEDGER_PATH", str(Path(directory) / "ledger.sqlite3")):
            state = {
                "session_id": "session-failure",
                "running": True,
                "config": {"mode": "vol_target_momentum", "initial_usdt": 1000.0},
                "metrics": {"virtual_balance": 1000.0, "starting_balance": 1000.0, "trades": 0},
                "result": {"initial_usdt": 1000.0, "final_usdt": 1000.0, "trades": [], "total_trades": 0},
            }
            updated = paper_live._update_vol_target_session(
                state,
                state["config"],
                str(Path(directory) / "state.json"),
            )

            self.assertEqual(updated["fallback_mode"], "data_quality_hold")
            self.assertFalse(updated["event_engine"]["pending_orders"])
            self.assertFalse(updated["strategy_decision"]["data_quality"]["ok"])


if __name__ == "__main__":
    unittest.main()
