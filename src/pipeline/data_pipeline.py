import argparse
from datetime import datetime, timedelta

import pandas as pd

from src.fetchers.akshare_cn import AKShareFetcher
from src.fetchers.moex import MOEXFetcher
from src.fetchers.cbr import CBRFetcher
from src.fetchers.fred import FREDFetcher
from src.fetchers.chinabond import ChinaBondLoader, load_pboc_lpr
from src.database import DatabaseManager

try:
    from config import API_KEYS, DEFAULT_START_DATE, MANUAL_DATA_DIR
except ImportError:
    API_KEYS = {}
    DEFAULT_START_DATE = "2015-01-01"
    MANUAL_DATA_DIR = None


class DataPipeline:
    """Main data pipeline orchestrator.
    
    Only calls sources that are known to return data:
      - CBR: key rate, G-curve, currency rates
      - MOEX: OFZ yields
      - FRED: Russia CPI/IP, China CPI, USD/CNY, global indicators, business activity
      - AKShare: China bond yields, PBOC LPR, CPI, PPI, PMI, GDP, money supply, trade balance
      - Embedded: PBOC LPR fallback
    
    Excluded (always fail/empty):
      - IMF IFS (all requests timeout)
      - BIS (placeholder, no real fetch)
      - CBR industrial production / business confidence (placeholder)
      - FRED RUSCCUSMA02STM, CHNPROINDMISMEI (discontinued, 404)
    """
    
    def __init__(self, db_path: str = None, test_mode: bool = False):
        self.db = DatabaseManager(db_path) if not test_mode else None
        self.test_mode = test_mode
        
        self.akshare = AKShareFetcher()
        self.moex = MOEXFetcher()
        self.cbr = CBRFetcher()
        fred_key = API_KEYS.get('fred')
        self.fred = FREDFetcher(api_key=fred_key)
        if fred_key:
            print("  [INFO] FRED fetcher using API (FRED_API_KEY set)")
        self.chinabond = ChinaBondLoader()
        
        self._akshare_cache = None
    
    def _save(self, df: pd.DataFrame, table_name: str, **kwargs) -> bool:
        if self.test_mode:
            print(f"  [TEST] Would save {len(df)} rows to '{table_name}'")
            return True
        return self.db.save_dataframe(df, table_name, **kwargs)
    
    def _get_akshare_data(self) -> dict:
        """Fetch AKShare China macro data once and cache it."""
        if self._akshare_cache is None and self.akshare.is_available():
            self._akshare_cache = self.akshare.fetch_all_china_macro()
        return self._akshare_cache or {}
    
    # =========================================================================
    # RUSSIAN DATA
    # =========================================================================
    
    def fetch_cbr_data(self) -> dict:
        print("\n" + "="*60)
        print("FETCHING CBR DATA")
        print("="*60)
        
        data = {}
        
        print("\n1. Key Rate:")
        df = self.cbr.fetch_key_rate_monthly()
        if not df.empty:
            data['key_rate'] = df
            self._save(df, 'cbr_key_rate',
                      description='CBR key interest rate (monthly)',
                      source='Bank of Russia XML/HTML')
        
        print("\n2. G-Curve:")
        df = self.cbr.fetch_gcurve_monthly()
        if not df.empty:
            data['gcurve'] = df
            self._save(df, 'cbr_gcurve',
                      description='CBR G-Curve yields (monthly)',
                      source='Bank of Russia')
        
        print("\n3. Currency Rates:")
        df = self.cbr.fetch_all_currency_rates_monthly()
        if not df.empty:
            data['currency'] = df
            self._save(df, 'currency_rates',
                      description='CBR currency exchange rates (monthly)',
                      source='Bank of Russia XML API')
        
        return data
    
    def fetch_russian_bond_yields(self, start_date: str = None) -> pd.DataFrame:
        print("\n" + "="*60)
        print("FETCHING RUSSIAN BOND YIELDS")
        print("="*60)
        
        df = self.moex.fetch_ofz_yields_monthly(start_date or DEFAULT_START_DATE)
        if not df.empty:
            self._save(df, 'russian_bond_yields',
                      description='Russian OFZ yields by maturity (monthly)',
                      source='MOEX ISS API')
        return df
    
    def fetch_russian_macro(self, start_date: str = None) -> pd.DataFrame:
        print("\n" + "="*60)
        print("FETCHING RUSSIAN MACRO DATA")
        print("="*60)
        
        start_date = start_date or DEFAULT_START_DATE
        
        print("\nFrom FRED:")
        fred_df = self.fred.fetch_russia_macro_combined(start_date)
        
        if not fred_df.empty:
            self._save(fred_df, 'russian_macro',
                      description='Russian macroeconomic indicators (monthly)',
                      source='FRED API')
            return fred_df
        
        return pd.DataFrame()
    
    # =========================================================================
    # CHINESE DATA
    # =========================================================================
    
    def fetch_pboc_rates(self) -> pd.DataFrame:
        print("\n" + "="*60)
        print("FETCHING PBOC RATES")
        print("="*60)
        
        all_data = []
        
        print("\n1. From AKShare:")
        if self.akshare.is_available():
            df = self.akshare.fetch_pboc_lpr()
            if not df.empty:
                all_data.append(df)
        
        print("\n2. From embedded PBOC LPR data:")
        embedded = load_pboc_lpr()
        if not embedded.empty:
            print(f"  [OK] Loaded {len(embedded)} records from embedded data")
            all_data.append(embedded)
        
        if all_data:
            result = max(all_data, key=len).copy()
            if 'TRADE_DATE' in result.columns:
                if 'date' not in result.columns:
                    result['date'] = pd.to_datetime(result['TRADE_DATE'])
                result = result.drop(columns=['TRADE_DATE'])
            if 'date' in result.columns:
                result['date'] = pd.to_datetime(result['date'], errors='coerce')
            
            self._save(result, 'pboc_lpr',
                      description='PBOC Loan Prime Rate',
                      source='AKShare / embedded data')
            return result
        
        return pd.DataFrame()
    
    def fetch_chinese_bond_yields(self) -> pd.DataFrame:
        print("\n" + "="*60)
        print("FETCHING CHINESE BOND YIELDS")
        print("="*60)
        
        all_data = []
        
        print("\n1. From AKShare:")
        akshare_df = pd.DataFrame()
        if self.akshare.is_available():
            akshare_df = self.akshare.fetch_china_bond_yields_monthly()
            if not akshare_df.empty:
                all_data.append(akshare_df)
        
        print("\n2. From manual ChinaBond (src/data_manual/ or data/manual/):")
        manual_df = self.chinabond.load_from_directory()
        if manual_df.empty and MANUAL_DATA_DIR is not None:
            self.chinabond.data_dir = MANUAL_DATA_DIR
            manual_df = self.chinabond.load_from_directory()
        if manual_df.empty:
            manual_df = self.chinabond.load_from_excel()
        if manual_df.empty:
            manual_df = self.chinabond.load_from_csv()
        if not manual_df.empty:
            manual_monthly = self.chinabond.resample_to_monthly(manual_df)
            all_data.append(manual_monthly)
        
        if all_data:
            # Use the source with more rows as base
            all_data.sort(key=lambda d: len(d), reverse=True)
            result = all_data[0]
            for df in all_data[1:]:
                result = result.merge(df, on='date', how='outer')
            result = result.sort_values('date')
            
            self._save(result, 'chinese_bond_yields',
                      description='Chinese government bond yields (monthly)',
                      source='AKShare, ChinaBond manual')
            return result
        
        print("\n  Creating placeholder for Chinese yields...")
        placeholder = self.chinabond.create_placeholder_data()
        self._save(placeholder, 'chinese_bond_yields',
                  description='Chinese bond yields PLACEHOLDER',
                  source='Placeholder')
        return placeholder
    
    def fetch_chinese_macro(self, start_date: str = None) -> pd.DataFrame:
        """Fetch Chinese macro using cached AKShare data + FRED."""
        print("\n" + "="*60)
        print("FETCHING CHINESE MACRO DATA")
        print("="*60)
        
        start_date = start_date or DEFAULT_START_DATE
        all_data = []
        
        print("\n1. From AKShare:")
        ak_data = self._get_akshare_data()
        
        for name, df in ak_data.items():
            if df is None or df.empty:
                continue
            try:
                date_col = None
                for col in df.columns:
                    col_str = str(col)
                    if '日期' in col_str or 'date' in col_str.lower() or 'time' in col_str.lower():
                        date_col = col
                        break
                
                if date_col and date_col != 'date':
                    if 'date' in df.columns:
                        df = df.drop(columns=['date'])
                    df = df.rename(columns={date_col: 'date'})
                
                if 'date' not in df.columns:
                    continue
                
                df['date'] = pd.to_datetime(df['date'], errors='coerce', format='mixed')
                df = df.dropna(subset=['date'])
                
                rename_cols = {}
                used = set()
                for col in df.columns:
                    if col == 'date':
                        continue
                    suffix = str(col)
                    if not suffix.isascii() or not suffix.replace('_', '').replace('.', '').isalnum():
                        suffix = ''.join(c if c.isalnum() or c in '_.' else '_' for c in suffix)
                        if not suffix or suffix == '_':
                            suffix = 'value'
                    base = f'CN_{name}_{suffix}'
                    target = base
                    n = 0
                    while target in used:
                        n += 1
                        target = f'{base}_{n}'
                    used.add(target)
                    rename_cols[col] = target
                df = df.rename(columns=rename_cols)
                
                if not df.empty and len(df) > 5:
                    all_data.append(df)
                    print(f"    Added {name}: {len(df)} rows")
            except Exception as e:
                print(f"    [ERROR] Processing {name}: {e}")
        
        print("\n2. From FRED:")
        fred_df = self.fred.fetch_china_macro_combined(start_date)
        if not fred_df.empty:
            all_data.append(fred_df)
        
        if all_data:
            result = all_data[0]
            for df in all_data[1:]:
                if 'date' in df.columns:
                    result = result.merge(df, on='date', how='outer')
            result = result.sort_values('date')
            
            self._save(result, 'chinese_macro',
                      description='Chinese macroeconomic indicators (monthly)',
                      source='AKShare, FRED')
            return result
        
        return pd.DataFrame()
    
    # =========================================================================
    # GLOBAL DATA
    # =========================================================================
    
    def fetch_global_indicators(self, start_date: str = None) -> pd.DataFrame:
        print("\n" + "="*60)
        print("FETCHING GLOBAL INDICATORS")
        print("="*60)
        
        start_date = start_date or DEFAULT_START_DATE
        df = self.fred.fetch_global_combined(start_date)
        
        if not df.empty:
            df = self.fred.resample_to_monthly(df)
            self._save(df, 'global_indicators',
                      description='Global economic indicators (monthly)',
                      source='FRED API')
        return df
    
    # =========================================================================
    # BUSINESS ACTIVITY
    # =========================================================================
    
    def fetch_business_activity(self, start_date: str = None) -> pd.DataFrame:
        """Fetch business activity from FRED + cached AKShare PMI data."""
        print("\n" + "="*60)
        print("FETCHING BUSINESS ACTIVITY INDICATORS")
        print("="*60)
        
        start_date = start_date or DEFAULT_START_DATE
        all_data = []
        
        print("\n1. From FRED:")
        fred_business = self.fred.fetch_business_activity_combined(start_date)
        if not fred_business.empty:
            all_data.append(fred_business)
        
        print("\n2. From AKShare (China PMI):")
        ak_data = self._get_akshare_data()
        for key in ['pmi', 'services_pmi']:
            if key in ak_data and ak_data[key] is not None and not ak_data[key].empty:
                df = ak_data[key].copy()
                date_col = None
                for col in df.columns:
                    col_str = str(col)
                    if '日期' in col_str or 'date' in col_str.lower() or 'time' in col_str.lower():
                        date_col = col
                        break
                
                if date_col and date_col != 'date':
                    if 'date' in df.columns:
                        df = df.drop(columns=['date'])
                    df = df.rename(columns={date_col: 'date'})
                
                if 'date' in df.columns:
                    df['date'] = pd.to_datetime(df['date'], errors='coerce', format='mixed')
                    df = df.dropna(subset=['date'])
                    df = df.set_index('date')
                    numeric_cols = df.select_dtypes(include=['number']).columns
                    df = df[numeric_cols].resample('ME').last().reset_index()
                    rename_cols = {col: f'CN_{key}_{col}' for col in df.columns if col != 'date'}
                    df = df.rename(columns=rename_cols)
                    if not df.empty:
                        all_data.append(df)
                        print(f"    Added {key}: {len(df)} rows")
        
        if all_data:
            result = all_data[0]
            for df in all_data[1:]:
                if 'date' in df.columns:
                    result = result.merge(df, on='date', how='outer')
            result = result.sort_values('date')
            
            self._save(result, 'business_activity',
                      description='Business activity indicators (monthly)',
                      source='FRED, AKShare')
            return result
        
        print("  [WARNING] No business activity data collected")
        return pd.DataFrame()
    
    # =========================================================================
    # RISK SENTIMENT & COMMODITIES
    # =========================================================================

    def fetch_risk_sentiment(self, start_date: str = None) -> pd.DataFrame:
        print("\n" + "="*60)
        print("FETCHING RISK SENTIMENT INDICATORS")
        print("="*60)

        df = self.fred.fetch_risk_combined(start_date or DEFAULT_START_DATE)
        if not df.empty:
            self._save(df, 'risk_sentiment',
                       description='Risk sentiment: VIX, US HY OAS (monthly)',
                       source='FRED API')
        return df

    def fetch_commodities(self, start_date: str = None) -> pd.DataFrame:
        print("\n" + "="*60)
        print("FETCHING COMMODITY PRICES")
        print("="*60)

        df = self.fred.fetch_commodities_combined(start_date or DEFAULT_START_DATE)
        if not df.empty:
            self._save(df, 'commodities',
                       description='Commodity prices: natural gas, copper (monthly)',
                       source='FRED API')
        return df

    # =========================================================================
    # RUSSIA MONEY MARKETS
    # =========================================================================

    def fetch_russia_money_markets(self) -> pd.DataFrame:
        print("\n" + "="*60)
        print("FETCHING RUSSIA MONEY MARKETS")
        print("="*60)

        all_data = []

        print("\n1. RUONIA (MOEX):")
        ruonia = self.moex.fetch_ruonia_monthly()
        if not ruonia.empty:
            all_data.append(ruonia)

        print("\n2. Russia FX Reserves (CBR):")
        fx_res = self.cbr.fetch_fx_reserves_monthly()
        if not fx_res.empty:
            all_data.append(fx_res)

        if not all_data:
            print("  [WARNING] No Russia money market data collected")
            return pd.DataFrame()

        result = all_data[0]
        for df in all_data[1:]:
            result = result.merge(df, on='date', how='outer')
        result = result.sort_values('date')

        self._save(result, 'russia_money_markets',
                   description='Russia money markets: RUONIA, FX reserves (monthly)',
                   source='MOEX ISS, CBR')
        return result

    # =========================================================================
    # CHINA MONEY MARKETS
    # =========================================================================

    def fetch_china_money_markets(self) -> pd.DataFrame:
        print("\n" + "="*60)
        print("FETCHING CHINA MONEY MARKETS")
        print("="*60)

        df = self.akshare.fetch_china_money_markets()
        if not df.empty:
            self._save(df, 'china_money_markets',
                       description='China money markets: SHIBOR, DR007, CNH-CNY, PBoC FX reserves (monthly)',
                       source='AKShare')
        else:
            print("  [WARNING] No China money market data collected")
        return df

    # =========================================================================
    # FULL PIPELINE
    # =========================================================================
    
    def run_full_update(self, start_date: str = None):
        print("\n" + "="*70)
        print("RUNNING FULL DATA UPDATE")
        print(f"Start date: {start_date or DEFAULT_START_DATE}")
        print(f"Mode: {'TEST' if self.test_mode else 'PRODUCTION'}")
        print("="*70)
        
        start_time = datetime.now()
        
        self.fetch_cbr_data()
        self.fetch_russian_bond_yields(start_date)
        self.fetch_russian_macro(start_date)

        self.fetch_pboc_rates()
        self.fetch_chinese_bond_yields()
        self.fetch_chinese_macro(start_date)

        self.fetch_global_indicators(start_date)
        self.fetch_business_activity(start_date)

        self.fetch_risk_sentiment(start_date)
        self.fetch_commodities(start_date)
        self.fetch_russia_money_markets()
        self.fetch_china_money_markets()
        
        if not self.test_mode:
            print("\n" + "="*60)
            print("CREATING COMBINED VIEW")
            print("="*60)
            self.db.create_combined_monthly_view()
            self.db.print_summary()
        
        elapsed = datetime.now() - start_time
        print(f"\n[OK] Update completed in {elapsed.total_seconds():.1f} seconds")
    
    def run_quick_update(self):
        start_date = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
        print(f"\nRunning quick update from {start_date}...")
        self.run_full_update(start_date)

    # =========================================================================
    # WEEKLY UPDATE
    # =========================================================================

    def run_weekly_update(self, start_date: str = None):
        """
        Fetch and persist all weekly-frequency data, then rebuild combined_weekly.

        Sources:
          - MOEX: OFZ yields weekly
          - CBR: G-Curve weekly, currency rates weekly
          - FRED: global indicators weekly, risk sentiment weekly
          - AKShare: Chinese bond yields weekly
        """
        print("\n" + "="*70)
        print("RUNNING WEEKLY DATA UPDATE")
        print(f"Start date: {start_date or DEFAULT_START_DATE}")
        print(f"Mode: {'TEST' if self.test_mode else 'PRODUCTION'}")
        print("="*70)

        start_time = datetime.now()

        # --- Russian weekly ---
        print("\n" + "="*60)
        print("FETCHING RUSSIAN WEEKLY DATA")
        print("="*60)

        print("\n1. OFZ yields (weekly):")
        df = self.moex.fetch_ofz_yields_weekly(start_date or DEFAULT_START_DATE)
        if not df.empty:
            self._save(df, 'russian_bond_yields_weekly',
                       description='Russian OFZ yields by maturity (weekly)',
                       source='MOEX ISS API', frequency='weekly')

        print("\n2. G-Curve (weekly):")
        df = self.cbr.fetch_gcurve_weekly()
        if not df.empty:
            self._save(df, 'cbr_gcurve_weekly',
                       description='CBR G-Curve yields (weekly)',
                       source='Bank of Russia', frequency='weekly')

        print("\n3. Currency rates (weekly):")
        df = self.cbr.fetch_currency_rates_weekly()
        if not df.empty:
            self._save(df, 'currency_rates_weekly',
                       description='CBR currency exchange rates (weekly)',
                       source='Bank of Russia XML API', frequency='weekly')

        # --- Chinese weekly ---
        print("\n" + "="*60)
        print("FETCHING CHINESE WEEKLY DATA")
        print("="*60)

        print("\n4. Chinese bond yields (weekly):")
        df = self.akshare.fetch_china_bond_yields_weekly()
        if not df.empty:
            self._save(df, 'chinese_bond_yields_weekly',
                       description='Chinese government bond yields (weekly)',
                       source='AKShare', frequency='weekly')

        # --- Global weekly ---
        print("\n" + "="*60)
        print("FETCHING GLOBAL WEEKLY DATA")
        print("="*60)

        print("\n5. Global indicators (weekly):")
        df = self.fred.fetch_global_weekly(start_date or DEFAULT_START_DATE)
        if not df.empty:
            self._save(df, 'global_indicators_weekly',
                       description='Global economic indicators (weekly)',
                       source='FRED API', frequency='weekly')

        print("\n6. Risk sentiment (weekly):")
        df = self.fred.fetch_risk_weekly(start_date or DEFAULT_START_DATE)
        if not df.empty:
            self._save(df, 'risk_sentiment_weekly',
                       description='Risk sentiment: VIX, US HY OAS (weekly)',
                       source='FRED API', frequency='weekly')

        if not self.test_mode:
            print("\n" + "="*60)
            print("CREATING COMBINED WEEKLY VIEW")
            print("="*60)
            self.db.create_combined_weekly_view()

        elapsed = datetime.now() - start_time
        print(f"\n[OK] Weekly update completed in {elapsed.total_seconds():.1f} seconds")


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
