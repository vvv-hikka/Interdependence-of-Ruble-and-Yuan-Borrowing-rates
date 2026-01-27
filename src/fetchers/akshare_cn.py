"""
AKShare Fetcher - Chinese financial data
========================================
Source: https://akshare.akfamily.xyz/
Data: Chinese bonds, yields, macroeconomic indicators
Automation: Full (Python API)
Cost: Free
"""

import pandas as pd
from datetime import datetime
from typing import Optional, Dict, Any
import warnings
warnings.filterwarnings('ignore')


class AKShareFetcher:
    """Fetcher for Chinese financial data using AKShare library."""
    
    def __init__(self):
        self.ak = None
        self._import_akshare()
    
    def _import_akshare(self):
        """Import akshare with error handling."""
        try:
            import akshare as ak
            self.ak = ak
            print("[OK] AKShare imported successfully")
        except ImportError:
            print("[ERROR] AKShare not installed. Run: pip install akshare")
            self.ak = None
    
    def is_available(self) -> bool:
        """Check if AKShare is available."""
        return self.ak is not None
    
    # =========================================================================
    # BOND YIELDS
    # =========================================================================
    
    def fetch_china_bond_yields(self) -> pd.DataFrame:
        """
        Fetch Chinese government bond yields.
        Returns DataFrame with yield curve data.
        """
        if not self.is_available():
            return pd.DataFrame()
        
        try:
            # Chinese Treasury bond yields
            df = self.ak.bond_china_yield()
            if df is not None and not df.empty:
                # Standardize column names
                df.columns = [col.strip() for col in df.columns]
                print(f"  [OK] China bond yields: {len(df)} records")
                return df
        except Exception as e:
            print(f"  [ERROR] Error fetching China bond yields: {e}")
        
        return pd.DataFrame()
    
    def fetch_china_close_return_index(self) -> pd.DataFrame:
        """
        Fetch Chinese bond close return index.
        """
        if not self.is_available():
            return pd.DataFrame()
        
        try:
            df = self.ak.bond_china_close_return()
            if df is not None and not df.empty:
                print(f"  [OK] China bond close return: {len(df)} records")
                return df
        except Exception as e:
            print(f"  [ERROR] Error fetching China bond close return: {e}")
        
        return pd.DataFrame()
    
    # =========================================================================
    # PBOC RATES
    # =========================================================================
    
    def fetch_pboc_lpr(self) -> pd.DataFrame:
        """
        Fetch PBOC Loan Prime Rate (LPR) history.
        Returns DataFrame with 1-year and 5-year LPR.
        """
        if not self.is_available():
            return pd.DataFrame()
        
        try:
            df = self.ak.macro_china_lpr()
            if df is not None and not df.empty:
                # Standardize date column
                if '报告日' in df.columns:
                    df['date'] = pd.to_datetime(df['报告日'])
                elif 'TRADE_DATE' in df.columns:
                    df['date'] = pd.to_datetime(df['TRADE_DATE'])
                print(f"  [OK] PBOC LPR rates: {len(df)} records")
                return df
        except Exception as e:
            print(f"  [ERROR] Error fetching PBOC LPR: {e}")
        
        return pd.DataFrame()
    
    def fetch_pboc_required_reserve_ratio(self) -> pd.DataFrame:
        """
        Fetch PBOC Required Reserve Ratio history.
        """
        if not self.is_available():
            return pd.DataFrame()
        
        try:
            df = self.ak.macro_china_reserve_requirement_ratio()
            if df is not None and not df.empty:
                print(f"  [OK] PBOC Reserve Ratio: {len(df)} records")
                return df
        except Exception as e:
            print(f"  [ERROR] Error fetching PBOC Reserve Ratio: {e}")
        
        return pd.DataFrame()
    
    # =========================================================================
    # MACROECONOMIC INDICATORS
    # =========================================================================
    
    def fetch_china_cpi_monthly(self) -> pd.DataFrame:
        """Fetch China monthly CPI data."""
        if not self.is_available():
            return pd.DataFrame()
        
        try:
            df = self.ak.macro_china_cpi_monthly()
            if df is not None and not df.empty:
                print(f"  [OK] China CPI monthly: {len(df)} records")
                return df
        except Exception as e:
            print(f"  [ERROR] Error fetching China CPI: {e}")
        
        return pd.DataFrame()
    
    def fetch_china_ppi_monthly(self) -> pd.DataFrame:
        """Fetch China monthly PPI data."""
        if not self.is_available():
            return pd.DataFrame()
        
        try:
            df = self.ak.macro_china_ppi_monthly()
            if df is not None and not df.empty:
                print(f"  [OK] China PPI monthly: {len(df)} records")
                return df
        except Exception as e:
            print(f"  [ERROR] Error fetching China PPI: {e}")
        
        return pd.DataFrame()
    
    def fetch_china_pmi(self) -> pd.DataFrame:
        """Fetch China PMI data."""
        if not self.is_available():
            return pd.DataFrame()
        
        try:
            df = self.ak.macro_china_pmi()
            if df is not None and not df.empty:
                print(f"  [OK] China PMI: {len(df)} records")
                return df
        except Exception as e:
            print(f"  [ERROR] Error fetching China PMI: {e}")
        
        return pd.DataFrame()
    
    def fetch_china_gdp(self) -> pd.DataFrame:
        """Fetch China GDP data."""
        if not self.is_available():
            return pd.DataFrame()
        
        try:
            df = self.ak.macro_china_gdp()
            if df is not None and not df.empty:
                print(f"  [OK] China GDP: {len(df)} records")
                return df
        except Exception as e:
            print(f"  [ERROR] Error fetching China GDP: {e}")
        
        return pd.DataFrame()
    
    def fetch_china_gdp_yearly(self) -> pd.DataFrame:
        """Fetch China yearly GDP data."""
        if not self.is_available():
            return pd.DataFrame()
        
        try:
            df = self.ak.macro_china_gdp_yearly()
            if df is not None and not df.empty:
                print(f"  [OK] China GDP yearly: {len(df)} records")
                return df
        except Exception as e:
            print(f"  [ERROR] Error fetching China GDP yearly: {e}")
        
        return pd.DataFrame()
    
    def fetch_china_money_supply(self) -> pd.DataFrame:
        """Fetch China M0, M1, M2 money supply data."""
        if not self.is_available():
            return pd.DataFrame()
        
        try:
            df = self.ak.macro_china_money_supply()
            if df is not None and not df.empty:
                print(f"  [OK] China money supply: {len(df)} records")
                return df
        except Exception as e:
            print(f"  [ERROR] Error fetching China money supply: {e}")
        
        return pd.DataFrame()
    
    def fetch_china_fx_reserves(self) -> pd.DataFrame:
        """Fetch China foreign exchange reserves."""
        if not self.is_available():
            return pd.DataFrame()
        
        try:
            df = self.ak.macro_china_fx_reserves_yearly()
            if df is not None and not df.empty:
                print(f"  [OK] China FX reserves: {len(df)} records")
                return df
        except Exception as e:
            print(f"  [ERROR] Error fetching China FX reserves: {e}")
        
        return pd.DataFrame()
    
    def fetch_china_trade_balance(self) -> pd.DataFrame:
        """Fetch China trade balance (imports/exports)."""
        if not self.is_available():
            return pd.DataFrame()
        
        try:
            df = self.ak.macro_china_trade_balance()
            if df is not None and not df.empty:
                print(f"  [OK] China trade balance: {len(df)} records")
                return df
        except Exception as e:
            print(f"  [ERROR] Error fetching China trade balance: {e}")
        
        return pd.DataFrame()
    
    def fetch_china_new_loans(self) -> pd.DataFrame:
        """Fetch China new loan data (社会融资)."""
        if not self.is_available():
            return pd.DataFrame()
        
        try:
            df = self.ak.macro_china_new_financial_credit()
            if df is not None and not df.empty:
                print(f"  [OK] China new financial credit: {len(df)} records")
                return df
        except Exception as e:
            print(f"  [ERROR] Error fetching China new loans: {e}")
        
        return pd.DataFrame()
    
    # =========================================================================
    # EXCHANGE RATES
    # =========================================================================
    
    def fetch_cny_usd_rate(self) -> pd.DataFrame:
        """Fetch CNY/USD exchange rate history."""
        if not self.is_available():
            return pd.DataFrame()
        
        try:
            # PBOC middle rate
            df = self.ak.currency_boc_sina(symbol="美元", start_date="20150101", end_date=datetime.now().strftime("%Y%m%d"))
            if df is not None and not df.empty:
                print(f"  [OK] CNY/USD rate: {len(df)} records")
                return df
        except Exception as e:
            print(f"  [ERROR] Error fetching CNY/USD rate: {e}")
        
        return pd.DataFrame()
    
    # =========================================================================
    # AGGREGATE FETCH
    # =========================================================================
    
    def fetch_all_china_macro(self) -> Dict[str, pd.DataFrame]:
        """
        Fetch all available Chinese macroeconomic data.
        Returns dictionary with DataFrames.
        """
        print("\n" + "="*60)
        print("Fetching all Chinese macroeconomic data via AKShare...")
        print("="*60)
        
        data = {}
        
        # Bond yields and rates
        data['bond_yields'] = self.fetch_china_bond_yields()
        data['pboc_lpr'] = self.fetch_pboc_lpr()
        data['reserve_ratio'] = self.fetch_pboc_required_reserve_ratio()
        
        # Macro indicators
        data['cpi_monthly'] = self.fetch_china_cpi_monthly()
        data['ppi_monthly'] = self.fetch_china_ppi_monthly()
        data['pmi'] = self.fetch_china_pmi()
        data['gdp'] = self.fetch_china_gdp()
        data['money_supply'] = self.fetch_china_money_supply()
        data['trade_balance'] = self.fetch_china_trade_balance()
        
        print("\n" + "-"*60)
        print("Summary of fetched data:")
        for name, df in data.items():
            if df is not None and not df.empty:
                print(f"  {name}: {len(df)} rows, {len(df.columns)} columns")
            else:
                print(f"  {name}: No data")
        print("-"*60)
        
        return data
    
    def fetch_china_bond_yields_monthly(self) -> pd.DataFrame:
        """
        Fetch and resample Chinese bond yields to monthly frequency.
        """
        df = self.fetch_china_bond_yields()
        if df.empty:
            return df
        
        # Find date column
        date_col = None
        for col in ['日期', 'date', 'Date', 'DATE']:
            if col in df.columns:
                date_col = col
                break
        
        if date_col is None:
            print("  [ERROR] Cannot find date column in bond yields data")
            return pd.DataFrame()
        
        try:
            df['date'] = pd.to_datetime(df[date_col])
            df = df.set_index('date')
            
            # Resample to monthly (last value of each month)
            numeric_cols = df.select_dtypes(include=['number']).columns
            monthly = df[numeric_cols].resample('ME').last().reset_index()
            
            print(f"  [OK] Resampled to monthly: {len(monthly)} records")
            return monthly
        except Exception as e:
            print(f"  [ERROR] Error resampling to monthly: {e}")
            return pd.DataFrame()


# Test function
def test_akshare_fetcher():
    """Test AKShare fetcher functionality."""
    fetcher = AKShareFetcher()
    
    if not fetcher.is_available():
        print("AKShare not available")
        return
    
    # Test individual fetchers
    print("\nTesting individual fetchers:")
    
    lpr = fetcher.fetch_pboc_lpr()
    if not lpr.empty:
        print(f"  LPR sample:\n{lpr.head()}")
    
    cpi = fetcher.fetch_china_cpi_monthly()
    if not cpi.empty:
        print(f"  CPI sample:\n{cpi.head()}")


if __name__ == "__main__":
    test_akshare_fetcher()

