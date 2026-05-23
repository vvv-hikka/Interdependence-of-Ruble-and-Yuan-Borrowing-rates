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
    
    def _try_akshare_methods(self, candidate_names: list, label: str) -> pd.DataFrame:
        """Try candidate akshare method names via getattr; return first non-empty DataFrame or empty + single log."""
        for name in candidate_names:
            fn = getattr(self.ak, name, None)
            if fn is None or not callable(fn):
                continue
            try:
                df = fn()
                if df is not None and not df.empty:
                    return df
            except Exception:
                continue
        print(f"  [INFO] {label} not available (no akshare method)")
        return pd.DataFrame()
    
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
        """Fetch China monthly PPI data. Tries multiple akshare method names; returns empty if none exist."""
        if not self.is_available():
            return pd.DataFrame()
        candidates = ["macro_china_ppi_monthly", "macro_china_ppi", "macro_china_ppi_yearly"]
        df = self._try_akshare_methods(candidates, "China PPI monthly")
        if not df.empty:
            print(f"  [OK] China PPI monthly: {len(df)} records")
        return df
    
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
    
    def fetch_china_industrial_production(self) -> pd.DataFrame:
        """Fetch China industrial production index. Tries multiple akshare method names; returns empty if none exist."""
        if not self.is_available():
            return pd.DataFrame()
        candidates = [
            "macro_china_industrial_production",
            "macro_china_industrial_value",
            "macro_china_industrial_output",
            "macro_china_industrial_value_monthly",
        ]
        df = self._try_akshare_methods(candidates, "China industrial production")
        if not df.empty:
            print(f"  [OK] China industrial production: {len(df)} records")
        return df
    
    def fetch_china_services_pmi(self) -> pd.DataFrame:
        """Fetch China Services PMI."""
        if not self.is_available():
            return pd.DataFrame()
        
        try:
            # Try to fetch services PMI
            try:
                df = self.ak.macro_china_pmi_services()
            except AttributeError:
                # Alternative: non-manufacturing PMI
                try:
                    df = self.ak.macro_china_pmi_non_manufacturing()
                except AttributeError:
                    # Try general PMI and filter
                    df = self.ak.macro_china_pmi()
                    if df is not None and not df.empty:
                        # Filter for services/non-manufacturing columns if available
                        services_cols = [col for col in df.columns if '服务' in str(col) or '非制造业' in str(col) or 'services' in str(col).lower()]
                        if services_cols:
                            df = df[['date'] + services_cols] if 'date' in df.columns else df[services_cols]
            
            if df is not None and not df.empty:
                print(f"  [OK] China Services PMI: {len(df)} records")
                return df
        except Exception as e:
            print(f"  [ERROR] Error fetching China Services PMI: {e}")
        
        return pd.DataFrame()
    
    def fetch_china_business_confidence(self) -> pd.DataFrame:
        """Fetch China business confidence index. Tries multiple akshare method names; returns empty if none exist."""
        if not self.is_available():
            return pd.DataFrame()
        candidates = [
            "macro_china_business_confidence",
            "macro_china_business_climate",
            "macro_china_enterprise_confidence",
        ]
        df = self._try_akshare_methods(candidates, "China business confidence")
        if not df.empty:
            print(f"  [OK] China business confidence: {len(df)} records")
        return df
    
    # =========================================================================
    # CHINA MONEY MARKETS
    # =========================================================================

    def fetch_shibor(self) -> pd.DataFrame:
        """
        Fetch SHIBOR (Shanghai Interbank Offered Rate) history.
        Returns daily rates for multiple tenors; caller resamples to monthly.
        """
        if not self.is_available():
            return pd.DataFrame()

        candidates = ["rate_interbank", "macro_china_shibor", "rate_shibor"]
        df = self._try_akshare_methods(candidates, "SHIBOR")
        if not df.empty:
            print(f"  [OK] SHIBOR: {len(df)} records")
        return df

    def fetch_dr007(self) -> pd.DataFrame:
        """
        Fetch DR007 (7-day pledged repo rate) — the PBoC's operating target.
        Tries multiple AKShare method names.
        """
        if not self.is_available():
            return pd.DataFrame()

        candidates = [
            "bond_repo_zh_sina",
            "macro_china_market_loan_rate",
            "macro_china_repo_rate",
            "bond_repo_hist",
        ]
        df = self._try_akshare_methods(candidates, "DR007")
        if not df.empty:
            print(f"  [OK] DR007: {len(df)} records")
        return df

    def fetch_cnh_cny_spread(self) -> pd.DataFrame:
        """
        Fetch CNH−CNY spread (offshore vs onshore yuan premium).
        Measures capital account pressure. Tries multiple AKShare method names.
        """
        if not self.is_available():
            return pd.DataFrame()

        candidates = [
            "currency_hist_cnh_cny",
            "fx_spot_quote",
            "macro_china_cnh_cny",
        ]
        df = self._try_akshare_methods(candidates, "CNH-CNY spread")
        if not df.empty:
            print(f"  [OK] CNH-CNY spread: {len(df)} records")
        return df

    def fetch_pboc_fx_reserves_monthly(self) -> pd.DataFrame:
        """
        Fetch PBoC foreign exchange reserves at monthly frequency.
        Tries monthly endpoint first, falls back to yearly.
        """
        if not self.is_available():
            return pd.DataFrame()

        candidates = [
            "macro_china_fx_reserves",
            "macro_china_fx_reserves_monthly",
            "macro_china_foreign_exchange_reserves",
        ]
        df = self._try_akshare_methods(candidates, "PBoC FX reserves (monthly)")

        if df.empty:
            # Fall back to yearly
            try:
                df = self.ak.macro_china_fx_reserves_yearly()
                if df is not None and not df.empty:
                    print(f"  [OK] PBoC FX reserves (yearly fallback): {len(df)} records")
            except Exception:
                pass

        if not df.empty:
            print(f"  [OK] PBoC FX reserves: {len(df)} records")
        return df

    def fetch_china_money_markets(self) -> pd.DataFrame:
        """
        Fetch all China money market indicators and merge into a single monthly DataFrame.
        Columns: date, SHIBOR_*, DR007_*, cnh_cny_spread, pboc_fx_reserves.
        """
        if not self.is_available():
            return pd.DataFrame()

        all_data = []

        # --- SHIBOR ---
        shibor = self.fetch_shibor()
        if not shibor.empty:
            date_col = next((c for c in shibor.columns
                             if 'date' in str(c).lower() or '日期' in str(c)), None)
            if date_col:
                shibor = shibor.rename(columns={date_col: 'date'}) if date_col != 'date' else shibor
                shibor['date'] = pd.to_datetime(shibor['date'], errors='coerce')
                shibor = shibor.dropna(subset=['date'])
                numeric = shibor.select_dtypes(include=['number']).columns.tolist()
                rename = {c: f'SHIBOR_{c}' for c in numeric}
                shibor = shibor[['date'] + numeric].rename(columns=rename)
                shibor = shibor.set_index('date')
                shibor = shibor.resample('ME').last().reset_index()
                all_data.append(shibor)

        # --- DR007 ---
        dr007 = self.fetch_dr007()
        if not dr007.empty:
            date_col = next((c for c in dr007.columns
                             if 'date' in str(c).lower() or '日期' in str(c)), None)
            if date_col:
                dr007 = dr007.rename(columns={date_col: 'date'}) if date_col != 'date' else dr007
                dr007['date'] = pd.to_datetime(dr007['date'], errors='coerce')
                dr007 = dr007.dropna(subset=['date'])
                numeric = dr007.select_dtypes(include=['number']).columns.tolist()
                rename = {c: f'DR007_{c}' for c in numeric}
                dr007 = dr007[['date'] + numeric].rename(columns=rename)
                dr007 = dr007.set_index('date')
                dr007 = dr007.resample('ME').last().reset_index()
                all_data.append(dr007)

        # --- CNH-CNY spread ---
        cnh = self.fetch_cnh_cny_spread()
        if not cnh.empty:
            date_col = next((c for c in cnh.columns
                             if 'date' in str(c).lower() or '日期' in str(c)), None)
            if date_col:
                cnh = cnh.rename(columns={date_col: 'date'}) if date_col != 'date' else cnh
                cnh['date'] = pd.to_datetime(cnh['date'], errors='coerce')
                cnh = cnh.dropna(subset=['date'])
                numeric = cnh.select_dtypes(include=['number']).columns.tolist()
                rename = {c: f'cnh_cny_{c}' for c in numeric}
                cnh = cnh[['date'] + numeric].rename(columns=rename)
                cnh = cnh.set_index('date')
                cnh = cnh.resample('ME').last().reset_index()
                all_data.append(cnh)

        # --- PBoC FX reserves ---
        fx = self.fetch_pboc_fx_reserves_monthly()
        if not fx.empty:
            date_col = next((c for c in fx.columns
                             if 'date' in str(c).lower() or '日期' in str(c)
                             or '月份' in str(c) or 'year' in str(c).lower()), None)
            if date_col:
                fx = fx.rename(columns={date_col: 'date'}) if date_col != 'date' else fx
                fx['date'] = pd.to_datetime(fx['date'], errors='coerce')
                fx = fx.dropna(subset=['date'])
                numeric = fx.select_dtypes(include=['number']).columns.tolist()
                rename = {c: f'pboc_fx_reserves_{c}' for c in numeric}
                fx = fx[['date'] + numeric].rename(columns=rename)
                fx = fx.set_index('date')
                fx = fx.resample('ME').last().reset_index()
                all_data.append(fx)

        if not all_data:
            print("  [INFO] No China money market data collected")
            return pd.DataFrame()

        result = all_data[0]
        for df in all_data[1:]:
            result = result.merge(df, on='date', how='outer')
        return result.sort_values('date').reset_index(drop=True)

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
        
        # Bond yields (use monthly normalized so columns are CN_3M, CN_6M, etc.)
        data['bond_yields'] = self.fetch_china_bond_yields_monthly()
        data['pboc_lpr'] = self.fetch_pboc_lpr()
        data['reserve_ratio'] = self.fetch_pboc_required_reserve_ratio()
        
        # Macro indicators
        data['cpi_monthly'] = self.fetch_china_cpi_monthly()
        data['ppi_monthly'] = self.fetch_china_ppi_monthly()
        data['pmi'] = self.fetch_china_pmi()
        data['services_pmi'] = self.fetch_china_services_pmi()
        data['gdp'] = self.fetch_china_gdp()
        data['money_supply'] = self.fetch_china_money_supply()
        data['trade_balance'] = self.fetch_china_trade_balance()
        data['industrial_production'] = self.fetch_china_industrial_production()
        data['business_confidence'] = self.fetch_china_business_confidence()
        
        print("\n" + "-"*60)
        print("Summary of fetched data:")
        for name, df in data.items():
            if df is not None and not df.empty:
                print(f"  {name}: {len(df)} rows, {len(df.columns)} columns")
            else:
                print(f"  {name}: No data")
        print("-"*60)
        
        return data
    
    def fetch_china_bond_yields_weekly(self) -> pd.DataFrame:
        """
        Fetch Chinese government bond yields and resample to weekly (Friday, last).
        Uses the same source as fetch_china_bond_yields_monthly.
        """
        df = self.fetch_china_bond_yields()
        if df.empty:
            return df

        date_col = next((c for c in ['日期', 'date', 'Date', 'DATE'] if c in df.columns), None)
        if date_col is None:
            print("  [ERROR] Cannot find date column in bond yields data for weekly resample")
            return pd.DataFrame()

        try:
            df['date'] = pd.to_datetime(df[date_col])
            df = df.set_index('date')
            numeric_cols = df.select_dtypes(include=['number']).columns
            weekly = df[numeric_cols].resample('W-FRI').last().reset_index()

            rename_map = {}
            for i, col in enumerate(weekly.columns):
                if col == 'date':
                    continue
                col_str = str(col).strip()
                if '0.25' in col_str or '3月' in col_str:
                    rename_map[col] = 'CN_3M'
                elif '0.5' in col_str or '6月' in col_str:
                    rename_map[col] = 'CN_6M'
                elif '1年' in col_str or col_str in ('1', '1.0'):
                    rename_map[col] = 'CN_1Y'
                elif '2年' in col_str or col_str in ('2', '2.0'):
                    rename_map[col] = 'CN_2Y'
                elif '3年' in col_str or col_str in ('3', '3.0'):
                    rename_map[col] = 'CN_3Y'
                elif '5年' in col_str or col_str in ('5', '5.0'):
                    rename_map[col] = 'CN_5Y'
                elif '7年' in col_str or col_str in ('7', '7.0'):
                    rename_map[col] = 'CN_7Y'
                elif '10年' in col_str or col_str in ('10', '10.0'):
                    rename_map[col] = 'CN_10Y'
                elif '15年' in col_str or col_str in ('15', '15.0'):
                    rename_map[col] = 'CN_15Y'
                elif '30年' in col_str or col_str in ('30', '30.0'):
                    rename_map[col] = 'CN_30Y'
                else:
                    rename_map[col] = f'CN_yield_{i}'
            if rename_map:
                weekly = weekly.rename(columns=rename_map)

            print(f"  [OK] China bond yields weekly: {len(weekly)} weeks")
            return weekly
        except Exception as e:
            print(f"  [ERROR] Error resampling to weekly: {e}")
            return pd.DataFrame()

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
            
            # Normalize yield column names to ASCII (CN_3M, CN_6M, CN_1Y, ...)
            rename_map = {}
            for i, col in enumerate(monthly.columns):
                if col == 'date':
                    continue
                col_str = str(col).strip()
                # Match common maturity patterns (Chinese "3年", "6月", or numeric 0.25, 0.5, 1, 3, 5, 7, 10, 15, 20, 30)
                if '0.25' in col_str or '3月' in col_str or '3M' in col_str.upper() or col_str == '3':
                    rename_map[col] = 'CN_3M'
                elif '0.5' in col_str or '6月' in col_str or '6M' in col_str.upper() or col_str == '6':
                    rename_map[col] = 'CN_6M'
                elif '1年' in col_str or '1Y' in col_str.upper() or col_str in ('1', '1.0'):
                    rename_map[col] = 'CN_1Y'
                elif '2年' in col_str or '2Y' in col_str.upper() or col_str in ('2', '2.0'):
                    rename_map[col] = 'CN_2Y'
                elif '3年' in col_str or '3Y' in col_str.upper() or col_str == '3':
                    rename_map[col] = 'CN_3Y'
                elif '5年' in col_str or '5Y' in col_str.upper() or col_str in ('5', '5.0'):
                    rename_map[col] = 'CN_5Y'
                elif '7年' in col_str or '7Y' in col_str.upper() or col_str in ('7', '7.0'):
                    rename_map[col] = 'CN_7Y'
                elif '10年' in col_str or '10Y' in col_str.upper() or col_str in ('10', '10.0'):
                    rename_map[col] = 'CN_10Y'
                elif '15年' in col_str or '15Y' in col_str.upper() or col_str in ('15', '15.0'):
                    rename_map[col] = 'CN_15Y'
                elif '20年' in col_str or '20Y' in col_str.upper() or col_str in ('20', '20.0'):
                    rename_map[col] = 'CN_20Y'
                elif '30年' in col_str or '30Y' in col_str.upper() or col_str in ('30', '30.0'):
                    rename_map[col] = 'CN_30Y'
                else:
                    rename_map[col] = f'CN_yield_{i}'
            if rename_map:
                monthly = monthly.rename(columns=rename_map)
            
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

