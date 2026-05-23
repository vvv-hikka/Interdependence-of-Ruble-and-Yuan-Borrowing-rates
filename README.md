# Interdependence of Ruble and Yuan Borrowing Rates

Reproducible research pipeline for RUB/CNY rates:
- fetch and normalize multi-source data into SQLite,
- run statistical and forecasting analyses,
- generate arbitrage signals,
- export report-ready tables/figures,
- run a constrained portfolio/risk benchmark.

## Environment

- Python `>=3.9`
- Windows: `venv\Scripts\activate`
- Linux/macOS: `source venv/bin/activate`

Install dependencies:

```bash
pip install -r requirements.txt
```

Optional but recommended:
- set `FRED_API_KEY` for stable FRED access.

Manual ChinaBond files:
- place `.xlsx` / `.csv` files into `data/manual/`.

## Canonical Monthly Run Path

From project root:

```bash
python scripts/run_pipeline.py
python scripts/check_data_status.py
python scripts/run_analysis.py --report analysis_report_latest.txt
python scripts/run_yield_forecasting.py
python scripts/run_model_comparison.py --curve both --horizon 1 --train-window 60 --export-prefix "project report/tables/tab_6_3_model_comparison"
python scripts/run_signals.py --save-csv data/processed/signals_latest.csv
python scripts/run_ml_signals.py --save-prefix data/processed/ml_signals
python scripts/run_ml_backtest.py
python scripts/run_advanced_comparison.py --output-prefix "project report/tables/tab_6_4_advanced_methods"
python scripts/export_report_data.py --with-model-comparison --with-portfolio-backtest --with-advanced-comparison --with-ml-signals
```

Primary generated artifacts:
- DB: `bond_rates_database.db`
- report tables: `project report/tables/`
- report figures: `project report/graphics/`
- signals: `data/processed/signals_latest*.csv`
- ML signals: `data/processed/ml_signals*.csv`
- portfolio summary: `data/processed/portfolio_backtest_summary.csv`
- ML backtest summary: `data/processed/ml_backtest_summary.csv`
- advanced methods: `project report/tables/tab_6_4_advanced_methods.*`

## Weekly Update Path

```bash
python scripts/run_weekly_update.py
python scripts/check_data_status.py
```

Weekly tables feed higher-frequency signal diagnostics and CIP workflows.

## Notes on Scope

- Implemented baseline forecasting: NS, DNS, VAR, RW (+ optional PCA in comparison script).
- AER module provides a minimal reproducible proxy in `src/forecasting/aer.py` (not full HJM neural filter).
- Regime DNS provides macro-threshold two-regime split in `src/forecasting/regime_dns.py`.
- Portfolio layer is a constrained benchmark module, intended as the bridge to full optimization.

## Notebook Demo Suite

The notebook suite is additive and does not replace:
- `statistical_analysis.ipynb`
- `yield_forecasting.ipynb`

New demo notebooks live under `notebooks/`:

1. `00_cache_and_run_control.ipynb`  
   - checks cache tiers and required artifacts  
   - runs full script chain only when artifacts are missing  
   - writes `data/processed/demo_run_manifest.json`
2. `01_data_and_statistics_demo.ipynb`
3. `02_forecasting_and_spreads_demo.ipynb`
4. `03_signals_demo_classical_vs_ml.ipynb`
5. `04_portfolio_and_risk_demo.ipynb`
6. `99_full_pipeline_dashboard.ipynb`

### Runtime policy

- **Fast demo mode**: if Tier-2 artifacts exist, notebooks load CSV/PNG/TEX only.
- **Full mode fallback**: if required artifacts are missing, notebook `00` executes:
  - `scripts/run_pipeline.py`
  - `scripts/check_data_status.py`
  - `scripts/run_model_comparison.py --curve both --horizon 1 --train-window 60 --export-prefix "project report/tables/tab_6_3_model_comparison"`
  - `scripts/run_signals.py --save-csv data/processed/signals_latest.csv`
  - `scripts/run_ml_signals.py --save-prefix data/processed/ml_signals`
  - `scripts/run_ml_backtest.py`
  - `scripts/run_portfolio_backtest.py`
  - `scripts/run_advanced_comparison.py --output-prefix "project report/tables/tab_6_4_advanced_methods"`
  - `scripts/export_report_data.py --with-model-comparison --with-portfolio-backtest --with-advanced-comparison --with-ml-signals`
