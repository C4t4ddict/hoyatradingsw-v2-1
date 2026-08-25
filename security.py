"""Encrypted secret storage and recursive sensitive-data redaction."""

from __future__ import annotations

import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from cryptography.fernet import Fernet, InvalidToken


SENSITIVE_KEY = re.compile(r"(?:api.?key|api.?secret|secret|token|password|authorization|private.?key)", re.IGNORECASE)
INLINE_SECRET = re.compile(
    r"(?i)((?:api[_-]?key|api[_-]?secret|secret|token|password|authorization)\s*[:=]\s*)([^\s,;&}\]]+)"
)


def mask_text(value: str) -> str:
    return INLINE_SECRET.sub(lambda match: f"{match.group(1)}***REDACTED***", str(value))


def redact_sensitive(value: Any, key: str = "") -> Any:
    if key and SENSITIVE_KEY.search(str(key)):
        return "***REDACTED***"
    if isinstance(value, dict):
        return {item_key: redact_sensitive(item_value, str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_sensitive(item) for item in value)
    if isinstance(value, str):
        return mask_text(value)
    return value


class SecretVault:
    def __init__(self, path: str = "data/secrets.sqlite3", master_key: Optional[str] = None):
        self.path = path
        key = master_key if master_key is not None else os.getenv("HOYA_MASTER_KEY", "")
        self._fernet = None
        if key:
            try:
                self._fernet = Fernet(key.encode("ascii"))
            except (ValueError, TypeError) as exc:
                raise ValueError("HOYA_MASTER_KEY must be a valid Fernet key") from exc
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._initialize()

    @property
    def configured(self) -> bool:
        return self._fernet is not None

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
                CREATE TABLE IF NOT EXISTS encrypted_secrets (
                    name TEXT PRIMARY KEY,
                    ciphertext BLOB NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def set(self, name: str, value: str) -> None:
        if not self._fernet:
            raise RuntimeError("encrypted secret storage is not configured")
        if not name or not value:
            raise ValueError("name and value are required")
        now = datetime.now(timezone.utc).isoformat()
        ciphertext = self._fernet.encrypt(value.encode("utf-8"))
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO encrypted_secrets VALUES (?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET ciphertext=excluded.ciphertext, updated_at=excluded.updated_at
                """,
                (name, ciphertext, now, now),
            )

    def get(self, name: str) -> Optional[str]:
        if not self._fernet:
            return None
        with self._connection() as connection:
            row = connection.execute("SELECT ciphertext FROM encrypted_secrets WHERE name = ?", (name,)).fetchone()
        if not row:
            return None
        try:
            return self._fernet.decrypt(row["ciphertext"]).decode("utf-8")
        except InvalidToken as exc:
            raise ValueError("secret cannot be decrypted with the configured master key") from exc

    def delete(self, name: str) -> bool:
        with self._connection() as connection:
            cursor = connection.execute("DELETE FROM encrypted_secrets WHERE name = ?", (name,))
        return cursor.rowcount > 0

    def status(self) -> Dict[str, Any]:
        with self._connection() as connection:
            rows = connection.execute("SELECT name, created_at, updated_at FROM encrypted_secrets ORDER BY name").fetchall()
        return {
            "encryption_configured": self.configured,
            "secrets": [{**dict(row), "configured": True} for row in rows],
        }


def get_vault() -> SecretVault:
    return SecretVault(os.getenv("HOYA_SECRET_VAULT_PATH", "data/secrets.sqlite3"))


def resolve_secret(name: str, environment_name: Optional[str] = None) -> str:
    environment_value = os.getenv(environment_name or name, "")
    if environment_value:
        return environment_value
    try:
        return get_vault().get(name) or ""
    except (RuntimeError, ValueError):
        return ""
