# Strategy validation and approval evidence

Strategies must be selected with training/validation data and evaluated once on
an untouched final holdout. The validation utility produces evidence for the
stage gates implemented by `strategy_governance.py`; it never promotes a
strategy automatically.

## Required input

The CSV must be ordered in time and contain decimal period returns:

- `strategy_return`
- `benchmark_return`
- `turnover` (absolute fraction of NAV traded)
- optional `funding_return` (signed portfolio return)
- optional additional `*_return` strategy columns for correlation analysis

## Run

```powershell
.\.venv\Scripts\python.exe strategy_validation.py data\validation_returns.csv `
  --output-dir research\output\validation --seed 42
```

```bash
./.venv/bin/python strategy_validation.py data/validation_returns.csv \
  --output-dir research/output/validation --seed 42
```

## Outputs

- `validation_report.json`: headline, benchmark, Monte Carlo, and methodology
- `purged_walk_forward.csv`: train/test metrics with purge and embargo gaps
- `regime_performance.csv`: causal bull/bear/sideways and volatility results
- `cost_stress.csv`: fee/slippage turnover stress plus signed funding
- `strategy_correlation.csv`: strategy return correlation matrix

Market regimes use trailing windows and fixed thresholds. Full-sample quantiles
are intentionally avoided because they leak future distribution information.
Monte Carlo output is reproducible from the recorded seed. Small Live and Live
approval still require external exchange-validation evidence, which this local
suite does not create.
