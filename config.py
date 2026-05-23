"""
Configuration file for data fetchers
=====================================

Add your API keys here.

API Key Sources:
- FRED: https://fred.stlouisfed.org/docs/api/api_key.html (free)
- Tinkoff: https://www.tinkoff.ru/invest/open-api/ (requires account)
- Cbonds: https://cbonds.ru/api/ (paid, demo available)
"""

import os
from pathlib import Path

# =============================================================================
# PROJECT PATHS
# =============================================================================

PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
MANUAL_DATA_DIR = DATA_DIR / "manual"

# Create directories if they don't exist
for dir_path in [DATA_DIR, RAW_DATA_DIR, PROCESSED_DATA_DIR, MANUAL_DATA_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)

# =============================================================================
# API KEYS
# =============================================================================

# Environment variables take precedence over hardcoded values
API_KEYS = {
    # FRED API (free, recommended)
    # Get key at: https://fred.stlouisfed.org/docs/api/api_key.html
    'fred': os.environ.get('FRED_API_KEY', None),
    
    # Tinkoff Invest API (requires brokerage account)
    'tinkoff': os.environ.get('TINKOFF_API_KEY', None),
    
    # BCS API (requires brokerage account)  
    'bcs': os.environ.get('BCS_API_KEY', None),
    
    # Cbonds API (paid service, 7-day demo available)
    'cbonds': os.environ.get('CBONDS_API_KEY', None),
}

# =============================================================================
# DATA SETTINGS
# =============================================================================

# Default date range for data fetching
DEFAULT_START_DATE = "2015-01-01"

# Request timeout in seconds
REQUEST_TIMEOUT = 60

# Rate limiting (seconds between requests)
RATE_LIMIT_DELAY = 0.1

# =============================================================================
# OFZ BENCHMARK BONDS
# =============================================================================

# Updated list of OFZ benchmark bonds by maturity
# These are commonly used bonds for yield curve construction
OFZ_BENCHMARKS = {
    "1Y": ["SU26222RMFS6", "SU26227RMFS5", "SU26234RMFS1"],
    "2Y": ["SU26229RMFS1", "SU26233RMFS3"],
    "3Y": ["SU26232RMFS5", "SU26230RMFS9", "SU26226RMFS7"],
    "5Y": ["SU26235RMFS9", "SU26236RMFS7", "SU26225RMFS9"],
    "7Y": ["SU26237RMFS5", "SU26221RMFS8"],
    "10Y": ["SU26238RMFS3", "SU26240RMFS9", "SU26241RMFS7", "SU26228RMFS3"],
    "15Y": ["SU26239RMFS1", "SU26230RMFS9"],
}

# =============================================================================
# FRED SERIES
# =============================================================================
# Discontinued FRED series (kept for reference, not fetched)
# RUSCCUSMA02STM: Russia Consumer Confidence — 404 since ~2023
# CHNPROINDMISMEI: China Industrial Production — 404 since ~2023
# GOLDAMGBD228NLBM: Gold Price — discontinued
FRED_OPTIONAL_SERIES = set()

FRED_SERIES_RUSSIA = {
    "RUSCPIALLMINMEI": "Russia CPI (Monthly)",
    "RUSPROINDMISMEI": "Russia Industrial Production Index",
}

FRED_SERIES_CHINA = {
    "CHNCPIALLMINMEI": "China CPI (Monthly)",
    "DEXCHUS": "USD/CNY Exchange Rate",
}

FRED_SERIES_GLOBAL = {
    "DGS10": "US 10-Year Treasury Yield",
    "DGS2": "US 2-Year Treasury Yield",
    "FEDFUNDS": "Federal Funds Rate",
    "DCOILBRENTEU": "Brent Crude Oil Price",
    "DTWEXBGS": "Trade Weighted USD Index",
    "IPMAN": "US Industrial Production: Manufacturing",
    "UMCSENT": "US Consumer Sentiment",
}

