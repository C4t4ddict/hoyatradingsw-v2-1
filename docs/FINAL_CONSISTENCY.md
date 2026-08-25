# Final consistency audit

This audit closes the remaining desktop and engine consistency gaps while keeping mobile support and real-exchange connection testing out of scope.

## Execution behavior

- Paper portfolio execution remains fixed to confirmed 4-hour BTC/ETH/SOL spot candles with long/cash exposure and 1x leverage.
- Advisory ML output never opens a position while its validated decision is neutral.
- Two consecutive realized losses start one 24-hour cooldown. The same loss sequence cannot continuously re-arm the cooldown after it expires.
- Paper state writes use a same-directory temporary file, `fsync`, and atomic replacement so an interrupted write preserves the last valid state.
- A process lock prevents a second Paper worker from owning the same session.

## API and desktop UI

- Overview consistently exposes the advisory signal as `ml_signal`.
- Risk responses expose the fields rendered by the desktop page, including daily loss limits, concurrent-position limits, leverage, dry-run state, and Live-control state.
- Account data is not fetched automatically. Private data requires an explicit authenticated request, and an unqueried value is shown as unavailable rather than zero.
- Paper controls expose only settings supported by the execution engine; advisory signals are visibly separated from order decisions.

## Verification boundary

Automated unit/integration tests, the production frontend build, API smoke checks, and desktop browser QA are required. Mobile viewport QA and requests to a real exchange account are deliberately excluded.
