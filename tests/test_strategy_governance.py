import tempfile
import unittest
from pathlib import Path

from strategy_governance import StrategyRegistry


GOOD_METRICS = {
    "observation_days": 60,
    "trades": 200,
    "holdout_sharpe": 1.0,
    "max_drawdown_pct": 5.0,
    "slippage_deviation_bps": 5.0,
}
GOOD_EVIDENCE = {
    "test_run_id": "ci-123",
    "code_sha": "abc123",
    "dataset_as_of": "2026-08-25",
}


class StrategyGovernanceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.registry = StrategyRegistry(str(Path(self.directory.name) / "registry.sqlite3"))
        self.strategy = self.registry.register(
            name="vol-target-momentum",
            version="1.0.0",
            parameters={"target_volatility": 0.20},
            dataset_as_of="2026-08-25",
            code_sha="abc123",
        )

    def tearDown(self):
        self.directory.cleanup()

    def test_registration_records_reproducibility_metadata(self):
        self.assertEqual(self.strategy["stage"], "research")
        self.assertEqual(self.strategy["parameters"]["target_volatility"], 0.20)
        self.assertEqual(self.strategy["code_sha"], "abc123")

    def test_promotion_requires_manual_approval_and_evidence(self):
        rejected = self.registry.request_transition(
            self.strategy["strategy_id"],
            target_stage="candidate",
            metrics=GOOD_METRICS,
            evidence=GOOD_EVIDENCE,
            manual_approved=False,
        )
        self.assertEqual(rejected["decision"], "rejected")
        self.assertEqual(rejected["strategy"]["stage"], "research")

        approved = self.registry.request_transition(
            self.strategy["strategy_id"],
            target_stage="candidate",
            metrics=GOOD_METRICS,
            evidence=GOOD_EVIDENCE,
            manual_approved=True,
            approved_by="operator@example.test",
        )
        self.assertEqual(approved["decision"], "approved")
        self.assertEqual(approved["strategy"]["stage"], "candidate")
        self.assertEqual(len(self.registry.history(self.strategy["strategy_id"])), 2)

    def test_failed_metric_gate_is_recorded_without_promotion(self):
        metrics = {**GOOD_METRICS, "holdout_sharpe": -0.5, "trades": 1}
        result = self.registry.request_transition(
            self.strategy["strategy_id"],
            target_stage="candidate",
            metrics=metrics,
            evidence=GOOD_EVIDENCE,
            manual_approved=True,
            approved_by="operator",
        )
        self.assertEqual(result["decision"], "rejected")
        self.assertIn("holdout Sharpe", result["reason"])
        self.assertIn("minimum trades", result["reason"])

    def test_small_live_requires_exchange_validation_evidence(self):
        strategy_id = self.strategy["strategy_id"]
        for target in ("candidate", "shadow", "paper"):
            self.registry.request_transition(
                strategy_id,
                target_stage=target,
                metrics=GOOD_METRICS,
                evidence=GOOD_EVIDENCE,
                manual_approved=True,
                approved_by="operator",
            )
        result = self.registry.request_transition(
            strategy_id,
            target_stage="small_live",
            metrics=GOOD_METRICS,
            evidence=GOOD_EVIDENCE,
            manual_approved=True,
            approved_by="operator",
        )
        self.assertEqual(result["decision"], "rejected")
        self.assertIn("exchange validation", result["reason"])

    def test_risk_breach_automatically_demotes_one_stage(self):
        strategy_id = self.strategy["strategy_id"]
        self.registry.request_transition(
            strategy_id,
            target_stage="candidate",
            metrics=GOOD_METRICS,
            evidence=GOOD_EVIDENCE,
            manual_approved=True,
            approved_by="operator",
        )
        result = self.registry.auto_demote(
            strategy_id,
            {"max_drawdown_pct": 50.0, "slippage_deviation_bps": 5.0},
        )
        self.assertEqual(result["decision"], "auto_demoted")
        self.assertEqual(result["strategy"]["stage"], "research")

    def test_stage_skipping_is_rejected(self):
        with self.assertRaises(ValueError):
            self.registry.request_transition(
                self.strategy["strategy_id"],
                target_stage="paper",
                metrics=GOOD_METRICS,
                evidence=GOOD_EVIDENCE,
                manual_approved=True,
                approved_by="operator",
            )


if __name__ == "__main__":
    unittest.main()
