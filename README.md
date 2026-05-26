# Interdependence of Ruble and Yuan Borrowing Rates

Research and software pipeline for RUB/CNY borrowing-rate analysis:
- fetches and normalizes multi-source data into SQLite,
- runs statistical and forecasting models,
- builds classical and ML arbitrage signals,
- evaluates strategy and risk backtests,
- exports report-ready artifacts.

## Setup

- Python `>=3.9`
- Install dependencies:

```bash
pip install -r requirements.txt
```

Optional environment variable:
- `FRED_API_KEY` for reliable FRED downloads.

Manual inputs:
- put ChinaBond `.xlsx`/`.csv` files into `data/manual/`.

## Core Pipeline

Run from project root:

```bash
python scripts/run_pipeline.py
python scripts/check_data_status.py
python scripts/run_analysis.py --report analysis_report_latest.txt
python scripts/run_model_comparison.py --curve both --horizon 1 --train-window 60 --export-prefix "project report/tables/tab_6_3_model_comparison"
python scripts/run_signals.py --save-csv data/processed/signals_latest.csv
python scripts/run_ml_signals.py --save-prefix data/processed/ml_signals
python scripts/run_portfolio_backtest.py
python scripts/run_ml_backtest.py
python scripts/run_unified_backtest.py
python scripts/run_advanced_comparison.py --output-prefix "project report/tables/tab_6_4_advanced_methods"
python scripts/export_report_data.py --with-model-comparison --with-portfolio-backtest --with-advanced-comparison --with-ml-signals --with-financial-gains
```

Main outputs:
- `bond_rates_database.db`
- `data/processed/*.csv`
- `project report/tables/*`
- `project report/graphics/*`

## Weekly Update

```bash
python scripts/run_weekly_update.py
python scripts/check_data_status.py
```

## Notebooks

Notebook flow in `notebooks/`:
- `00_cache_and_run_control.ipynb` (artifact checks + optional full rerun)
- `01_data_and_statistics_demo.ipynb`
- `02_forecasting_and_spreads_demo.ipynb`
- `03_signals_demo_classical_vs_ml.ipynb`
- `04_portfolio_and_risk_demo.ipynb`
- `05_profit_demo.ipynb`
- `99_full_pipeline_dashboard.ipynb`

`00_cache_and_run_control.ipynb` writes `data/processed/demo_run_manifest.json` and triggers full script chain only when required artifacts are missing.
