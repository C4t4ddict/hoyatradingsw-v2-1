# Signal quality and market regime

News and machine-learning outputs are advisory until their realized outcomes are validated. The runtime therefore stores each prediction and subsequent return, calculates Brier score, directional accuracy and information coefficient, and assigns a zero decision weight until the configured minimum observation and quality thresholds pass.

The policy replaces fixed Intel/ML weights with scores derived from validated performance. Syndicated headlines are deduplicated before aggregation, and source trust is adjusted only after at least ten realized observations with Beta shrinkage.

Market regime classification is causal: trend, realized volatility, liquidity, funding and cross-asset correlation use only data at or before the decision timestamp. It changes the position-size multiplier, not the selected strategy. Bear, high-volatility, thin-liquidity and overheated-funding states can only reduce exposure.

API endpoints:

- `GET /api/signals/quality`: aggregate and per-horizon quality gates plus source reliability.
- `POST /api/signals/outcomes`: idempotently record a realized observation using `observation_id`.
- `POST /api/signals/regime`: classify a supplied causal market window.
- `GET /api/ml/readiness`: audit dataset completeness, temporal leakage, label balance and validated model coverage.

The Paper and Intel pages expose observation counts, Brier scores, dynamic weights, regime, position multiplier and ML readiness blockers so a neutral or reduced decision is explainable. Bidirectional models are ignored unless their bundle contains validation metadata produced by the chronological, purged holdout trainer.

Historical market-pattern learning is a separate ML stream from news-event learning. It uses completed 4-hour public OHLCV bars, next-open entry labels, a newest-period holdout and a 24-hour purge gap. The recent 40% is also evaluated in four expanding walk-forward folds, with at least three passes required. Promotion requires classification improvement over the training-prior baseline and positive cost-adjusted holdout economics. Offline validation makes the model eligible for observation, while live `pattern` outcomes must still pass the signal-quality gate before the model receives decision weight.
