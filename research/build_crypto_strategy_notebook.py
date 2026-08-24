from pathlib import Path

import nbformat as nbf
from nbclient import NotebookClient


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "research" / "output"
NOTEBOOK = ROOT / "research" / "crypto_strategy_backtest.ipynb"


def build_notebook():
    nb = nbf.v4.new_notebook()
    nb["metadata"]["kernelspec"] = {
        "display_name": "Python 3",
        "language": "python",
        "name": "python3",
    }
    nb["metadata"]["language_info"] = {"name": "python", "version": "3.12"}

    nb["cells"] = [
        nbf.v4.new_markdown_cell(
            """# Crypto automatic-investment strategy study

## tl;dr

- Source: Binance USD-M public 4-hour OHLCV and funding history for BTC, ETH, and SOL. Exact coverage and freshness are reported in the generated source-quality table below.
- The most consistent candidate is **long/cash momentum with volatility targeting**. It materially reduces drawdown versus buy-and-hold in this sample while retaining positive risk-adjusted returns.
- The paper-trading candidate uses BTC/ETH/SOL base weights of 60/30/10, no leverage, and a conservative 20%–25% volatility target.
- Current regime and exposure must be read from the generated market snapshot and risk-target table; they change whenever the data cache is refreshed.
- Do not deploy the repository's current `ensemble_regime` to live capital yet: its regime slicing creates discontinuous synthetic candles, entries use the signal bar's close, and funding direction is wrong for shorts.
"""
        ),
        nbf.v4.new_markdown_cell(
            """## Context & Methods

Decision: identify strategies suitable for staged automatic crypto investing, not maximize historical return.

### Key Assumptions

- Signals use information available at a 4-hour bar close and become active at the next bar open.
- Exposure is capped at 1.0x; no borrowed leverage is used.
- Spot-style strategies pay 13 bps per 1x turnover; futures strategies pay 8 bps plus actual Binance funding with the correct long/short sign.
- Indicators use day-equivalent windows: 50/200-day EMA, 55/20-day Donchian, 90-day momentum, and 30-day realized volatility.
- The first seven months are warm-up; reported returns begin 2021-08-01 UTC.
- Sources: [Binance public market-data documentation](https://developers.binance.com/en/docs/products/spot/rest-api) and [USD-M futures documentation](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/Introduction).
"""
        ),
        nbf.v4.new_code_cell(
            """from pathlib import Path
import json
import pandas as pd
from IPython.display import Image, Markdown, display
from research.crypto_strategy_backtest import run_study

ROOT = Path.cwd()
OUTPUT = ROOT / 'research' / 'output'
study = run_study(refresh=False)
pd.set_option('display.max_columns', 30)
pd.set_option('display.width', 160)
"""
        ),
        nbf.v4.new_markdown_cell("## Data"),
        nbf.v4.new_code_cell(
            """display(Markdown('### Source quality'))
display(study['sources'])
display(Markdown('### Current market snapshot'))
display(study['snapshot'].round(3))
"""
        ),
        nbf.v4.new_markdown_cell("## Results"),
        nbf.v4.new_code_cell(
            """display(Markdown('### Cross-asset strategy ranking'))
display(study['aggregate'].round(3))
display(Markdown('### Portfolio comparison'))
cols = ['portfolio','cagr_pct','sharpe','sortino','max_drawdown_pct','return_2024_current_pct','return_2025_current_pct']
display(study['portfolio_summary'][cols].round(2))
display(Markdown('### Risk-target choices for BTC/ETH/SOL 60/30/10'))
cols = ['target_vol_pct','cagr_pct','sharpe','max_drawdown_pct','return_2024_current_pct','return_2025_current_pct','current_net_exposure_pct']
display(study['risk_scenarios'][cols].round(2))
"""
        ),
        nbf.v4.new_code_cell(
            """display(Image(filename=str(OUTPUT / 'btc_equity_curves.png')))
display(Image(filename=str(OUTPUT / 'portfolio_equity_curves.png')))
display(Image(filename=str(OUTPUT / 'strategy_cagr_comparison.png')))
"""
        ),
        nbf.v4.new_markdown_cell("## Robustness & Holdout"),
        nbf.v4.new_code_cell(
            """robustness = study['robustness']
robustness_summary = robustness.groupby(['asset','family']).agg(
    configs=('params','size'),
    positive_holdout_pct=('holdout_return_pct', lambda values: (values > 0).mean() * 100),
    median_holdout_pct=('holdout_return_pct','median'),
    worst_holdout_pct=('holdout_return_pct','min'),
    best_holdout_pct=('holdout_return_pct','max'),
).round(2)
display(robustness_summary)
display(Markdown('### Parameters selected on 2021–2023, evaluated on 2024–current'))
display(study['walk_forward'][['asset','family','params','train_return_pct','holdout_return_pct','full_sharpe','full_max_drawdown_pct']].round(2))
display(Image(filename=str(OUTPUT / 'parameter_robustness_holdout.png')))
display(Image(filename=str(OUTPUT / 'btc_cost_sensitivity.png')))
"""
        ),
        nbf.v4.new_markdown_cell(
            """## Validation Report

### Overall Assessment: Share with caveats

### Methodology Review

The independent harness avoids same-bar close execution, includes turnover costs, applies actual funding with correct direction, caps exposure at 1.0x, checks three assets, separates 2021–2023 selection from 2024-current holdout, and tests nearby parameters and costs.

### Issues Found

1. **High — current repository ensemble:** regime-filtered candles are concatenated and backtested as if time were continuous. The resulting return is not decision-grade.
2. **High — current repository fills:** a signal calculated with the current close is filled at that same close. This is optimistic unless a later executable quote is used.
3. **High — current repository funding:** positive funding is subtracted from shorts, although positive funding is paid by longs to shorts.
4. **Medium — this study:** 4-hour OHLCV cannot model order-book depth, partial fills, outages, or gap-dependent slippage.
5. **Medium — this study:** USD-M perpetual OHLCV is used as a price proxy for spot strategies; funding is excluded for those spot-style variants.

### Calculation Spot-Checks

- Source completeness: verified from the generated source-quality table; review row counts, timestamps, duplicates, and null cells after every refresh.
- Execution timing: verified — signal is shifted one bar before returns are applied.
- Funding sign: verified — net return subtracts `position × funding_rate`, so shorts receive positive funding.
- Cost sensitivity: verified across 4, 8, 13, and 20 bps per turnover unit.
- Holdout: verified using 2024-current after parameter selection on 2021–2023.

### Required Caveats

- Backtests estimate behavior under assumptions; they do not prove future profitability.
- Paper trading with live bid/ask and exchange filters is required before any capital allocation.
- Account-level fee tier, taxes, delisting, and exchange/API outage behavior are not included.
"""
        ),
        nbf.v4.new_markdown_cell(
            """## Takeaways

1. **Adopt for paper trading:** long/cash 90-day momentum + 200-day trend filter + 20%–25% volatility target, using BTC/ETH/SOL base weights of 60/30/10 and no leverage.
2. **Keep as benchmark:** 50/200-day long/cash trend. It performed well on BTC but was inconsistent on ETH and SOL and allowed materially deeper drawdowns.
3. **Reject for now:** unrestricted long/short EMA and Donchian futures variants. Cross-asset holdout losses and 79%–91% worst drawdowns are unacceptable for unattended automation.
4. **Reject as inactive:** the tested RSI pullback rule produced no trades, so it provides no evidence of usefulness.
5. **Current regime:** allow partial long exposure, but do not treat the rebound as a confirmed structural bull market until the 50-day trend catches the 200-day trend. Positive funding also favors spot-style exposure over paying perpetual funding for an aggressive long.
"""
        ),
    ]
    return nb


if __name__ == "__main__":
    notebook = build_notebook()
    NOTEBOOK.parent.mkdir(parents=True, exist_ok=True)
    nbf.write(notebook, NOTEBOOK)
    client = NotebookClient(notebook, timeout=600, kernel_name="python3", resources={"metadata": {"path": str(ROOT)}})
    client.execute()
    nbf.write(notebook, NOTEBOOK)
    print(NOTEBOOK)
