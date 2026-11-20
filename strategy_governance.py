"""Persistent, evidence-based strategy approval and automatic demotion."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Optional


STAGES = ("research", "candidate", "shadow", "paper", "small_live", "live")
DEFAULT_GATES: Dict[str, Dict[str, float]] = {
    "candidate": {"min_observation_days": 0, "min_trades": 10, "min_holdout_sharpe": 0.25, "max_drawdown_pct": 40, "max_slippage_deviation_bps": 50},
    "shadow": {"min_observation_days": 7, "min_trades": 20, "min_holdout_sharpe": 0.30, "max_drawdown_pct": 30, "max_slippage_deviation_bps": 35},
    "paper": {"min_observation_days": 14, "min_trades": 30, "min_holdout_sharpe": 0.35, "max_drawdown_pct": 20, "max_slippage_deviation_bps": 25},
    "small_live": {"min_observation_days": 28, "min_trades": 60, "min_holdout_sharpe": 0.40, "max_drawdown_pct": 15, "max_slippage_deviation_bps": 20},
    "live": {"min_observation_days": 30, "min_trades": 100, "min_holdout_sharpe": 0.50, "max_drawdown_pct": 12, "max_slippage_deviation_bps": 15},
}
REQUIRED_EVIDENCE = ("test_run_id", "code_sha", "dataset_as_of")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class StrategyRegistry:
    """Store strategy versions and append-only transition decisions."""

    def __init__(self, path: str = "data/strategy_registry.sqlite3"):
        self.path = path
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

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS strategy_versions (
                    strategy_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    version TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    parameters_json TEXT NOT NULL,
                    dataset_as_of TEXT NOT NULL,
                    code_sha TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(name, version)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS strategy_transitions (
                    transition_id TEXT PRIMARY KEY,
                    strategy_id TEXT NOT NULL,
                    from_stage TEXT NOT NULL,
                    to_stage TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    approved_by TEXT,
                    metrics_json TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

    def register(
        self,
        *,
        name: str,
        version: str,
        parameters: Dict[str, Any],
        dataset_as_of: str,
        code_sha: str,
    ) -> Dict[str, Any]:
        strategy_id = str(uuid.uuid4())
        timestamp = _now()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO strategy_versions(
                    strategy_id, name, version, stage, parameters_json,
                    dataset_as_of, code_sha, created_at, updated_at
                ) VALUES (?, ?, ?, 'research', ?, ?, ?, ?, ?)
                """,
                (strategy_id, name, version, json.dumps(parameters, sort_keys=True), dataset_as_of, code_sha, timestamp, timestamp),
            )
        return self.get(strategy_id)

    def get(self, strategy_id: str) -> Dict[str, Any]:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM strategy_versions WHERE strategy_id = ?", (strategy_id,)).fetchone()
        if row is None:
            raise KeyError(strategy_id)
        result = dict(row)
        result["parameters"] = json.loads(result.pop("parameters_json"))
        return result

    def list(self) -> list[Dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute("SELECT strategy_id FROM strategy_versions ORDER BY created_at DESC").fetchall()
        return [self.get(row["strategy_id"]) for row in rows]

    def history(self, strategy_id: str) -> list[Dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM strategy_transitions WHERE strategy_id = ? ORDER BY created_at, transition_id",
                (strategy_id,),
            ).fetchall()
        return [
            {**dict(row), "metrics": json.loads(row["metrics_json"]), "evidence": json.loads(row["evidence_json"])}
            for row in rows
        ]

    def request_transition(
        self,
        strategy_id: str,
        *,
        target_stage: str,
        metrics: Dict[str, Any],
        evidence: Dict[str, Any],
        manual_approved: bool,
        approved_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        strategy = self.get(strategy_id)
        current = strategy["stage"]
        if target_stage not in STAGES:
            raise ValueError("unknown target stage")
        if STAGES.index(target_stage) != STAGES.index(current) + 1:
            raise ValueError("only one-step promotion is allowed")
        failures = self._gate_failures(target_stage, metrics, evidence)
        if not manual_approved or not approved_by:
            failures.append("manual approval required")
        decision = "approved" if not failures else "rejected"
        reason = "all gates passed" if not failures else "; ".join(sorted(set(failures)))
        self._record_transition(strategy_id, current, target_stage, decision, reason, approved_by, metrics, evidence)
        if decision == "approved":
            with self._connection() as connection:
                connection.execute(
                    "UPDATE strategy_versions SET stage = ?, updated_at = ? WHERE strategy_id = ?",
                    (target_stage, _now(), strategy_id),
                )
        return {"decision": decision, "from_stage": current, "to_stage": target_stage, "reason": reason, "strategy": self.get(strategy_id)}

    def auto_demote(self, strategy_id: str, metrics: Dict[str, Any]) -> Dict[str, Any]:
        strategy = self.get(strategy_id)
        current = strategy["stage"]
        if current == "research":
            return {"decision": "unchanged", "stage": current, "reason": "already at research"}
        gate = DEFAULT_GATES[current]
        reasons = []
        if float(metrics.get("max_drawdown_pct", 0.0)) > gate["max_drawdown_pct"]:
            reasons.append("drawdown gate breached")
        if float(metrics.get("slippage_deviation_bps", 0.0)) > gate["max_slippage_deviation_bps"]:
            reasons.append("slippage gate breached")
        if bool(metrics.get("risk_halt", False)):
            reasons.append("risk halt active")
        if not reasons:
            return {"decision": "unchanged", "stage": current, "reason": "demotion gates clear"}
        target = STAGES[STAGES.index(current) - 1]
        reason = "; ".join(reasons)
        self._record_transition(strategy_id, current, target, "auto_demoted", reason, "system", metrics, {})
        with self._connection() as connection:
            connection.execute(
                "UPDATE strategy_versions SET stage = ?, updated_at = ? WHERE strategy_id = ?",
                (target, _now(), strategy_id),
            )
        return {"decision": "auto_demoted", "from_stage": current, "to_stage": target, "reason": reason, "strategy": self.get(strategy_id)}

    def _gate_failures(self, target_stage: str, metrics: Dict[str, Any], evidence: Dict[str, Any]) -> list[str]:
        gate = DEFAULT_GATES[target_stage]
        failures = []
        checks = (
            (float(metrics.get("observation_days", 0)) >= gate["min_observation_days"], "minimum observation days not met"),
            (int(metrics.get("trades", 0)) >= gate["min_trades"], "minimum trades not met"),
            (float(metrics.get("holdout_sharpe", -999)) >= gate["min_holdout_sharpe"], "holdout Sharpe gate not met"),
            (float(metrics.get("max_drawdown_pct", 999)) <= gate["max_drawdown_pct"], "drawdown gate not met"),
            (float(metrics.get("slippage_deviation_bps", 999)) <= gate["max_slippage_deviation_bps"], "slippage gate not met"),
        )
        failures.extend(message for passed, message in checks if not passed)
        failures.extend(f"missing evidence: {key}" for key in REQUIRED_EVIDENCE if not evidence.get(key))
        if target_stage in {"small_live", "live"} and not evidence.get("exchange_validation_passed"):
            failures.append("exchange validation evidence required")
        return failures

    def _record_transition(
        self,
        strategy_id: str,
        from_stage: str,
        to_stage: str,
        decision: str,
        reason: str,
        approved_by: Optional[str],
        metrics: Dict[str, Any],
        evidence: Dict[str, Any],
    ) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO strategy_transitions(
                    transition_id, strategy_id, from_stage, to_stage, decision,
                    reason, approved_by, metrics_json, evidence_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), strategy_id, from_stage, to_stage, decision, reason, approved_by, json.dumps(metrics, sort_keys=True), json.dumps(evidence, sort_keys=True), _now()),
            )

