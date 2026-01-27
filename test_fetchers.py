"""
Test script for data fetchers
"""

import sys
import os
from pathlib import Path

# Fix encoding for Windows console
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    os.environ['PYTHONIOENCODING'] = 'utf-8'

sys.path.insert(0, str(Path(__file__).parent / "src"))

from fetchers.moex import MOEXFetcher
from fetchers.cbr import CBRFetcher
from fetchers.fred import FREDFetcher
from fetchers.akshare_cn import AKShareFetcher


def test_moex():
    """Test MOEX fetcher."""
    print("\n" + "="*60)
    print("TESTING MOEX FETCHER")
    print("="*60)
    
    moex = MOEXFetcher()
    
    # Search for OFZ bonds
    print("\nSearching for OFZ bonds...")
    for prefix in ['SU262', 'SU263', 'SU264', 'SU265']:
        ofz = moex.search_securities(prefix)
        for _, row in ofz.iterrows():
            if row.get('is_traded') == 1:
                secid = row['secid']
                # Safe print without cyrillic
                print(f"  Found: {secid}")
    
    # Test bond history with correct SECID
    print("\nFetching bond history (SU26238RMFS4)...")
    history = moex.fetch_bond_history('SU26238RMFS4', '2024-01-01', '2024-12-31')
    print(f"Got {len(history)} records")
    
    if not history.empty and 'YIELDCLOSE' in history.columns:
        print(history[['TRADEDATE', 'CLOSE', 'YIELDCLOSE']].tail().to_string())
    
    # Test OFZ yields monthly
    print("\nFetching OFZ yields monthly...")
    yields = moex.fetch_ofz_yields_monthly('2024-01-01', '2024-12-31')
    if not yields.empty:
        print(f"Got {len(yields)} monthly records")
        print(yields.tail().to_string())


def test_cbr():
    """Test CBR fetcher."""
    print("\n" + "="*60)
    print("TESTING CBR FETCHER")
    print("="*60)
    
    cbr = CBRFetcher()
    
    # Test key rate
    print("\nFetching key rate...")
    key_rate = cbr.fetch_key_rate()
    print(f"Got {len(key_rate)} records")
    if not key_rate.empty:
        print(key_rate.tail().to_string())
    
    # Test currency rates
    print("\nFetching USD/RUB rate...")
    usd = cbr.fetch_usd_rate("01/01/2024", "31/12/2024")
    print(f"Got {len(usd)} records")
    if not usd.empty:
        print(usd.tail().to_string())
    
    # Test G-Curve
    print("\nFetching G-Curve...")
    gcurve = cbr.fetch_gcurve_params("01.01.2024", "31.12.2024")
    print(f"Got {len(gcurve)} records")
    if not gcurve.empty:
        # G-Curve might have cyrillic column names
        print(f"Columns: {list(gcurve.columns)}")


def test_fred():
    """Test FRED fetcher."""
    print("\n" + "="*60)
    print("TESTING FRED FETCHER")
    print("="*60)
    
    fred = FREDFetcher()
    
    # Test US 10Y yield
    print("\nFetching US 10Y Treasury Yield...")
    df = fred.fetch_series("DGS10", "2024-01-01")
    print(f"Got {len(df)} records")
    if not df.empty:
        print(df.tail().to_string())
    
    # Test Russia CPI
    print("\nFetching Russia CPI...")
    df = fred.fetch_series("RUSCPIALLMINMEI", "2020-01-01")
    print(f"Got {len(df)} records")
    if not df.empty:
        print(df.tail().to_string())


def test_akshare():
    """Test AKShare fetcher."""
    print("\n" + "="*60)
    print("TESTING AKSHARE FETCHER")
    print("="*60)
    
    ak = AKShareFetcher()
    
    if not ak.is_available():
        print("AKShare not available")
        return
    
    # Test PBOC LPR
    print("\nFetching PBOC LPR...")
    lpr = ak.fetch_pboc_lpr()
    print(f"Got {len(lpr)} records")
    if not lpr.empty:
        print(f"Columns: {list(lpr.columns)}")
        print(f"Last 5 rows shape: {lpr.tail().shape}")
    
    # Test China CPI
    print("\nFetching China CPI...")
    cpi = ak.fetch_china_cpi_monthly()
    print(f"Got {len(cpi)} records")
    if not cpi.empty:
        print(f"Columns: {list(cpi.columns)}")
    
    # Test bond yields
    print("\nFetching China bond yields...")
    yields = ak.fetch_china_bond_yields()
    print(f"Got {len(yields)} records")
    if not yields.empty:
        print(f"Columns: {list(yields.columns)}")


def main():
    print("Running fetcher tests...")
    
    test_moex()
    test_cbr()
    test_fred()
    test_akshare()
    
    print("\n" + "="*60)
    print("ALL TESTS COMPLETED")
    print("="*60)


if __name__ == "__main__":
    main()

