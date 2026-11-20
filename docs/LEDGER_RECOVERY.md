# Trading ledger recovery

Paper execution events are stored in an append-only SQLite ledger. Each event contains the previous event hash for the same session and environment, its own SHA-256 hash, the strategy version and the code revision. `verify_integrity()` checks both SQLite integrity and the event chain.

Session checkpoints persist the event-engine portfolio, pending orders, metrics and configuration hash. Resume reconciles the JSON runtime state against the ledger. A missing or stale pending-order snapshot is reconstructed from durable `order_pending`, `order_filled` and `order_cancelled` events. A failed hash check keeps the session paused with `ledger_integrity_hold`.

Operations endpoints:

- `GET /api/paper/audit` includes ledger integrity and reconciliation state.
- `POST /api/paper/ledger/backup` creates a consistent SQLite online backup.
- `POST /api/paper/ledger/export` creates a CSV audit export.
- `POST /api/paper/ledger/restore` accepts a backup filename from the configured backup directory and only runs while Paper is paused. A pre-restore rollback backup is created automatically.

Configuration:

- `TRADING_LEDGER_PATH` selects the active SQLite ledger.
- `TRADING_LEDGER_BACKUP_DIR` selects the backup/export directory.
- `HOYA_CODE_VERSION` optionally overrides automatic Git revision detection.
