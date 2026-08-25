import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet
from fastapi import HTTPException

from backend.app.routes.security import SecretWriteRequest, api_security_set_secret, api_security_status
from live_controls import FIRST_CONFIRMATION, SECOND_CONFIRMATION, LiveControlStore
from operations import OperationalStore
from paper_ledger import TradingLedger
from performance import log_trade
from security import SecretVault, redact_sensitive
from webhook_server import _authorize_live_order
from webhook_server import FuturesConfigRequest, FuturesPositionModeRequest, futures_configure, futures_position_mode


UTC = timezone.utc


class SecretSecurityTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.key = Fernet.generate_key().decode("ascii")

    def tearDown(self):
        self.directory.cleanup()

    def test_vault_encrypts_at_rest_and_status_never_returns_value(self):
        secret = "super-secret-api-value"
        path = self.root / "vault.sqlite3"
        vault = SecretVault(str(path), self.key)
        vault.set("API_SECRET", secret)

        self.assertEqual(vault.get("API_SECRET"), secret)
        self.assertNotIn(secret, path.read_bytes().decode("latin-1"))
        status = vault.status()
        self.assertNotIn(secret, json.dumps(status))
        self.assertEqual(status["secrets"][0]["name"], "API_SECRET")

    def test_sensitive_values_are_redacted_from_logs_ledger_and_alerts(self):
        secret = "never-write-this"
        performance_path = self.root / "performance.jsonl"
        log_trade({"api_key": secret, "error": f"API_SECRET={secret}"}, str(performance_path))
        self.assertNotIn(secret, performance_path.read_text(encoding="utf-8"))

        ledger_path = self.root / "ledger.sqlite3"
        ledger = TradingLedger(str(ledger_path))
        ledger.append_event(
            event_id="one", session_id="s1", event_type="config_changed",
            payload={"config": {"API_KEY": secret}, "message": f"token={secret}"},
        )
        self.assertNotIn(secret, json.dumps(ledger.list_events()))

        operations = OperationalStore(str(self.root / "operations.sqlite3"))
        operations.raise_alert(
            dedup_key="secret-test", category="worker", severity="critical",
            message=f"API_KEY={secret}", details={"authorization": secret},
        )
        self.assertNotIn(secret, json.dumps(operations.list_alerts()))

    def test_secret_write_api_requires_settings_token_and_never_echoes_value(self):
        vault_path = str(self.root / "api-vault.sqlite3")
        environment = {
            "SETTINGS_TOKEN": "settings-auth-token",
            "HOYA_MASTER_KEY": self.key,
            "HOYA_SECRET_VAULT_PATH": vault_path,
            "LIVE_CONTROL_DB_PATH": str(self.root / "live.sqlite3"),
        }
        with patch.dict(os.environ, environment, clear=False):
            with self.assertRaises(HTTPException) as denied:
                api_security_set_secret(SecretWriteRequest(name="API_KEY", value="top-secret"), None)
            accepted = api_security_set_secret(
                SecretWriteRequest(name="API_KEY", value="top-secret"), "settings-auth-token",
            )
            status = api_security_status()

        self.assertEqual(denied.exception.status_code, 401)
        self.assertNotIn("top-secret", json.dumps(accepted))
        self.assertNotIn("top-secret", json.dumps(status))
        self.assertIn("API_KEY", json.dumps(status))


class LiveControlTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "live.sqlite3"
        self.store = LiveControlStore(str(self.path), max_cap_usdt=1000.0)
        self.now = datetime(2026, 1, 1, 12, tzinfo=UTC)

    def tearDown(self):
        self.directory.cleanup()

    def test_live_requires_two_confirmations_and_token_is_hashed(self):
        with self.assertRaises(ValueError):
            self.store.request_live_challenge("yes", now=self.now)
        challenge = self.store.request_live_challenge(FIRST_CONFIRMATION, now=self.now)

        with closing(sqlite3.connect(self.path)) as connection:
            stored_hash = connection.execute("SELECT challenge_hash FROM live_control_state").fetchone()[0]
        self.assertNotEqual(stored_hash, challenge["challenge_token"])
        self.assertNotIn(challenge["challenge_token"], self.path.read_bytes().decode("latin-1"))

        with self.assertRaises(ValueError):
            self.store.confirm_live(challenge["challenge_token"], "yes", now=self.now)
        enabled = self.store.confirm_live(
            challenge["challenge_token"], SECOND_CONFIRMATION, duration_minutes=60, now=self.now,
        )
        self.assertTrue(enabled["live_enabled"])
        self.assertEqual(enabled["mode"], "live")

    def test_order_cap_and_expiry_fail_closed_with_history(self):
        challenge = self.store.request_live_challenge(FIRST_CONFIRMATION, now=self.now)
        self.store.confirm_live(challenge["challenge_token"], SECOND_CONFIRMATION, now=self.now)
        self.store.set_order_cap(50.0)

        self.assertTrue(self.store.authorize_order(49.0, self.now)["allowed"])
        over_cap = self.store.authorize_order(51.0, self.now)
        self.assertFalse(over_cap["allowed"])
        self.assertIn("max_order_usdt_exceeded", over_cap["reasons"])

        expired = self.store.authorize_order(10.0, self.now + timedelta(hours=5))
        self.assertFalse(expired["allowed"])
        self.assertIn("live_not_double_confirmed", expired["reasons"])
        actions = {row["action"] for row in self.store.history()}
        self.assertTrue({"live_enabled", "order_cap_changed", "live_expired"}.issubset(actions))

    @patch("webhook_server.get_live_control_store")
    def test_webhook_live_guard_is_bypassed_only_for_dry_run(self, get_store):
        get_store.return_value.authorize_order.return_value = {
            "allowed": False, "reasons": ["live_not_double_confirmed"], "control": {"mode": "paper"},
        }
        self.assertTrue(_authorize_live_order(100.0, True)["allowed"])
        self.assertFalse(_authorize_live_order(100.0, False)["allowed"])
        get_store.return_value.authorize_order.assert_called_once_with(100.0)

    @patch("webhook_server._get_exchange")
    @patch("webhook_server._authorize_live_order")
    def test_live_account_configuration_is_blocked_before_exchange_call(self, authorize, get_exchange):
        authorize.return_value = {
            "allowed": False, "reasons": ["live_not_double_confirmed"], "control": {"mode": "paper"},
        }
        with patch("webhook_server.DRY_RUN", False), patch("webhook_server.WEBHOOK_TOKEN", ""):
            leverage = futures_configure(FuturesConfigRequest(symbol="BTC/USDT:USDT", leverage=2, margin_mode="isolated"))
            position = futures_position_mode(FuturesPositionModeRequest(hedged=False))

        self.assertTrue(leverage["ignored"])
        self.assertTrue(position["ignored"])
        get_exchange.assert_not_called()


if __name__ == "__main__":
    unittest.main()
