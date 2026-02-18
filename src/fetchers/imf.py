"""
IMF Fetcher - International Monetary Fund Data
==============================================
Source: https://data.imf.org/
Data: International Financial Statistics (IFS), World Economic Outlook (WEO)
Automation: Full (REST API)
Cost: Free
"""

import time
import requests
import pandas as pd
from datetime import datetime
from typing import Optional, Dict, List, Any


class IMFFetcher:
    """Fetcher for IMF data (IFS, WEO)."""
    
    BASE_URL = "https://dataservices.imf.org/REST/SDMX_JSON.svc"
    
    # Country codes
    COUNTRIES = {
        'russia': 'RUS',
        'china': 'CHN',
        'usa': 'USA',
    }
    
    # Common IFS series codes
    IFS_SERIES = {
        'PCPI_IX': 'Consumer Price Index',
        'PCPI_PC_CP_A_PT': 'CPI Inflation Rate (%)',
        'PPI_IX': 'Producer Price Index',
        'ENDA_XDC_USD_RATE': 'Exchange Rate (per USD)',
        'NGDP_R': 'Real GDP',
        'NGDP': 'Nominal GDP',
        'FITB_PA': 'Treasury Bill Rate',
        'FPOLM_PA': 'Policy Rate',
        'FILR_PA': 'Lending Rate',
        'FIDR_PA': 'Deposit Rate',
        'FM0_XDC': 'Monetary Base (M0)',
        'FM1_XDC': 'Money Supply (M1)',
        'FM2_XDC': 'Broad Money (M2)',
        'EREER_IX': 'Real Effective Exchange Rate',
        'BFXW_BP6_USD': 'International Reserves',
        # Business activity indicators
        'IP_IX': 'Industrial Production Index',
        'XGS_BP6_USD': 'Exports of Goods and Services',
        'MGS_BP6_USD': 'Imports of Goods and Services',
        'BCA_BP6_USD': 'Current Account Balance',
    }
    
    def __init__(self, timeout: int = 120):
        self.timeout = timeout
        self.session = requests.Session()
    
    def _get_with_retry(self, url: str, params: dict = None, max_retries: int = 2):
        """GET with retries on timeout/connection errors. Returns response or raises."""
        params = params or {}
        last_exc = None
        for attempt in range(max_retries + 1):
            try:
                response = self.session.get(url, params=params, timeout=self.timeout)
                return response
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                last_exc = e
                if attempt < max_retries:
                    time.sleep(2 ** (attempt + 1))
        if last_exc:
            raise last_exc
        return response
    
    # =========================================================================
    # IFS DATA
    # =========================================================================
    
    def fetch_ifs_series(self, country_code: str, series_code: str,
                         frequency: str = 'M',
                         start_year: int = 2000,
                         end_year: int = None) -> pd.DataFrame:
        """
        Fetch a single IFS series.
        
        Args:
            country_code: IMF country code (RUS, CHN, USA)
            series_code: IFS series code
            frequency: M (monthly), Q (quarterly), A (annual)
            start_year: Start year
            end_year: End year (defaults to current)
        
        Returns:
            DataFrame with date and value columns
        """
        if end_year is None:
            end_year = datetime.now().year
        
        url = f"{self.BASE_URL}/CompactData/IFS/{frequency}.{country_code}.{series_code}"
        params = {
            "startPeriod": str(start_year),
            "endPeriod": str(end_year)
        }
        
        try:
            response = self._get_with_retry(url, params)
            response.raise_for_status()
            data = response.json()
            
            # Parse response
            if "CompactData" not in data:
                return pd.DataFrame()
            
            dataset = data["CompactData"].get("DataSet", {})
            series = dataset.get("Series", {})
            
            if not series:
                return pd.DataFrame()
            
            obs = series.get("Obs", [])
            
            if not obs:
                return pd.DataFrame()
            
            # Handle single observation case
            if isinstance(obs, dict):
                obs = [obs]
            
            records = []
            for o in obs:
                time_period = o.get("@TIME_PERIOD")
                value = o.get("@OBS_VALUE")
                
                if time_period and value:
                    try:
                        # Convert time period to datetime
                        if frequency == 'M':
                            date = pd.to_datetime(time_period, format='%Y-%m')
                        elif frequency == 'Q':
                            year, quarter = time_period.split('-Q')
                            month = (int(quarter) - 1) * 3 + 1
                            date = pd.to_datetime(f"{year}-{month:02d}-01")
                        else:
                            date = pd.to_datetime(f"{time_period}-01-01")
                        
                        records.append({
                            "date": date,
                            "value": float(value)
                        })
                    except (ValueError, TypeError):
                        continue
            
            if records:
                df = pd.DataFrame(records)
                df = df.sort_values('date')
                return df
            
        except requests.exceptions.Timeout:
            print(f"  [ERROR] Timeout fetching {country_code}-{series_code}")
        except Exception as e:
            print(f"  [ERROR] Error fetching {country_code}-{series_code}: {e}")
        
        return pd.DataFrame()
    
    def fetch_multiple_ifs_series(self, country_code: str,
                                   series_codes: List[str],
                                   frequency: str = 'M',
                                   start_year: int = 2000) -> pd.DataFrame:
        """
        Fetch multiple IFS series and combine into single DataFrame.
        """
        result = None
        
        for code in series_codes:
            df = self.fetch_ifs_series(country_code, code, frequency, start_year)
            
            if df.empty:
                continue
            
            df = df.rename(columns={'value': code})
            
            if result is None:
                result = df
            else:
                result = result.merge(df, on='date', how='outer')
        
        if result is not None:
            result = result.sort_values('date')
        
        return result if result is not None else pd.DataFrame()
    
    # =========================================================================
    # RUSSIA DATA
    # =========================================================================
    
    def fetch_russia_ifs(self, start_year: int = 2000) -> pd.DataFrame:
        """
        Fetch Russian economic data from IMF IFS.
        """
        print("\nFetching Russian data from IMF IFS...")
        
        series_codes = [
            'PCPI_IX',  # CPI
            'PPI_IX',  # PPI
            'ENDA_XDC_USD_RATE',  # Exchange rate
            'FPOLM_PA',  # Policy rate
            'FM2_XDC',  # M2
        ]
        
        data = {}
        for code in series_codes:
            print(f"  Fetching {self.IFS_SERIES.get(code, code)}...")
            df = self.fetch_ifs_series('RUS', code, 'M', start_year)
            if not df.empty:
                df = df.rename(columns={'value': f'RU_{code}'})
                data[code] = df
                print(f"    [OK] {len(df)} records")
            else:
                print(f"    [ERROR] No data")
        
        # Combine all series
        if not data:
            return pd.DataFrame()
        
        result = None
        for df in data.values():
            if result is None:
                result = df
            else:
                result = result.merge(df, on='date', how='outer')
        
        return result.sort_values('date') if result is not None else pd.DataFrame()
    
    # =========================================================================
    # CHINA DATA
    # =========================================================================
    
    def fetch_china_ifs(self, start_year: int = 2000) -> pd.DataFrame:
        """
        Fetch Chinese economic data from IMF IFS.
        """
        print("\nFetching Chinese data from IMF IFS...")
        
        series_codes = [
            'PCPI_IX',  # CPI
            'PPI_IX',  # PPI
            'ENDA_XDC_USD_RATE',  # Exchange rate
            'FPOLM_PA',  # Policy rate
            'FM2_XDC',  # M2
        ]
        
        data = {}
        for code in series_codes:
            print(f"  Fetching {self.IFS_SERIES.get(code, code)}...")
            df = self.fetch_ifs_series('CHN', code, 'M', start_year)
            if not df.empty:
                df = df.rename(columns={'value': f'CN_{code}'})
                data[code] = df
                print(f"    [OK] {len(df)} records")
            else:
                print(f"    [ERROR] No data")
        
        # Combine all series
        if not data:
            return pd.DataFrame()
        
        result = None
        for df in data.values():
            if result is None:
                result = df
            else:
                result = result.merge(df, on='date', how='outer')
        
        return result.sort_values('date') if result is not None else pd.DataFrame()
    
    # =========================================================================
    # BUSINESS ACTIVITY DATA
    # =========================================================================
    
    def fetch_business_activity_ifs(self, country_code: str, start_year: int = 2000) -> pd.DataFrame:
        """
        Fetch business activity indicators from IMF IFS.
        
        Includes industrial production, trade data for both countries.
        
        Args:
            country_code: Country code ('RUS' or 'CHN')
            start_year: Start year for data
        
        Returns:
            DataFrame with business activity indicators
        """
        print(f"\nFetching business activity data from IMF IFS for {country_code}...")
        
        # Business activity series codes
        business_series = [
            'IP_IX',  # Industrial Production Index
            'XGS_BP6_USD',  # Exports of Goods and Services
            'MGS_BP6_USD',  # Imports of Goods and Services
            'BCA_BP6_USD',  # Current Account Balance
        ]
        
        data = {}
        for code in business_series:
            description = self.IFS_SERIES.get(code, code)
            print(f"  Fetching {description}...")
            df = self.fetch_ifs_series(country_code, code, 'M', start_year)
            if not df.empty:
                prefix = 'RU' if country_code == 'RUS' else 'CN'
                df = df.rename(columns={'value': f'{prefix}_{code}'})
                data[code] = df
                print(f"    [OK] {len(df)} records")
            else:
                print(f"    [ERROR] No data")
        
        # Combine all series
        if not data:
            return pd.DataFrame()
        
        result = None
        for df in data.values():
            if result is None:
                result = df
            else:
                result = result.merge(df, on='date', how='outer')
        
        return result.sort_values('date') if result is not None else pd.DataFrame()
    
    # =========================================================================
    # WEO DATA (Annual)
    # =========================================================================
    
    def fetch_weo_data(self, country_code: str, 
                       indicator_code: str) -> pd.DataFrame:
        """
        Fetch World Economic Outlook data (annual).
        Note: WEO data is typically annual and published twice a year.
        """
        url = f"{self.BASE_URL}/CompactData/WEO/A.{country_code}.{indicator_code}"
        
        try:
            response = self._get_with_retry(url)
            response.raise_for_status()
            data = response.json()
            
            dataset = data.get("CompactData", {}).get("DataSet", {})
            series = dataset.get("Series", {})
            
            if not series:
                return pd.DataFrame()
            
            obs = series.get("Obs", [])
            if isinstance(obs, dict):
                obs = [obs]
            
            records = []
            for o in obs:
                year = o.get("@TIME_PERIOD")
                value = o.get("@OBS_VALUE")
                if year and value:
                    records.append({
                        "date": pd.to_datetime(f"{year}-01-01"),
                        "value": float(value)
                    })
            
            if records:
                return pd.DataFrame(records).sort_values('date')
            
        except Exception as e:
            print(f"  [ERROR] Error fetching WEO data: {e}")
        
        return pd.DataFrame()
    
    # =========================================================================
    # AGGREGATE FETCH
    # =========================================================================
    
    def fetch_all_data(self, start_year: int = 2010) -> Dict[str, pd.DataFrame]:
        """
        Fetch all available IMF data for Russia and China.
        """
        print("\n" + "="*60)
        print(f"Fetching IMF IFS data from {start_year}")
        print("="*60)
        
        data = {
            'russia_ifs': self.fetch_russia_ifs(start_year),
            'china_ifs': self.fetch_china_ifs(start_year),
        }
        
        print("\n" + "-"*60)
        print("Summary of IMF data:")
        for name, df in data.items():
            if df is not None and not df.empty:
                print(f"  {name}: {len(df)} rows, {len(df.columns)} columns")
            else:
                print(f"  {name}: No data")
        print("-"*60)
        
        return data


# Test function
def test_imf_fetcher():
    """Test IMF fetcher functionality."""
    fetcher = IMFFetcher()
    
    # Test single series
    print("\nFetching Russia CPI from IMF...")
    df = fetcher.fetch_ifs_series('RUS', 'PCPI_IX', 'M', 2020)
    if not df.empty:
        print(f"Got {len(df)} records")
        print(df.tail())
    
    # Test China data
    print("\nFetching China data from IMF...")
    df = fetcher.fetch_china_ifs(2020)
    if not df.empty:
        print(f"Got {len(df)} records")
        print(df.columns.tolist())


if __name__ == "__main__":
    test_imf_fetcher()

