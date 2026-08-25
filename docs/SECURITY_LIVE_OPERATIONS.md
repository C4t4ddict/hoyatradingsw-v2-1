# Security and Live operations

## Encrypted secrets

Exchange and notification credentials can be stored in the local encrypted vault. Values are encrypted with Fernet before SQLite persistence. The encryption key must be supplied separately in `HOYA_MASTER_KEY`; the database is not self-decrypting.

The API exposes only secret names and timestamps. There is no secret-read endpoint. Mutations require `X-Settings-Token`, backed by `SETTINGS_TOKEN`. Exchange and Telegram clients prefer their existing environment variables and otherwise resolve the encrypted vault value.

Structured logs, immutable ledger payloads, operational alert details and common exception messages are recursively redacted for API keys, secrets, tokens, passwords and authorization fields.

## Live fail-closed control

`DRY_RUN=false` alone cannot authorize an order. Live execution additionally requires:

1. a first explicit confirmation that issues a single-use challenge whose hash—not token—is stored;
2. a second explicit confirmation within five minutes;
3. an unexpired Live window, at most 24 hours;
4. notional at or below the persistent `max_order_usdt` setting;
5. the existing strategy tag, risk, concurrency and market filters.

The same Live authorization blocks futures leverage, margin-mode and position-mode mutations. Disable is immediate, and expiry automatically returns the system to Paper. Every challenge, activation, expiry, disable and cap change is recorded in settings history.

## API and desktop UI

- `GET /api/security/status` returns vault metadata and safe Live status.
- `POST /api/security/secrets` and `DELETE /api/security/secrets/{name}` manage encrypted values without echoing them.
- `GET /api/live/status` returns the control state and settings history.
- `POST /api/live/challenge`, `/api/live/confirm`, `/api/live/disable`, and `/api/live/order-cap` implement the guarded transition.
- `/operations` displays worker health, data freshness, ledger integrity, alerts, audit history, encrypted-secret status, backups/reports and Live controls.

Ledger backup/export/restore and daily-report delivery are also settings-token protected. No actual-exchange integration test is performed by this feature.
