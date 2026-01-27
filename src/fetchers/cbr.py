"""
CBR Fetcher - Bank of Russia data
=================================
Source: https://www.cbr.ru/
Data: Key rate, yield curves, currency rates, macro indicators
Automation: Full (XML/HTML API)
Cost: Free
"""

import requests
import pandas as pd
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from io import StringIO
import re


class CBRFetcher:
    """Fetcher for Bank of Russia (CBR) data."""
    
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
    
    # =========================================================================
    # KEY RATE
    # =========================================================================
    
    def fetch_key_rate(self) -> pd.DataFrame:
        """
        Fetch CBR key interest rate history.
        Returns DataFrame with date and rate columns.
        """
        url = "https://www.cbr.ru/scripts/XML_KeyRate.asp"
        
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            
            # Try to fix malformed XML
            content = response.content
            
            # Try parsing
            try:
                root = ET.fromstring(content)
            except ET.ParseError:
                # Try to decode and fix common issues
                text = content.decode('windows-1251', errors='ignore')
                # Remove problematic tags
                text = re.sub(r'<br\s*/?>', '', text)
                text = re.sub(r'&\w+;', '', text)
                try:
                    root = ET.fromstring(text.encode('utf-8'))
                except ET.ParseError:
                    # Last resort: parse HTML-style
                    print("  ! XML parse failed, trying alternative method")
                    return self._fetch_key_rate_html()
            
            records = []
            for record in root.findall('.//Record'):
                date_str = record.get('Date')
                rate_elem = record.find('Rate')
                
                if date_str and rate_elem is not None and rate_elem.text:
                    try:
                        date = datetime.strptime(date_str, '%d.%m.%Y')
                        rate = float(rate_elem.text.replace(',', '.'))
                        records.append({'date': date, 'cbr_key_rate': rate})
                    except (ValueError, TypeError):
                        continue
            
            if records:
                df = pd.DataFrame(records)
                df = df.sort_values('date')
                print(f"  [OK] CBR key rate: {len(df)} records")
                return df
            
        except Exception as e:
            print(f"  [ERROR] Error fetching CBR key rate: {e}")
        
        return pd.DataFrame()
    
    def _fetch_key_rate_html(self) -> pd.DataFrame:
        """Alternative method: fetch key rate from HTML page with full history."""
        # Use the full history page with date range
        url = "https://www.cbr.ru/hd_base/KeyRate/"
        
        try:
            # Request full history
            params = {
                "UniDbQuery.Posted": "True",
                "UniDbQuery.From": "01.01.2013",
                "UniDbQuery.To": datetime.now().strftime("%d.%m.%Y")
            }
            
            response = self.session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            
            tables = pd.read_html(StringIO(response.text), decimal=',', thousands=' ')
            
            if tables:
                df = tables[0]
                # Try to identify date and rate columns
                if len(df.columns) >= 2:
                    df.columns = ['date', 'cbr_key_rate'] + list(df.columns[2:]) if len(df.columns) > 2 else ['date', 'cbr_key_rate']
                    
                    df['date'] = pd.to_datetime(df['date'], dayfirst=True, errors='coerce')
                    df['cbr_key_rate'] = pd.to_numeric(df['cbr_key_rate'], errors='coerce')
                    df = df[['date', 'cbr_key_rate']].dropna()
                    df = df.sort_values('date')
                    
                    print(f"  [OK] CBR key rate (HTML): {len(df)} records")
                    return df
            
        except Exception as e:
            print(f"  [ERROR] HTML fetch failed: {e}")
        
        # Final fallback: use embedded key rate data
        return self._get_embedded_key_rate()
    
    def _get_embedded_key_rate(self) -> pd.DataFrame:
        """Return embedded CBR key rate history as fallback."""
        # Historical CBR key rate data (official values)
        data = """date,cbr_key_rate
2013-09-13,5.5
2014-03-03,7.0
2014-04-28,7.5
2014-07-28,8.0
2014-11-05,9.5
2014-12-12,10.5
2014-12-16,17.0
2015-02-02,15.0
2015-03-16,14.0
2015-05-05,12.5
2015-06-16,11.5
2015-08-03,11.0
2016-06-14,10.5
2016-09-19,10.0
2017-03-27,9.75
2017-05-02,9.25
2017-06-19,9.0
2017-09-18,8.5
2017-10-30,8.25
2017-12-18,7.75
2018-02-12,7.5
2018-03-26,7.25
2018-09-17,7.5
2018-12-17,7.75
2019-06-17,7.5
2019-07-29,7.25
2019-09-09,7.0
2019-10-28,6.5
2019-12-16,6.25
2020-02-10,6.0
2020-04-27,5.5
2020-06-22,4.5
2020-07-27,4.25
2021-03-22,4.5
2021-04-26,5.0
2021-06-15,5.5
2021-07-26,6.5
2021-09-13,6.75
2021-10-25,7.5
2021-12-20,8.5
2022-02-28,20.0
2022-04-11,17.0
2022-05-04,14.0
2022-06-14,9.5
2022-07-25,8.0
2022-09-19,7.5
2023-07-24,8.5
2023-08-15,12.0
2023-09-18,13.0
2023-10-30,15.0
2023-12-18,16.0
2024-02-16,16.0
2024-07-26,18.0
2024-09-13,19.0
2024-10-25,21.0
"""
        df = pd.read_csv(StringIO(data), parse_dates=['date'])
        df = df.sort_values('date')
        print(f"  [OK] CBR key rate (embedded): {len(df)} records")
        return df
    
    def fetch_key_rate_monthly(self) -> pd.DataFrame:
        """
        Fetch CBR key rate and resample to monthly (last value of month).
        """
        df = self.fetch_key_rate()
        if df.empty:
            return df
        
        df = df.set_index('date')
        monthly = df.resample('ME').last().reset_index()
        monthly = monthly.ffill()
        
        print(f"  [OK] Monthly key rate: {len(monthly)} months")
        return monthly
    
    # =========================================================================
    # G-CURVE (ZERO-COUPON YIELD CURVE)
    # =========================================================================
    
    def fetch_gcurve_params(self, date_from: str, date_to: str) -> pd.DataFrame:
        """
        Fetch G-Curve (zero-coupon yield curve) parameters from CBR.
        
        Args:
            date_from: Start date (DD.MM.YYYY)
            date_to: End date (DD.MM.YYYY)
        
        Returns:
            DataFrame with Nelson-Siegel-Svensson parameters
        """
        url = "https://www.cbr.ru/hd_base/zcyc_params/zcyc/"
        
        params = {
            "UniDbQuery.Posted": "True",
            "UniDbQuery.From": date_from,
            "UniDbQuery.To": date_to
        }
        
        try:
            response = self.session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            
            # Parse HTML tables
            tables = pd.read_html(StringIO(response.text), decimal=',', thousands=' ')
            
            if tables and len(tables) > 0:
                df = tables[0]
                print(f"  [OK] G-Curve params: {len(df)} records")
                return df
            
        except Exception as e:
            print(f"  [ERROR] Error fetching G-Curve params: {e}")
        
        return pd.DataFrame()
    
    def fetch_gcurve_yields(self, date_from: str, date_to: str) -> pd.DataFrame:
        """
        Fetch G-Curve yields for standard maturities from CBR.
        
        Args:
            date_from: Start date (DD.MM.YYYY)
            date_to: End date (DD.MM.YYYY)
        """
        url = "https://www.cbr.ru/hd_base/zcyc_params/"
        
        params = {
            "UniDbQuery.Posted": "True",
            "UniDbQuery.From": date_from,
            "UniDbQuery.To": date_to
        }
        
        try:
            response = self.session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            
            tables = pd.read_html(StringIO(response.text), decimal=',', thousands=' ')
            
            if tables and len(tables) > 0:
                df = tables[0]
                print(f"  [OK] G-Curve yields: {len(df)} records")
                return df
            
        except Exception as e:
            print(f"  [ERROR] Error fetching G-Curve yields: {e}")
        
        return pd.DataFrame()
    
    def fetch_gcurve_monthly(self, start_year: int = 2015) -> pd.DataFrame:
        """
        Fetch G-Curve parameters with monthly sampling.
        Fetches year by year to avoid timeouts with large date ranges.
        """
        end_date = datetime.now()
        start_date = datetime(start_year, 1, 1)
        
        print(f"\nFetching G-Curve from {start_year} to {end_date.year}...")
        
        all_data = []
        
        # Fetch year by year to avoid timeouts
        for year in range(start_year, end_date.year + 1):
            year_start = f"01.01.{year}"
            year_end = f"31.12.{year}" if year < end_date.year else end_date.strftime("%d.%m.%Y")
            
            print(f"  Fetching {year}...")
            df = self.fetch_gcurve_yields(year_start, year_end)
            
            if not df.empty:
                all_data.append(df)
                print(f"    Got {len(df)} records")
        
        if not all_data:
            print("  [ERROR] No G-Curve data fetched, using embedded data")
            return self._get_embedded_gcurve()
        
        # Combine all years
        combined = pd.concat(all_data, ignore_index=True)
        
        # Find date column (first column usually)
        date_col = combined.columns[0]
        
        try:
            combined['date'] = pd.to_datetime(combined[date_col], dayfirst=True, errors='coerce')
            combined = combined.dropna(subset=['date'])
            combined = combined.set_index('date')
            
            # Get numeric columns (yield values for different maturities)
            numeric_cols = combined.select_dtypes(include=['number']).columns
            
            # Resample to monthly (last value)
            monthly = combined[numeric_cols].resample('ME').last().reset_index()
            
            # Rename columns to standard format
            new_cols = {'date': 'date'}
            for col in monthly.columns:
                if col == 'date':
                    continue
                # Try to extract maturity from column name
                col_str = str(col)
                if '0.25' in col_str or '3м' in col_str.lower():
                    new_cols[col] = 'RU_3M'
                elif '0.5' in col_str or '6м' in col_str.lower():
                    new_cols[col] = 'RU_6M'
                elif '1.00' in col_str or '1' == col_str or '1год' in col_str.lower():
                    new_cols[col] = 'RU_1Y'
                elif '2.00' in col_str or '2' == col_str:
                    new_cols[col] = 'RU_2Y'
                elif '3.00' in col_str or '3' == col_str:
                    new_cols[col] = 'RU_3Y'
                elif '5.00' in col_str or '5' == col_str:
                    new_cols[col] = 'RU_5Y'
                elif '7.00' in col_str or '7' == col_str:
                    new_cols[col] = 'RU_7Y'
                elif '10.00' in col_str or '10' == col_str:
                    new_cols[col] = 'RU_10Y'
                elif '15.00' in col_str or '15' == col_str:
                    new_cols[col] = 'RU_15Y'
                elif '20.00' in col_str or '20' == col_str:
                    new_cols[col] = 'RU_20Y'
                elif '30.00' in col_str or '30' == col_str:
                    new_cols[col] = 'RU_30Y'
            
            monthly = monthly.rename(columns=new_cols)
            
            print(f"  [OK] Monthly G-Curve: {len(monthly)} months")
            return monthly
        except Exception as e:
            print(f"  [ERROR] Error processing G-Curve: {e}")
            return self._get_embedded_gcurve()
    
    def _get_embedded_gcurve(self) -> pd.DataFrame:
        """Return placeholder G-Curve structure."""
        dates = pd.date_range('2015-01-01', datetime.now(), freq='ME')
        return pd.DataFrame({
            'date': dates,
            'RU_1Y': [None] * len(dates),
            'RU_3Y': [None] * len(dates),
            'RU_5Y': [None] * len(dates),
            'RU_10Y': [None] * len(dates),
        })
    
    # =========================================================================
    # CURRENCY RATES
    # =========================================================================
    
    def fetch_currency_rate(self, currency_code: str, 
                           date_from: str = None, date_to: str = None) -> pd.DataFrame:
        """
        Fetch currency exchange rate from CBR.
        
        Args:
            currency_code: CBR internal code (R01235=USD, R01375=CNY, R01239=EUR)
            date_from: Start date (DD/MM/YYYY)
            date_to: End date (DD/MM/YYYY)
        
        Returns:
            DataFrame with date and rate columns
        """
        if date_from is None:
            date_from = "01/01/2015"
        if date_to is None:
            date_to = datetime.now().strftime("%d/%m/%Y")
        
        url = "https://www.cbr.ru/scripts/XML_dynamic.asp"
        params = {
            "date_req1": date_from,
            "date_req2": date_to,
            "VAL_NM_RQ": currency_code
        }
        
        try:
            response = self.session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            
            root = ET.fromstring(response.content)
            
            records = []
            for record in root.findall('.//Record'):
                date_str = record.get('Date')
                value_elem = record.find('Value')
                nominal_elem = record.find('Nominal')
                
                if date_str and value_elem is not None:
                    try:
                        date = datetime.strptime(date_str, '%d.%m.%Y')
                        value = float(value_elem.text.replace(',', '.'))
                        nominal = int(nominal_elem.text) if nominal_elem is not None else 1
                        rate = value / nominal
                        records.append({'date': date, 'rate': rate})
                    except (ValueError, TypeError):
                        continue
            
            if records:
                df = pd.DataFrame(records)
                df = df.sort_values('date')
                return df
            
        except Exception as e:
            print(f"  [ERROR] Error fetching currency rate: {e}")
        
        return pd.DataFrame()
    
    def fetch_usd_rate(self, date_from: str = None, date_to: str = None) -> pd.DataFrame:
        """Fetch USD/RUB rate."""
        print("  Fetching USD/RUB rate...")
        df = self.fetch_currency_rate("R01235", date_from, date_to)
        if not df.empty:
            df = df.rename(columns={'rate': 'usd_rub'})
            print(f"  [OK] USD/RUB: {len(df)} records")
        return df
    
    def fetch_cny_rate(self, date_from: str = None, date_to: str = None) -> pd.DataFrame:
        """Fetch CNY/RUB rate."""
        print("  Fetching CNY/RUB rate...")
        df = self.fetch_currency_rate("R01375", date_from, date_to)
        if not df.empty:
            df = df.rename(columns={'rate': 'cny_rub'})
            print(f"  [OK] CNY/RUB: {len(df)} records")
        return df
    
    def fetch_eur_rate(self, date_from: str = None, date_to: str = None) -> pd.DataFrame:
        """Fetch EUR/RUB rate."""
        print("  Fetching EUR/RUB rate...")
        df = self.fetch_currency_rate("R01239", date_from, date_to)
        if not df.empty:
            df = df.rename(columns={'rate': 'eur_rub'})
            print(f"  [OK] EUR/RUB: {len(df)} records")
        return df
    
    def fetch_all_currency_rates_monthly(self) -> pd.DataFrame:
        """
        Fetch all main currency rates and resample to monthly.
        """
        print("\nFetching CBR currency rates...")
        
        usd = self.fetch_usd_rate()
        cny = self.fetch_cny_rate()
        eur = self.fetch_eur_rate()
        
        # Merge all rates
        rates = None
        
        for df in [usd, cny, eur]:
            if df.empty:
                continue
            if rates is None:
                rates = df
            else:
                rates = rates.merge(df, on='date', how='outer')
        
        if rates is None or rates.empty:
            return pd.DataFrame()
        
        # Resample to monthly
        rates = rates.set_index('date')
        monthly = rates.resample('ME').last().reset_index()
        
        print(f"  [OK] Monthly currency rates: {len(monthly)} months")
        return monthly
    
    # =========================================================================
    # MACROECONOMIC INDICATORS
    # =========================================================================
    
    def fetch_inflation_targets(self) -> pd.DataFrame:
        """
        Fetch CBR inflation targets (note: this is target, not actual inflation).
        """
        # CBR inflation target has been 4% since 2017
        years = list(range(2015, datetime.now().year + 1))
        targets = []
        for year in years:
            if year < 2017:
                target = 4.0  # Transitional period
            else:
                target = 4.0  # Official target
            targets.append({'year': year, 'inflation_target': target})
        
        return pd.DataFrame(targets)
    
    # =========================================================================
    # AGGREGATE FETCH
    # =========================================================================
    
    def fetch_all_cbr_data(self) -> Dict[str, pd.DataFrame]:
        """
        Fetch all available CBR data.
        """
        print("\n" + "="*60)
        print("Fetching all CBR data...")
        print("="*60)
        
        data = {}
        
        # Key rate
        data['key_rate'] = self.fetch_key_rate()
        data['key_rate_monthly'] = self.fetch_key_rate_monthly()
        
        # G-Curve
        data['gcurve'] = self.fetch_gcurve_monthly()
        
        # Currency rates
        data['currency_rates'] = self.fetch_all_currency_rates_monthly()
        
        print("\n" + "-"*60)
        print("Summary of CBR data:")
        for name, df in data.items():
            if df is not None and not df.empty:
                print(f"  {name}: {len(df)} rows")
            else:
                print(f"  {name}: No data")
        print("-"*60)
        
        return data


# Test function
def test_cbr_fetcher():
    """Test CBR fetcher functionality."""
    fetcher = CBRFetcher()
    
    # Test key rate
    print("\nFetching CBR key rate...")
    key_rate = fetcher.fetch_key_rate()
    if not key_rate.empty:
        print(f"Got {len(key_rate)} records")
        print(key_rate.tail())
    
    # Test G-Curve
    print("\nFetching G-Curve...")
    gcurve = fetcher.fetch_gcurve_params("01.01.2024", "31.12.2024")
    if not gcurve.empty:
        print(gcurve.head())
    
    # Test currency rates
    print("\nFetching USD/RUB rate...")
    usd = fetcher.fetch_usd_rate("01/01/2024", "31/12/2024")
    if not usd.empty:
        print(usd.tail())


if __name__ == "__main__":
    test_cbr_fetcher()

