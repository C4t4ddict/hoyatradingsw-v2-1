# Backtester execution-model migration

Issue #23 changes the legacy backtester from same-close execution to a
reproducible next-bar model.

## Behavior changes

- Signals calculated from bar `t` execute at bar `t+1` open.
- Signal exits also execute at the following open; intrabar stops, targets, and
  liquidation checks use the active bar's high/low.
- Maker fee, taker fee, and adverse slippage are independent parameters. The
  legacy `fee_pct` remains the default for both fee types.
- Positive funding is a cost for longs and a credit for shorts. Funding events
  are applied only while the position is open.
- The equity curve is mark-to-market while a position is open. Any remaining
  position is closed at the final close with the reason `end_of_test`.
- The ensemble runs on one continuous candle sequence. It selects the active
  strategy per timestamp instead of concatenating discontinuous regime slices.

## Expected result differences

Historical outputs can show later entries and exits, lower performance after
explicit costs, opposite funding impact for shorts, and different ensemble
trade counts. These differences are intentional. Results generated before this
migration must not be compared as if they used the same execution model.

## Compatibility

Callers that only pass `fee_pct` remain supported. New studies should set
`maker_fee_pct`, `taker_fee_pct`, and `slippage_pct` explicitly and record the
returned `fee_model` metadata.
