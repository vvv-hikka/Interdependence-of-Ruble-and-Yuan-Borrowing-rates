import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

import pandas as pd

# Import fetchers
from fetchers.akshare_cn import AKShareFetcher
from fetchers.moex import MOEXFetcher
from fetchers.cbr import CBRFetcher
from fetchers.fred import FREDFetcher
from fetchers.imf import IMFFetcher
from fetchers.chinabond import ChinaBondLoader, load_pboc_lpr
from database import DatabaseManager

# Import config
try:
    from config import API_KEYS, DEFAULT_START_DATE
except ImportError:
    API_KEYS = {}
    DEFAULT_START_DATE = "2015-01-01"


class DataPipeline:
    """Main data pipeline orchestrator."""
    
    def __init__(self, db_path: str = None, test_mode: bool = False):
        self.db = DatabaseManager(db_path) if not test_mode else None
        self.test_mode = test_mode
        
        # Initialize fetchers
        self.akshare = AKShareFetcher()
        self.moex = MOEXFetcher()
        self.cbr = CBRFetcher()
        self.fred = FREDFetcher(api_key=API_KEYS.get('fred'))
        self.imf = IMFFetcher()
        self.chinabond = ChinaBondLoader()
    
    def _save(self, df: pd.DataFrame, table_name: str, **kwargs) -> bool:
        """Save DataFrame to database (unless in test mode)."""
        if self.test_mode:
            print(f"  [TEST] Would save {len(df)} rows to '{table_name}'")
            return True
        return self.db.save_dataframe(df, table_name, **kwargs)
    
    # =========================================================================
    # RUSSIAN DATA
    # =========================================================================
    
    def fetch_russian_bond_yields(self, start_date: str = None) -> pd.DataFrame:
        """Fetch and save Russian OFZ yields."""
        print("\n" + "="*60)
        print("FETCHING RUSSIAN BOND YIELDS")
        print("="*60)
        
        if start_date is None:
            start_date = DEFAULT_START_DATE
        
        df = self.moex.fetch_ofz_yields_monthly(start_date)
        
        if not df.empty:
            self._save(df, 'russian_bond_yields',
                      description='Russian OFZ yields by maturity (monthly)',
                      source='MOEX ISS API')
        
        return df
    
    def fetch_cbr_data(self) -> dict:
        """Fetch and save CBR data (key rate, G-curve, currency rates)."""
        print("\n" + "="*60)
        print("FETCHING CBR DATA")
        print("="*60)
        
        data = {}
        
        # Key rate
        print("\n1. Key Rate:")
        df = self.cbr.fetch_key_rate_monthly()
        if not df.empty:
            data['key_rate'] = df
            self._save(df, 'cbr_key_rate',
                      description='CBR key interest rate (monthly)',
                      source='Bank of Russia XML API')
        
        # G-Curve
        print("\n2. G-Curve:")
        df = self.cbr.fetch_gcurve_monthly()
        if not df.empty:
            data['gcurve'] = df
            self._save(df, 'cbr_gcurve',
                      description='CBR G-Curve parameters (monthly)',
                      source='Bank of Russia')
        
        # Currency rates
        print("\n3. Currency Rates:")
        df = self.cbr.fetch_all_currency_rates_monthly()
        if not df.empty:
            data['currency'] = df
            self._save(df, 'currency_rates',
                      description='CBR currency exchange rates (monthly)',
                      source='Bank of Russia XML API')
        
        return data
    
    def fetch_russian_macro(self, start_date: str = None) -> pd.DataFrame:
        """Fetch Russian macroeconomic data from multiple sources."""
        print("\n" + "="*60)
        print("FETCHING RUSSIAN MACRO DATA")
        print("="*60)
        
        if start_date is None:
            start_date = DEFAULT_START_DATE
        
        all_data = []
        
        # FRED data
        print("\n1. From FRED:")
        fred_df = self.fred.fetch_russia_macro_combined(start_date)
        if not fred_df.empty:
            all_data.append(fred_df)
        
        # IMF data
        print("\n2. From IMF IFS:")
        try:
            imf_df = self.imf.fetch_russia_ifs(int(start_date[:4]))
            if not imf_df.empty:
                all_data.append(imf_df)
        except Exception as e:
            print(f"  IMF fetch failed: {e}")
        
        # Combine all sources
        if all_data:
            result = all_data[0]
            for df in all_data[1:]:
                result = result.merge(df, on='date', how='outer')
            result = result.sort_values('date')
            
            self._save(result, 'russian_macro',
                      description='Russian macroeconomic indicators (monthly)',
                      source='FRED, IMF IFS, World Bank')
            
            return result
        
        return pd.DataFrame()
    
    # =========================================================================
    # CHINESE DATA
    # =========================================================================
    
    def fetch_chinese_bond_yields(self) -> pd.DataFrame:
        """Fetch Chinese bond yields (AKShare + manual data)."""
        print("\n" + "="*60)
        print("FETCHING CHINESE BOND YIELDS")
        print("="*60)
        
        all_data = []
        
        # Try AKShare first
        print("\n1. From AKShare:")
        if self.akshare.is_available():
            df = self.akshare.fetch_china_bond_yields_monthly()
            if not df.empty:
                all_data.append(df)
        
        # Try manual ChinaBond data
        print("\n2. From manual ChinaBond file:")
        manual_df = self.chinabond.load_from_excel()
        if manual_df.empty:
            manual_df = self.chinabond.load_from_csv()
        
        if not manual_df.empty:
            manual_monthly = self.chinabond.resample_to_monthly(manual_df)
            all_data.append(manual_monthly)
        
        # Combine data
        if all_data:
            result = all_data[0]
            for df in all_data[1:]:
                result = result.merge(df, on='date', how='outer')
            result = result.sort_values('date')
            
            self._save(result, 'chinese_bond_yields',
                      description='Chinese government bond yields (monthly)',
                      source='AKShare, ChinaBond manual')
            
            return result
        
        # Create placeholder if no data
        print("\n  Creating placeholder for Chinese yields...")
        placeholder = self.chinabond.create_placeholder_data()
        self._save(placeholder, 'chinese_bond_yields',
                  description='Chinese bond yields PLACEHOLDER (needs manual data)',
                  source='Placeholder - download from ChinaBond')
        
        return placeholder
    
    def fetch_pboc_rates(self) -> pd.DataFrame:
        """Fetch PBOC rates (LPR, etc.)."""
        print("\n" + "="*60)
        print("FETCHING PBOC RATES")
        print("="*60)
        
        all_data = []
        
        # Try AKShare
        print("\n1. From AKShare:")
        if self.akshare.is_available():
            df = self.akshare.fetch_pboc_lpr()
            if not df.empty:
                all_data.append(df)
        
        # Use embedded data as fallback
        print("\n2. From embedded PBOC LPR data:")
        embedded = load_pboc_lpr()
        if not embedded.empty:
            print(f"  [OK] Loaded {len(embedded)} records from embedded data")
            all_data.append(embedded)
        
        if all_data:
            # Use the most complete dataset
            result = max(all_data, key=len)
            
            self._save(result, 'pboc_lpr',
                      description='PBOC Loan Prime Rate (monthly)',
                      source='PBOC official announcements')
            
            return result
        
        return pd.DataFrame()
    
    def fetch_chinese_macro(self, start_date: str = None) -> pd.DataFrame:
        """Fetch Chinese macroeconomic data."""
        print("\n" + "="*60)
        print("FETCHING CHINESE MACRO DATA")
        print("="*60)
        
        if start_date is None:
            start_date = DEFAULT_START_DATE
        
        all_data = []
        
        # AKShare data
        print("\n1. From AKShare:")
        if self.akshare.is_available():
            ak_data = self.akshare.fetch_all_china_macro()
            
            # Combine AKShare data
            for name, df in ak_data.items():
                if df is not None and not df.empty:
                    try:
                        # Find date column
                        date_col = None
                        for col in df.columns:
                            col_str = str(col)
                            if '日期' in col_str or 'date' in col_str.lower() or 'time' in col_str.lower():
                                date_col = col
                                break
                        
                        if date_col and date_col != 'date':
                            # Drop existing 'date' column if present to avoid duplicates
                            if 'date' in df.columns:
                                df = df.drop(columns=['date'])
                            df = df.rename(columns={date_col: 'date'})
                        
                        if 'date' in df.columns:
                            # Handle various date formats
                            df['date'] = pd.to_datetime(df['date'], errors='coerce', format='mixed')
                            df = df.dropna(subset=['date'])
                            
                            # Prefix columns with indicator name (except date)
                            rename_cols = {col: f'CN_{name}_{col}' for col in df.columns if col != 'date'}
                            df = df.rename(columns=rename_cols)
                            
                            if not df.empty and len(df) > 5:  # Only add if enough data
                                all_data.append(df)
                                print(f"    Added {name}: {len(df)} rows")
                    except Exception as e:
                        print(f"    [ERROR] Processing {name}: {e}")
        
        # FRED data
        print("\n2. From FRED:")
        fred_df = self.fred.fetch_china_macro_combined(start_date)
        if not fred_df.empty:
            all_data.append(fred_df)
        
        # IMF data  
        print("\n3. From IMF IFS:")
        try:
            imf_df = self.imf.fetch_china_ifs(int(start_date[:4]))
            if not imf_df.empty:
                all_data.append(imf_df)
        except Exception as e:
            print(f"  IMF fetch failed: {e}")
        
        # Combine all sources
        if all_data:
            result = all_data[0]
            for df in all_data[1:]:
                if 'date' in df.columns:
                    result = result.merge(df, on='date', how='outer')
            result = result.sort_values('date')
            
            self._save(result, 'chinese_macro',
                      description='Chinese macroeconomic indicators (monthly)',
                      source='AKShare, FRED, IMF IFS')
            
            return result
        
        return pd.DataFrame()
    
    # =========================================================================
    # GLOBAL DATA
    # =========================================================================
    
    def fetch_global_indicators(self, start_date: str = None) -> pd.DataFrame:
        """Fetch global economic indicators."""
        print("\n" + "="*60)
        print("FETCHING GLOBAL INDICATORS")
        print("="*60)
        
        if start_date is None:
            start_date = DEFAULT_START_DATE
        
        df = self.fred.fetch_global_combined(start_date)
        
        if not df.empty:
            # Resample to monthly
            df = self.fred.resample_to_monthly(df)
            
            self._save(df, 'global_indicators',
                      description='Global economic indicators (monthly)',
                      source='FRED API')
        
        return df
    
    # =========================================================================
    # FULL PIPELINE
    # =========================================================================
    
    def run_full_update(self, start_date: str = None):
        """Run full data update."""
        print("\n" + "="*70)
        print("RUNNING FULL DATA UPDATE")
        print(f"Start date: {start_date or DEFAULT_START_DATE}")
        print(f"Mode: {'TEST' if self.test_mode else 'PRODUCTION'}")
        print("="*70)
        
        start_time = datetime.now()
        
        # Russian data
        self.fetch_cbr_data()
        self.fetch_russian_bond_yields(start_date)
        self.fetch_russian_macro(start_date)
        
        # Chinese data
        self.fetch_pboc_rates()
        self.fetch_chinese_bond_yields()
        self.fetch_chinese_macro(start_date)
        
        # Global data
        self.fetch_global_indicators(start_date)
        
        # Create combined view
        if not self.test_mode:
            print("\n" + "="*60)
            print("CREATING COMBINED VIEW")
            print("="*60)
            self.db.create_combined_monthly_view()
            
            # Print summary
            self.db.print_summary()
        
        elapsed = datetime.now() - start_time
        print(f"\n[OK] Update completed in {elapsed.total_seconds():.1f} seconds")
    
    def run_quick_update(self):
        """Run quick update (last 3 months only)."""
        start_date = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
        print(f"\nRunning quick update from {start_date}...")
        self.run_full_update(start_date)


def main():
    parser = argparse.ArgumentParser(description='Data Pipeline for Bond Rates Database')
    parser.add_argument('--quick', action='store_true', help='Quick update (last 3 months)')
    parser.add_argument('--test', action='store_true', help='Test mode (no database writes)')
    parser.add_argument('--start-date', type=str, help='Start date (YYYY-MM-DD)')
    
    args = parser.parse_args()
    
    pipeline = DataPipeline(test_mode=args.test)
    
    if args.quick:
        pipeline.run_quick_update()
    else:
        pipeline.run_full_update(args.start_date)


if __name__ == "__main__":
    main()

