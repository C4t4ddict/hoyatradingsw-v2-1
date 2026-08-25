# Signal quality and market regime

News and machine-learning outputs are advisory until their realized outcomes are validated. The runtime therefore stores each prediction and subsequent return, calculates Brier score, directional accuracy and information coefficient, and assigns a zero decision weight until the configured minimum observation and quality thresholds pass.

The policy replaces fixed Intel/ML weights with scores derived from validated performance. Syndicated headlines are deduplicated before aggregation, and source trust is adjusted only after at least ten realized observations with Beta shrinkage.

Market regime classification is causal: trend, realized volatility, liquidity, funding and cross-asset correlation use only data at or before the decision timestamp. It changes the position-size multiplier, not the selected strategy. Bear, high-volatility, thin-liquidity and overheated-funding states can only reduce exposure.

API endpoints:

- `GET /api/signals/quality`: aggregate and per-horizon quality gates plus source reliability.
- `POST /api/signals/outcomes`: idempotently record a realized observation using `observation_id`.
- `POST /api/signals/regime`: classify a supplied causal market window.

The Paper and Intel pages expose observation counts, Brier scores, dynamic weights, regime and position multiplier so a neutral or reduced decision is explainable.
