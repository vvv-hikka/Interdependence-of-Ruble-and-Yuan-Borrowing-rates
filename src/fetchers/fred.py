"""
FRED Fetcher - Federal Reserve Economic Data
=============================================
Source: https://fred.stlouisfed.org/
Data: Global macroeconomic indicators
Automation: Full (REST API)
Cost: Free (API key required)

Get API key: https://fred.stlouisfed.org/docs/api/api_key.html
"""

import time
import requests
import pandas as pd
from datetime import datetime
from typing import Optional, Dict, List
from io import StringIO

try:
    from config import FRED_OPTIONAL_SERIES, FRED_SERIES_RISK, FRED_SERIES_COMMODITIES
except ImportError:
    FRED_OPTIONAL_SERIES = frozenset()
    FRED_SERIES_RISK = {
        "VIXCLS": "CBOE VIX Volatility Index",
        "BAMLH0A0HYM2": "US High-Yield OAS (ICE BofA)",
    }
    FRED_SERIES_COMMODITIES = {
        "DHHNGSP": "Henry Hub Natural Gas Spot Price",
        "PCOPPUSDM": "Copper Price (USD/metric ton)",
    }


class FREDFetcher:
    """Fetcher for FRED (Federal Reserve Economic Data)."""
    
    BASE_URL = "https://api.stlouisfed.org/fred"
    CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
    
    SERIES_RUSSIA = {
        "RUSCPIALLMINMEI": "Russia CPI (Monthly)",
        "RUSPROINDMISMEI": "Russia Industrial Production Index",
    }
    
    SERIES_CHINA = {
        "CHNCPIALLMINMEI": "China CPI (Monthly)",
        "DEXCHUS": "USD/CNY Exchange Rate",
    }
    
    SERIES_GLOBAL = {
        "DGS10": "US 10-Year Treasury Yield",
        "DGS2": "US 2-Year Treasury Yield",
        "FEDFUNDS": "Federal Funds Rate",
        "DCOILBRENTEU": "Brent Crude Oil Price",
        "DTWEXBGS": "Trade Weighted USD Index",
        "IPMAN": "US Industrial Production: Manufacturing",
        "UMCSENT": "US Consumer Sentiment",
    }
    
    def __init__(self, api_key: str = None, timeout: int = 30):
        """
        Initialize FRED fetcher.
        
        Args:
            api_key: FRED API key (optional for CSV downloads)
            timeout: Request timeout in seconds
        """
        self.api_key = api_key
        self.timeout = timeout
        self.session = requests.Session()
    
    def set_api_key(self, api_key: str):
        """Set or update API key."""
        self.api_key = api_key
    
    def _get_with_retry(self, url: str, params: dict, max_retries: int = 3):
        """GET with retries on 502 and connection errors. Returns response or raises."""
        last_exc = None
        for attempt in range(max_retries):
            try:
                response = self.session.get(url, params=params, timeout=self.timeout)
                if response.status_code == 502 and attempt < max_retries - 1:
                    time.sleep(2 ** (attempt + 1))
                    continue
                return response
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                last_exc = e
                if attempt < max_retries - 1:
                    time.sleep(2 ** (attempt + 1))
        if last_exc:
            raise last_exc
        return response
    
    # =========================================================================
    # CSV DOWNLOAD (No API key required)
    # =========================================================================
    
    def fetch_series_csv(self, series_id: str, 
                         start_date: str = None, 
                         end_date: str = None) -> pd.DataFrame:
        """
        Fetch series data via CSV download (no API key needed).
        Retries on 502/connection errors. Returns empty DataFrame on 404 (series not found).
        """
        params = {"id": series_id}
        
        if start_date:
            params["cosd"] = start_date
        if end_date:
            params["coed"] = end_date
        
        try:
            response = self._get_with_retry(self.CSV_URL, params)
            if response.status_code == 404:
                print(f"  [SKIP] {series_id} not found (404)")
                return pd.DataFrame()
            response.raise_for_status()
            
            df = pd.read_csv(StringIO(response.text))
            
            # Standardize column names
            if len(df.columns) >= 2:
                df.columns = ['date', 'value']
                df['date'] = pd.to_datetime(df['date'])
                df['value'] = pd.to_numeric(df['value'], errors='coerce')
                df = df.dropna()
                
                if not df.empty:
                    return df
            
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                print(f"  [SKIP] {series_id} not found (404)")
            else:
                print(f"  [ERROR] Error fetching {series_id}: {e}")
        except Exception as e:
            print(f"  [ERROR] Error fetching {series_id}: {e}")
        
        return pd.DataFrame()
    
    # =========================================================================
    # API ACCESS (Requires API key)
    # =========================================================================
    
    def fetch_series_api(self, series_id: str,
                         start_date: str = None,
                         end_date: str = None,
                         frequency: str = None) -> pd.DataFrame:
        """
        Fetch series data via FRED API.
        
        Args:
            series_id: FRED series ID
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            frequency: Resample frequency (d, w, bw, m, q, sa, a)
        
        Returns:
            DataFrame with date and value columns
        """
        if not self.api_key:
            print("  ⚠ No API key set, falling back to CSV download")
            return self.fetch_series_csv(series_id, start_date, end_date)
        
        url = f"{self.BASE_URL}/series/observations"
        params = {
            "series_id": series_id,
            "api_key": self.api_key,
            "file_type": "json"
        }
        
        if start_date:
            params["observation_start"] = start_date
        if end_date:
            params["observation_end"] = end_date
        if frequency:
            params["frequency"] = frequency
        
        try:
            response = self._get_with_retry(url, params)
            response.raise_for_status()
            data = response.json()
            
            if "observations" in data:
                records = []
                for obs in data["observations"]:
                    if obs["value"] != ".":
                        records.append({
                            "date": pd.to_datetime(obs["date"]),
                            "value": float(obs["value"])
                        })
                
                if records:
                    df = pd.DataFrame(records)
                    return df
            
        except Exception as e:
            print(f"  [ERROR] Error fetching {series_id} via API: {e}")
            # Fallback to CSV
            return self.fetch_series_csv(series_id, start_date, end_date)
        
        return pd.DataFrame()
    
    def fetch_series(self, series_id: str,
                     start_date: str = None,
                     end_date: str = None) -> pd.DataFrame:
        """
        Fetch a single FRED series (auto-selects method based on API key).
        """
        if self.api_key:
            return self.fetch_series_api(series_id, start_date, end_date)
        else:
            return self.fetch_series_csv(series_id, start_date, end_date)
    
    # =========================================================================
    # RUSSIA DATA
    # =========================================================================
    
    def fetch_russia_macro(self, start_date: str = None, 
                           end_date: str = None) -> Dict[str, pd.DataFrame]:
        """
        Fetch all available Russian macroeconomic data from FRED.
        """
        print("\nFetching Russian macro data from FRED...")
        
        data = {}
        for series_id, description in self.SERIES_RUSSIA.items():
            print(f"  Fetching {description}...")
            df = self.fetch_series(series_id, start_date, end_date)
            if not df.empty:
                df = df.rename(columns={'value': series_id})
                data[series_id] = df
                print(f"    [OK] {len(df)} records")
            else:
                msg = "    [SKIP] No data" if series_id in FRED_OPTIONAL_SERIES else "    [ERROR] No data"
                print(msg)
        
        return data
    
    def fetch_russia_macro_combined(self, start_date: str = None,
                                    end_date: str = None) -> pd.DataFrame:
        """
        Fetch and combine all Russian macro data into single DataFrame.
        """
        data = self.fetch_russia_macro(start_date, end_date)
        
        if not data:
            return pd.DataFrame()
        
        # Merge all series
        result = None
        for series_id, df in data.items():
            if result is None:
                result = df
            else:
                result = result.merge(df, on='date', how='outer')
        
        if result is not None:
            result = result.sort_values('date')
        
        return result
    
    # =========================================================================
    # CHINA DATA
    # =========================================================================
    
    def fetch_china_macro(self, start_date: str = None,
                          end_date: str = None) -> Dict[str, pd.DataFrame]:
        """
        Fetch all available Chinese macroeconomic data from FRED.
        """
        print("\nFetching Chinese macro data from FRED...")
        
        data = {}
        for series_id, description in self.SERIES_CHINA.items():
            print(f"  Fetching {description}...")
            df = self.fetch_series(series_id, start_date, end_date)
            if not df.empty:
                df = df.rename(columns={'value': series_id})
                data[series_id] = df
                print(f"    [OK] {len(df)} records")
            else:
                msg = "    [SKIP] No data" if series_id in FRED_OPTIONAL_SERIES else "    [ERROR] No data"
                print(msg)
        
        return data
    
    def fetch_china_macro_combined(self, start_date: str = None,
                                   end_date: str = None) -> pd.DataFrame:
        """
        Fetch and combine all Chinese macro data into single DataFrame.
        """
        data = self.fetch_china_macro(start_date, end_date)
        
        if not data:
            return pd.DataFrame()
        
        result = None
        for series_id, df in data.items():
            if result is None:
                result = df
            else:
                result = result.merge(df, on='date', how='outer')
        
        if result is not None:
            result = result.sort_values('date')
        
        return result
    
    # =========================================================================
    # GLOBAL DATA
    # =========================================================================
    
    def fetch_global_indicators(self, start_date: str = None,
                                end_date: str = None) -> Dict[str, pd.DataFrame]:
        """
        Fetch global economic indicators (US rates, commodities, etc.)
        """
        print("\nFetching global indicators from FRED...")
        
        data = {}
        for series_id, description in self.SERIES_GLOBAL.items():
            print(f"  Fetching {description}...")
            df = self.fetch_series(series_id, start_date, end_date)
            if not df.empty:
                df = df.rename(columns={'value': series_id})
                data[series_id] = df
                print(f"    [OK] {len(df)} records")
            else:
                print(f"    [ERROR] No data")
        
        return data
    
    def fetch_global_combined(self, start_date: str = None,
                              end_date: str = None) -> pd.DataFrame:
        """
        Fetch and combine all global indicators into single DataFrame.
        """
        data = self.fetch_global_indicators(start_date, end_date)
        
        if not data:
            return pd.DataFrame()
        
        result = None
        for series_id, df in data.items():
            if result is None:
                result = df
            else:
                result = result.merge(df, on='date', how='outer')
        
        if result is not None:
            result = result.sort_values('date')
        
        return result
    
    # =========================================================================
    # RISK SENTIMENT DATA
    # =========================================================================

    def fetch_risk_combined(self, start_date: str = None,
                            end_date: str = None) -> pd.DataFrame:
        """
        Fetch risk sentiment indicators: VIX and US High-Yield OAS.
        Both are daily/weekly series resampled to monthly last.
        """
        print("\nFetching risk sentiment indicators from FRED...")

        all_data = []
        for series_id, description in FRED_SERIES_RISK.items():
            print(f"  Fetching {description}...")
            df = self.fetch_series(series_id, start_date, end_date)
            if not df.empty:
                df = df.rename(columns={'value': series_id})
                all_data.append(df)
                print(f"    [OK] {len(df)} records")
            else:
                print(f"    [ERROR] No data for {series_id}")

        if not all_data:
            return pd.DataFrame()

        result = all_data[0]
        for df in all_data[1:]:
            result = result.merge(df, on='date', how='outer')

        result = result.sort_values('date')
        return self.resample_to_monthly(result)

    # =========================================================================
    # COMMODITIES DATA
    # =========================================================================

    def fetch_commodities_combined(self, start_date: str = None,
                                   end_date: str = None) -> pd.DataFrame:
        """
        Fetch commodity prices: Henry Hub natural gas and copper.
        Resampled to monthly last.
        """
        print("\nFetching commodity prices from FRED...")

        all_data = []
        for series_id, description in FRED_SERIES_COMMODITIES.items():
            print(f"  Fetching {description}...")
            df = self.fetch_series(series_id, start_date, end_date)
            if not df.empty:
                df = df.rename(columns={'value': series_id})
                all_data.append(df)
                print(f"    [OK] {len(df)} records")
            else:
                print(f"    [ERROR] No data for {series_id}")

        if not all_data:
            return pd.DataFrame()

        result = all_data[0]
        for df in all_data[1:]:
            result = result.merge(df, on='date', how='outer')

        result = result.sort_values('date')
        return self.resample_to_monthly(result)

    # =========================================================================
    # BUSINESS ACTIVITY DATA
    # =========================================================================
    
    def fetch_business_activity_combined(self, start_date: str = None,
                                         end_date: str = None) -> pd.DataFrame:
        """
        Fetch business activity indicators from FRED.
        Only series that are known to be available (no discontinued ones).
        """
        print("\nFetching business activity indicators from FRED...")
        
        series = {
            "RUSPROINDMISMEI": ("Russia Industrial Production", "RU_RUSPROINDMISMEI"),
            "IPMAN": ("US Industrial Production: Manufacturing", "IPMAN"),
            "UMCSENT": ("US Consumer Sentiment", "UMCSENT"),
        }
        
        all_data = []
        for series_id, (description, col_name) in series.items():
            print(f"  Fetching {description}...")
            df = self.fetch_series(series_id, start_date, end_date)
            if not df.empty:
                df = df.rename(columns={'value': col_name})
                all_data.append(df)
                print(f"    [OK] {len(df)} records")
        
        if not all_data:
            return pd.DataFrame()
        
        result = all_data[0]
        for df in all_data[1:]:
            result = result.merge(df, on='date', how='outer')
        
        result = result.sort_values('date')
        return self.resample_to_monthly(result)
    
    # =========================================================================
    # RESAMPLE HELPERS
    # =========================================================================

    def resample_to_weekly(self, df: pd.DataFrame,
                           date_col: str = 'date') -> pd.DataFrame:
        """Resample DataFrame to weekly frequency (Friday week-end, last value)."""
        if df.empty:
            return df
        df = df.set_index(date_col)
        numeric_cols = df.select_dtypes(include=['number']).columns
        weekly = df[numeric_cols].resample('W-FRI').last().reset_index()
        return weekly

    def fetch_global_weekly(self, start_date: str = None,
                            end_date: str = None) -> pd.DataFrame:
        """
        Fetch daily FRED global indicators and resample to weekly.
        Covers series that update at daily/weekly frequency and are most
        useful for weekly signal work: US yields, Brent, USD index.
        """
        weekly_series = {
            "DGS10": "US 10-Year Treasury Yield",
            "DGS2": "US 2-Year Treasury Yield",
            "DCOILBRENTEU": "Brent Crude Oil Price",
            "DTWEXBGS": "Trade Weighted USD Index",
        }
        print("\nFetching weekly global indicators from FRED...")
        all_data = []
        for series_id, description in weekly_series.items():
            print(f"  Fetching {description}...")
            df = self.fetch_series(series_id, start_date, end_date)
            if not df.empty:
                df = df.rename(columns={'value': series_id})
                all_data.append(df)
                print(f"    [OK] {len(df)} records")
            else:
                print(f"    [ERROR] No data for {series_id}")
        if not all_data:
            return pd.DataFrame()
        result = all_data[0]
        for df in all_data[1:]:
            result = result.merge(df, on='date', how='outer')
        return self.resample_to_weekly(result.sort_values('date'))

    def fetch_risk_weekly(self, start_date: str = None,
                          end_date: str = None) -> pd.DataFrame:
        """Fetch VIX and US HY OAS resampled to weekly frequency."""
        print("\nFetching weekly risk sentiment indicators from FRED...")
        all_data = []
        for series_id, description in FRED_SERIES_RISK.items():
            print(f"  Fetching {description}...")
            df = self.fetch_series(series_id, start_date, end_date)
            if not df.empty:
                df = df.rename(columns={'value': series_id})
                all_data.append(df)
                print(f"    [OK] {len(df)} records")
            else:
                print(f"    [ERROR] No data for {series_id}")
        if not all_data:
            return pd.DataFrame()
        result = all_data[0]
        for df in all_data[1:]:
            result = result.merge(df, on='date', how='outer')
        return self.resample_to_weekly(result.sort_values('date'))

    # =========================================================================
    # RESAMPLE TO MONTHLY
    # =========================================================================

    def resample_to_monthly(self, df: pd.DataFrame,
                            date_col: str = 'date') -> pd.DataFrame:
        """
        Resample DataFrame to monthly frequency.
        """
        if df.empty:
            return df
        
        df = df.set_index(date_col)
        numeric_cols = df.select_dtypes(include=['number']).columns
        monthly = df[numeric_cols].resample('ME').last().reset_index()
        
        return monthly
    
    # =========================================================================
    # AGGREGATE FETCH
    # =========================================================================
    
    def fetch_all_data(self, start_date: str = "2015-01-01",
                       end_date: str = None) -> Dict[str, pd.DataFrame]:
        """
        Fetch all available data from FRED.
        """
        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")
        
        print("\n" + "="*60)
        print(f"Fetching all FRED data from {start_date} to {end_date}")
        print("="*60)
        
        data = {
            'russia': self.fetch_russia_macro_combined(start_date, end_date),
            'china': self.fetch_china_macro_combined(start_date, end_date),
            'global': self.fetch_global_combined(start_date, end_date),
        }
        
        # Resample to monthly
        for key in data:
            if data[key] is not None and not data[key].empty:
                data[key] = self.resample_to_monthly(data[key])
        
        print("\n" + "-"*60)
        print("Summary of FRED data:")
        for name, df in data.items():
            if df is not None and not df.empty:
                print(f"  {name}: {len(df)} rows, {len(df.columns)} columns")
            else:
                print(f"  {name}: No data")
        print("-"*60)
        
        return data


# Test function
def test_fred_fetcher():
    """Test FRED fetcher functionality."""
    fetcher = FREDFetcher()  # No API key, will use CSV download
    
    # Test single series
    print("\nFetching US 10Y Treasury Yield...")
    df = fetcher.fetch_series("DGS10", "2024-01-01")
    if not df.empty:
        print(f"Got {len(df)} records")
        print(df.tail())
    
    # Test Russia CPI
    print("\nFetching Russia CPI...")
    df = fetcher.fetch_series("RUSCPIALLMINMEI", "2020-01-01")
    if not df.empty:
        print(f"Got {len(df)} records")
        print(df.tail())
    
    # Test China data
    print("\nFetching China data...")
    data = fetcher.fetch_china_macro("2020-01-01")
    for name, df in data.items():
        print(f"  {name}: {len(df)} records" if not df.empty else f"  {name}: No data")


if __name__ == "__main__":
    test_fred_fetcher()

