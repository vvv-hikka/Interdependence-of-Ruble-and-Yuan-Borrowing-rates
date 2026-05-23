"""
Run weekly data update — fetch and persist all weekly-frequency series.

Usage:
    python scripts/run_weekly_update.py                    # Full history
    python scripts/run_weekly_update.py --test             # Dry run (no DB writes)
    python scripts/run_weekly_update.py --start-date 2022-01-01
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.pipeline.data_pipeline import DataPipeline


def main():
    parser = argparse.ArgumentParser(description='Weekly data update')
    parser.add_argument('--test', action='store_true', help='Test mode (no database writes)')
    parser.add_argument('--start-date', type=str, help='Start date (YYYY-MM-DD)')
    args = parser.parse_args()

    pipeline = DataPipeline(test_mode=args.test)
    pipeline.run_weekly_update(start_date=args.start_date)


if __name__ == "__main__":
    main()