FRED_SERIES_BUSINESS_ACTIVITY = {
    "RUSPROINDMISMEI": "Russia Industrial Production",
    "IPMAN": "US Industrial Production: Manufacturing",
    "UMCSENT": "US Consumer Sentiment",
}

FRED_SERIES_RISK = {
    "VIXCLS": "CBOE VIX Volatility Index",
    "BAMLH0A0HYM2": "US High-Yield OAS (ICE BofA)",
}

FRED_SERIES_COMMODITIES = {
    "DHHNGSP": "Henry Hub Natural Gas Spot Price",
    "PCOPPUSDM": "Copper Price (USD/metric ton)",
}

# =============================================================================
# CBR CURRENCY CODES
# =============================================================================

CBR_CURRENCY_CODES = {
    "USD": "R01235",
    "EUR": "R01239",
    "CNY": "R01375",
    "GBP": "R01035",
    "JPY": "R01820",
}

# =============================================================================
# DATABASE CONFIGURATION
# =============================================================================

DB_PATH = PROJECT_ROOT / "bond_rates_database.db"

DB_TABLES = {
    'russian_bond_yields': 'Russian OFZ yields by maturity (monthly)',
    'chinese_bond_yields': 'Chinese government bond yields (monthly)',
    'russian_macro': 'Russian macroeconomic indicators (monthly)',
    'chinese_macro': 'Chinese macroeconomic indicators (monthly)',
    'cbr_key_rate': 'CBR key interest rate (monthly)',
    'cbr_gcurve': 'CBR G-Curve parameters (monthly)',
    'currency_rates': 'Currency exchange rates (monthly)',
    'pboc_lpr': 'PBOC Loan Prime Rate (monthly)',
    'global_indicators': 'Global economic indicators (monthly)',
    'business_activity': 'Business activity indicators (monthly)',
    'risk_sentiment': 'Risk sentiment indicators: VIX, US HY spreads (monthly)',
    'commodities': 'Commodity prices: natural gas, copper (monthly)',
    'russia_money_markets': 'Russia money markets: RUONIA, CBR FX reserves (monthly)',
    'china_money_markets': 'China money markets: SHIBOR, DR007, CNH-CNY spread, PBoC FX reserves (monthly)',
}

# Table prefixes for FRED-sourced data in combined_monthly
# Use these to explicitly restrict analysis to FRED-backed series
FRED_TABLE_PREFIXES = ['russian_macro', 'chinese_macro', 'global_indicators', 'business_activity']

# Weekly tables (separate from monthly; combined into combined_weekly view)
WEEKLY_BASE_TABLES = [
    'russian_bond_yields_weekly',
    'cbr_gcurve_weekly',
    'currency_rates_weekly',
    'chinese_bond_yields_weekly',
    'global_indicators_weekly',
    'risk_sentiment_weekly',
]

# Base tables only (exclude derived views like combined_monthly)
BASE_TABLES_FOR_COMBINED_VIEW = [
    'cbr_key_rate', 'cbr_gcurve', 'currency_rates', 'russian_bond_yields',
    'russian_macro', 'pboc_lpr', 'chinese_bond_yields', 'chinese_macro',
    'global_indicators', 'business_activity',
    'risk_sentiment', 'commodities', 'russia_money_markets', 'china_money_markets',
]

# Canonical variable prefixes for analysis (combined view columns are {table}_{col})
# Use these to select columns from combined_monthly when variables is not specified
ANALYSIS_VARIABLE_PREFIXES = list(BASE_TABLES_FOR_COMBINED_VIEW)

# =============================================================================
# SCHEDULER SETTINGS
# =============================================================================

# Update schedule (cron-like)
SCHEDULE = {
    'daily_update': '0 9 * * *',  # Every day at 9 AM
    'monthly_full_update': '0 10 1 * *',  # 1st of each month at 10 AM
}

