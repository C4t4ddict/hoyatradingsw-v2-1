# Operations alerts and daily reports

Operational alerts are persisted in SQLite rather than existing only as outbound Telegram messages. Each alert has a category, severity, stable deduplication key, lifecycle status, occurrence count and notification timestamps.

Repeated observations update the active alert but do not notify again until `OPERATIONS_ALERT_COOLDOWN_SEC` expires. A healthy observation resolves worker, data-delay, state-consistency and ledger-integrity alerts. Historical order and fill events are marked as observed in the Paper checkpoint so polling does not create false recurrences.

Monitored conditions include:

- worker down or worker update exception;
- delayed Paper market-data update;
- runtime state consistency or ledger integrity failure;
- rejected orders, fills and active risk blocks.

API endpoints:

- `GET /api/operations`: health snapshot, active counts, full alert history and Paper audit state.
- `GET /api/operations/daily-report`: generate and persist the current UTC-day report.
- `POST /api/operations/daily-report/send`: generate the report and send it to the configured Paper Telegram channel. It is marked notified only when delivery succeeds.

The daily report derives orders, fills, rejections, realized PnL and win rate from immutable ledger events, scoped to a single UTC date and environment.
