"""
Run data pipeline - fetch and save bond rates and macroeconomic data.

Usage:
    python scripts/run_pipeline.py                    # Full update
    python scripts/run_pipeline.py --quick            # Quick update (last 3 months)
    python scripts/run_pipeline.py --test             # Test mode (no database writes)
"""

from src.pipeline.data_pipeline import main

if __name__ == "__main__":
    main()
