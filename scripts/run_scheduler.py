"""
Scheduler - Automated data updates
==================================

This script sets up automatic data updates using APScheduler.

Usage:
    python scripts/run_scheduler.py              # Start scheduler (runs in foreground)
    python scripts/run_scheduler.py --once       # Run once and exit
    python scripts/run_scheduler.py --status     # Check last update status
"""

import argparse
import logging
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from src.pipeline import DataPipeline
from src.database import DatabaseManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scheduler.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def run_daily_update():
    """Run daily data update job."""
    logger.info("Starting daily update...")
    try:
        pipeline = DataPipeline()
        pipeline.run_quick_update()
        logger.info("Daily update completed successfully")
    except Exception as e:
        logger.error(f"Daily update failed: {e}")


def run_monthly_update():
    """Run full monthly data update job."""
    logger.info("Starting monthly full update...")
    try:
        pipeline = DataPipeline()
        pipeline.run_full_update()
        logger.info("Monthly update completed successfully")
    except Exception as e:
        logger.error(f"Monthly update failed: {e}")


def start_scheduler():
    """Start the scheduler with configured jobs."""
    scheduler = BlockingScheduler()
    
    # Daily update at 9:00 AM (local time)
    scheduler.add_job(
        run_daily_update,
        CronTrigger(hour=9, minute=0),
        id='daily_update',
        name='Daily data update',
        replace_existing=True
    )
    
    # Full monthly update on 1st of each month at 10:00 AM
    scheduler.add_job(
        run_monthly_update,
        CronTrigger(day=1, hour=10, minute=0),
        id='monthly_update',
        name='Monthly full update',
        replace_existing=True
    )
    
    logger.info("Scheduler started with the following jobs:")
    for job in scheduler.get_jobs():
        logger.info(f"  - {job.name}: {job.trigger}")
    
    print("\n" + "="*60)
    print("SCHEDULER STARTED")
    print("="*60)
    print("Jobs scheduled:")
    print("  1. Daily update: Every day at 9:00 AM")
    print("  2. Monthly update: 1st of each month at 10:00 AM")
    print("\nPress Ctrl+C to stop")
    print("="*60 + "\n")
    
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped by user")


def check_status():
    """Check the status of last updates."""
    db = DatabaseManager()
    
    print("\n" + "="*60)
    print("UPDATE STATUS")
    print("="*60)
    
    # Get update log
    log = db.get_update_log(limit=20)
    
    if log.empty:
        print("No updates recorded yet.")
        return
    
    # Show recent updates
    print("\nRecent updates:")
    print("-"*60)
    
    for _, row in log.iterrows():
        print(f"  {row['update_time']}: {row['table_name']} ({row['rows_added']} rows)")
    
    # Show table metadata
    print("\n" + "-"*60)
    print("Tables in database:")
    print("-"*60)
    
    metadata = db.get_metadata()
    for _, row in metadata.iterrows():
        print(f"  {row['table_name']}: {row.get('last_updated', 'N/A')}")
    
    print("="*60 + "\n")


def run_once():
    """Run update once and exit."""
    logger.info("Running one-time update...")
    pipeline = DataPipeline()
    pipeline.run_full_update()
    logger.info("One-time update completed")


def main():
    parser = argparse.ArgumentParser(description='Data Update Scheduler')
    parser.add_argument('--once', action='store_true', help='Run once and exit')
    parser.add_argument('--status', action='store_true', help='Check update status')
    parser.add_argument('--quick', action='store_true', help='Run quick update once')
    
    args = parser.parse_args()
    
    if args.status:
        check_status()
    elif args.once:
        run_once()
    elif args.quick:
        logger.info("Running quick update...")
        pipeline = DataPipeline()
        pipeline.run_quick_update()
    else:
        start_scheduler()


if __name__ == "__main__":
    main()
