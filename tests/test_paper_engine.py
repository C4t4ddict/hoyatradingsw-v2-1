import tempfile
import unittest
from pathlib import Path

from paper_engine import (
    FOUR_HOURS_MS,
    EventDrivenPaperEngine,
    RiskContext,
    RiskPolicy,
    VolTargetMomentumStrategy,
    evaluate_order_risk,
)
from paper_ledger import TradingLedger


def _history(count=30, start=100.0, step=1.0):
    rows = []
    for index in range(count):
        price = start + step * index
        rows.append([index * FOUR_HOURS_MS, price, price + 1, price - 1, price, 1000.0])
    return rows


def _histories(step=1.0):
    return {
        "BTC/USDT": _history(start=100.0, step=step),
        "ETH/USDT": _history(start=50.0, step=step * 0.5),
        "SOL/USDT": _history(start=20.0, step=step * 0.2),
    }


class VolTargetStrategyTests(unittest.TestCase):
    def setUp(self):
        self.strategy = VolTargetMomentumStrategy(
            ema_bars=10,
            momentum_bars=5,
            volatility_bars=5,
            target_volatility=0.20,
        )

    def test_uptrend_creates_long_cash_weights_without_leverage(self):
        histories = _histories(step=1.0)
        decision = self.strategy.evaluate(histories, histories["BTC/USDT"][-1][0] + FOUR_HOURS_MS)

        self.assertTrue(decision.data_quality["ok"])
        self.assertTrue(all(signal["active"] for signal in decision.signals.values()))
        self.assertGreater(sum(decision.target_weights.values()), 0.0)
        self.assertLessEqual(sum(decision.target_weights.values()), 1.0)
        self.assertAlmostEqual(decision.cash_weight + sum(decision.target_weights.values()), 1.0)

    def test_downtrend_moves_entire_portfolio_to_cash(self):
        histories = _histories(step=-0.4)
        decision = self.strategy.evaluate(histories, histories["BTC/USDT"][-1][0] + FOUR_HOURS_MS)

        self.assertTrue(decision.data_quality["ok"])
        self.assertTrue(all(weight == 0.0 for weight in decision.target_weights.values()))
        self.assertEqual(decision.cash_weight, 1.0)

    def test_missing_interval_rejects_signal(self):
        histories = _histories()
        histories["ETH/USDT"].pop(12)
        decision = self.strategy.evaluate(histories, histories["BTC/USDT"][-1][0] + FOUR_HOURS_MS)

        self.assertFalse(decision.data_quality["ok"])
        self.assertTrue(any("missing 4h intervals" in error for error in decision.data_quality["errors"]))


class RiskPolicyTests(unittest.TestCase):
    def _context(self, **updates):
        values = dict(
            initial_equity=1000.0,
            current_equity=1000.0,
            equity_peak=1000.0,
            latest_bar_ms=100,
            now_ms=100,
            spread_bps=5.0,
        )
        values.update(updates)
        return RiskContext(**values)

    def test_drawdown_reduces_then_blocks_new_buys(self):
        policy = RiskPolicy(max_order_nav_pct=1.0)
        reduced = evaluate_order_risk("buy", 400.0, self._context(current_equity=890.0), policy)
        blocked = evaluate_order_risk("buy", 400.0, self._context(current_equity=840.0), policy)

        self.assertTrue(reduced["allowed"])
        self.assertEqual(reduced["adjusted_notional"], 200.0)
        self.assertFalse(blocked["allowed"])
        self.assertIn("drawdown_buy_block", blocked["reasons"])

    def test_stale_spread_daily_loss_and_balance_mismatch_block(self):
        policy = RiskPolicy(stale_after_ms=10, max_spread_bps=20)
        result = evaluate_order_risk(
            "buy",
            100.0,
            self._context(
                latest_bar_ms=0,
                now_ms=100,
                spread_bps=30.0,
                daily_realized_pnl=-25.0,
                balance_consistent=False,
            ),
            policy,
        )

        self.assertFalse(result["allowed"])
        self.assertEqual(
            set(result["reasons"]),
            {"balance_mismatch", "daily_loss_limit", "spread_limit", "stale_market_data"},
        )


class EventDrivenEngineTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ledger = TradingLedger(str(Path(self.temp_dir.name) / "ledger.sqlite3"))
        self.strategy = VolTargetMomentumStrategy(
            ema_bars=10,
            momentum_bars=5,
            volatility_bars=5,
            target_volatility=0.20,
        )
        self.engine = EventDrivenPaperEngine(
            session_id="session-1",
            initial_cash=1000.0,
            ledger=self.ledger,
            strategy=self.strategy,
            risk_policy=RiskPolicy(max_order_nav_pct=1.0),
            fee_pct=0.0,
            slippage_pct=0.0,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_close_creates_idempotent_pending_orders_filled_at_next_open(self):
        histories = _histories()
        signal_bar = histories["BTC/USDT"][-1][0]
        first = self.engine.on_bar_close(histories, now_ms=signal_bar + FOUR_HOURS_MS)
        duplicate = self.engine.on_bar_close(histories, now_ms=signal_bar + FOUR_HOURS_MS + 1000)

        self.assertTrue(first["orders"])
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(len(self.engine.pending_orders), len(first["orders"]))
        self.assertEqual(self.engine.on_bar_open(timestamp_ms=signal_bar, open_prices={}), [])

        fills = self.engine.on_bar_open(
            timestamp_ms=signal_bar + FOUR_HOURS_MS,
            open_prices={symbol: rows[-1][4] for symbol, rows in histories.items()},
        )
        self.assertEqual(len(fills), len(first["orders"]))
        self.assertFalse(self.engine.pending_orders)
        self.assertGreater(sum(self.engine.portfolio.units.values()), 0.0)

    def test_rejected_order_records_reason_without_pending_execution(self):
        histories = _histories()
        signal_bar = histories["BTC/USDT"][-1][0]
        result = self.engine.on_bar_close(
            histories,
            now_ms=signal_bar + FOUR_HOURS_MS,
            spreads_bps={symbol: 100.0 for symbol in histories},
        )

        self.assertTrue(result["orders"])
        self.assertTrue(all(order["status"] == "rejected" for order in result["orders"]))
        self.assertFalse(self.engine.pending_orders)
        events = self.ledger.list_events(session_id="session-1")
        self.assertTrue(all(event["event_type"] == "order_rejected" for event in events))

    def test_snapshot_restores_pending_orders_and_portfolio(self):
        histories = _histories()
        signal_bar = histories["BTC/USDT"][-1][0]
        self.engine.on_bar_close(histories, now_ms=signal_bar + FOUR_HOURS_MS)
        snapshot = self.engine.snapshot()
        restored = EventDrivenPaperEngine(
            session_id="session-1",
            initial_cash=1000.0,
            ledger=self.ledger,
            strategy=self.strategy,
        )
        restored.restore(snapshot)

        self.assertEqual(restored.snapshot(), snapshot)

    def test_sell_fill_updates_realized_pnl_and_cost_basis(self):
        self.engine.portfolio.cash = 900.0
        self.engine.portfolio.units["BTC/USDT"] = 1.0
        self.engine.portfolio.average_cost["BTC/USDT"] = 100.0
        self.engine.pending_orders = [{
            "order_id": "sell-one",
            "symbol": "BTC/USDT",
            "side": "sell",
            "target_weight": 0.0,
            "signal_bar_ms": 0,
            "execute_after_ms": FOUR_HOURS_MS,
            "notional": 110.0,
            "risk": {"allowed": True, "reasons": []},
        }]

        fills = self.engine.on_bar_open(
            timestamp_ms=FOUR_HOURS_MS,
            open_prices={"BTC/USDT": 110.0},
        )

        self.assertEqual(fills[0]["realized_pnl"], 10.0)
        self.assertEqual(self.engine.portfolio.daily_realized_pnl, 10.0)
        self.assertNotIn("BTC/USDT", self.engine.portfolio.average_cost)


class TradingLedgerTests(unittest.TestCase):
    def test_event_id_is_append_only_and_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = TradingLedger(str(Path(directory) / "ledger.sqlite3"))
            self.assertTrue(
                ledger.append_event(
                    event_id="same-id",
                    session_id="s1",
                    event_type="order_pending",
                    payload={"symbol": "BTC/USDT"},
                )
            )
            self.assertFalse(
                ledger.append_event(
                    event_id="same-id",
                    session_id="s1",
                    event_type="order_pending",
                    payload={"symbol": "ETH/USDT"},
                )
            )
            events = ledger.list_events(session_id="s1")
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["payload"]["symbol"], "BTC/USDT")


if __name__ == "__main__":
    unittest.main()
