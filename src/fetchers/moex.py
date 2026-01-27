"""
MOEX ISS Fetcher - Moscow Exchange data
=======================================
Source: https://iss.moex.com/
Data: Russian bonds, OFZ yields, market data
Automation: Full (HTTP API)
Cost: Free (with delay, real-time requires subscription)
"""

import requests
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import time


class MOEXFetcher:
    """Fetcher for Russian financial data from Moscow Exchange ISS API."""
    
    BASE_URL = "https://iss.moex.com/iss"
    
    # Updated OFZ benchmark bonds (checked for current trading status - Jan 2026)
    # Format: {maturity: [list of ISINs to try]}
    OFZ_BONDS = {
        "2Y": ["SU26226RMFS9", "SU26233RMFS5", "SU26231RMFS9"],
        "3Y": ["SU26232RMFS7", "SU26230RMFS1", "SU26224RMFS4"],
        "5Y": ["SU26235RMFS0", "SU26236RMFS8", "SU26225RMFS1"],
        "7Y": ["SU26237RMFS6", "SU26221RMFS0", "SU26207RMFS9"],
        "10Y": ["SU26238RMFS4", "SU26240RMFS0", "SU26241RMFS8", "SU26228RMFS5"],
        "15Y": ["SU26239RMFS2", "SU26212RMFS9", "SU26218RMFS6"],
        "20Y": ["SU26242RMFS6", "SU26219RMFS4", "SU26243RMFS4"],
    }
    
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.session = requests.Session()
    
    def _make_request(self, endpoint: str, params: dict = None) -> dict:
        """Make API request with error handling."""
        url = f"{self.BASE_URL}/{endpoint}"
        try:
            response = self.session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"  [ERROR] Request error: {e}")
            return {}
    
    # =========================================================================
    # SECURITIES SEARCH
    # =========================================================================
    
    def search_securities(self, query: str) -> pd.DataFrame:
        """
        Search for securities by name/ticker.
        Example: search_securities("ОФЗ") for government bonds
        """
        endpoint = "securities.json"
        params = {"q": query, "limit": 100}
        
        data = self._make_request(endpoint, params)
        if not data or "securities" not in data:
            return pd.DataFrame()
        
        cols = data["securities"]["columns"]
        rows = data["securities"]["data"]
        
        if not rows:
            return pd.DataFrame()
        
        return pd.DataFrame([dict(zip(cols, row)) for row in rows])
    
    def get_security_info(self, secid: str) -> Dict[str, Any]:
        """Get detailed information about a security."""
        endpoint = f"securities/{secid}.json"
        data = self._make_request(endpoint)
        
        if not data:
            return {}
        
        result = {}
        for section in ["description", "boards"]:
            if section in data and data[section].get("data"):
                cols = data[section]["columns"]
                rows = data[section]["data"]
                result[section] = [dict(zip(cols, row)) for row in rows]
        
        return result
    
    # =========================================================================
    # BOND HISTORICAL DATA
    # =========================================================================
    
    def fetch_bond_history(self, secid: str, from_date: str, to_date: str) -> pd.DataFrame:
        """
        Fetch historical data for a specific bond.
        
        Args:
            secid: Security ID (e.g., "SU26238RMFS3")
            from_date: Start date (YYYY-MM-DD)
            to_date: End date (YYYY-MM-DD)
        
        Returns:
            DataFrame with historical price/yield data
        """
        endpoint = f"history/engines/stock/markets/bonds/securities/{secid}.json"
        all_data = []
        start = 0
        
        while True:
            params = {
                "from": from_date,
                "till": to_date,
                "start": start,
                "limit": 100
            }
            
            data = self._make_request(endpoint, params)
            
            if not data or "history" not in data:
                break
            
            cols = data["history"]["columns"]
            rows = data["history"]["data"]
            
            if not rows:
                break
            
            all_data.extend([dict(zip(cols, row)) for row in rows])
            start += 100
            
            if len(rows) < 100:
                break
            
            time.sleep(0.1)  # Rate limiting
        
        if not all_data:
            return pd.DataFrame()
        
        df = pd.DataFrame(all_data)
        
        # Convert date column
        if "TRADEDATE" in df.columns:
            df["date"] = pd.to_datetime(df["TRADEDATE"])
        
        return df
    
    def fetch_bond_candles(self, secid: str, from_date: str, to_date: str, 
                          interval: int = 24) -> pd.DataFrame:
        """
        Fetch candle data for a bond.
        
        Args:
            secid: Security ID
            from_date: Start date (YYYY-MM-DD)
            to_date: End date (YYYY-MM-DD)
            interval: Candle interval (24 = daily)
        """
        endpoint = f"engines/stock/markets/bonds/securities/{secid}/candles.json"
        params = {
            "from": from_date,
            "till": to_date,
            "interval": interval
        }
        
        data = self._make_request(endpoint, params)
        
        if not data or "candles" not in data:
            return pd.DataFrame()
        
        cols = data["candles"]["columns"]
        rows = data["candles"]["data"]
        
        if not rows:
            return pd.DataFrame()
        
        df = pd.DataFrame([dict(zip(cols, row)) for row in rows])
        
        if "begin" in df.columns:
            df["date"] = pd.to_datetime(df["begin"])
        
        return df
    
    # =========================================================================
    # OFZ YIELDS
    # =========================================================================
    
    def fetch_ofz_yields(self, from_date: str = None, to_date: str = None) -> pd.DataFrame:
        """
        Fetch OFZ yields for different maturities.
        
        Returns DataFrame with yields for 1Y, 2Y, 3Y, 5Y, 7Y, 10Y, 15Y maturities.
        """
        if from_date is None:
            from_date = "2015-01-01"
        if to_date is None:
            to_date = datetime.now().strftime("%Y-%m-%d")
        
        print(f"\nFetching OFZ yields from {from_date} to {to_date}...")
        
        all_yields = []
        
        for maturity, secids in self.OFZ_BONDS.items():
            print(f"  Trying {maturity} maturity bonds...")
            
            for secid in secids:
                df = self.fetch_bond_history(secid, from_date, to_date)
                
                if df.empty:
                    continue
                
                # Look for yield column
                yield_col = None
                for col in ["YIELDCLOSE", "YIELD", "YIELDLASTCOUPON", "YIELDATWAPRICE", "YIELDTOPREVYIELD"]:
                    if col in df.columns:
                        yield_col = col
                        break
                
                if yield_col is None:
                    print(f"    [ERROR] {secid}: No yield column found")
                    continue
                
                # Filter valid data
                df = df[["date", yield_col]].dropna()
                df = df[df[yield_col] > 0]  # Remove zero/negative yields
                
                if df.empty:
                    print(f"    [ERROR] {secid}: No valid yield data")
                    continue
                
                df["yield"] = pd.to_numeric(df[yield_col], errors="coerce")
                df["maturity"] = maturity
                df["secid"] = secid
                df = df[["date", "yield", "maturity", "secid"]]
                
                all_yields.append(df)
                print(f"    [OK] {secid}: {len(df)} records")
                break  # Got data for this maturity
        
        if not all_yields:
            print("  [ERROR] No OFZ yield data fetched")
            return pd.DataFrame()
        
        result = pd.concat(all_yields, ignore_index=True)
        print(f"\n  Total: {len(result)} yield records across {result['maturity'].nunique()} maturities")
        return result
    
    def fetch_ofz_yields_monthly(self, from_date: str = None, to_date: str = None) -> pd.DataFrame:
        """
        Fetch OFZ yields and resample to monthly frequency.
        Returns pivoted DataFrame with maturities as columns.
        """
        df = self.fetch_ofz_yields(from_date, to_date)
        
        if df.empty:
            return pd.DataFrame()
        
        # Resample to monthly (average)
        df["month"] = df["date"].dt.to_period("M")
        monthly = df.groupby(["month", "maturity"]).agg({"yield": "mean"}).reset_index()
        monthly["date"] = monthly["month"].dt.to_timestamp()
        
        # Pivot to wide format
        wide = monthly.pivot(index="date", columns="maturity", values="yield")
        wide.columns = [f"RU_{col}" for col in wide.columns]
        wide = wide.reset_index()
        
        print(f"  [OK] Monthly OFZ yields: {len(wide)} months")
        return wide
    
    # =========================================================================
    # MARKET DATA
    # =========================================================================
    
    def fetch_bond_market_data(self) -> pd.DataFrame:
        """
        Fetch current bond market data (all traded bonds).
        """
        endpoint = "engines/stock/markets/bonds/securities.json"
        data = self._make_request(endpoint)
        
        if not data or "securities" not in data:
            return pd.DataFrame()
        
        cols = data["securities"]["columns"]
        rows = data["securities"]["data"]
        
        if not rows:
            return pd.DataFrame()
        
        return pd.DataFrame([dict(zip(cols, row)) for row in rows])
    
    def fetch_index_history(self, index_id: str, from_date: str, to_date: str) -> pd.DataFrame:
        """
        Fetch historical data for a MOEX index.
        
        Args:
            index_id: Index ticker (e.g., "RGBI" for government bond index)
            from_date: Start date (YYYY-MM-DD)
            to_date: End date (YYYY-MM-DD)
        """
        endpoint = f"history/engines/stock/markets/index/securities/{index_id}.json"
        all_data = []
        start = 0
        
        while True:
            params = {
                "from": from_date,
                "till": to_date,
                "start": start,
                "limit": 100
            }
            
            data = self._make_request(endpoint, params)
            
            if not data or "history" not in data:
                break
            
            cols = data["history"]["columns"]
            rows = data["history"]["data"]
            
            if not rows:
                break
            
            all_data.extend([dict(zip(cols, row)) for row in rows])
            start += 100
            
            if len(rows) < 100:
                break
        
        if not all_data:
            return pd.DataFrame()
        
        df = pd.DataFrame(all_data)
        if "TRADEDATE" in df.columns:
            df["date"] = pd.to_datetime(df["TRADEDATE"])
        
        return df
    
    def fetch_rgbi_index(self, from_date: str = None, to_date: str = None) -> pd.DataFrame:
        """
        Fetch RGBI (Russian Government Bond Index) history.
        """
        if from_date is None:
            from_date = "2015-01-01"
        if to_date is None:
            to_date = datetime.now().strftime("%Y-%m-%d")
        
        print(f"\nFetching RGBI index from {from_date} to {to_date}...")
        
        df = self.fetch_index_history("RGBI", from_date, to_date)
        
        if df.empty:
            print("  [ERROR] No RGBI data")
            return df
        
        print(f"  [OK] RGBI index: {len(df)} records")
        return df
    
    # =========================================================================
    # YIELD CURVES (ZCYC)
    # =========================================================================
    
    def fetch_zcyc(self, date: str = None) -> pd.DataFrame:
        """
        Fetch zero-coupon yield curve data.
        Note: MOEX stopped publishing ZCYC data in 2018.
        For current data, use CBR G-Curve instead.
        """
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        
        endpoint = "engines/stock/zcyc.json"
        params = {"date": date}
        
        data = self._make_request(endpoint, params)
        
        if not data or "yearyields" not in data:
            print("  [ERROR] ZCYC data not available (discontinued since 2018)")
            return pd.DataFrame()
        
        cols = data["yearyields"]["columns"]
        rows = data["yearyields"]["data"]
        
        if not rows:
            return pd.DataFrame()
        
        return pd.DataFrame([dict(zip(cols, row)) for row in rows])
    
    # =========================================================================
    # CORPORATE BONDS
    # =========================================================================
    
    def search_corporate_bonds(self, issuer: str = None) -> pd.DataFrame:
        """
        Search for corporate bonds.
        
        Args:
            issuer: Issuer name or part of it (e.g., "Газпром")
        """
        if issuer:
            return self.search_securities(issuer)
        
        # Get all corporate bonds
        endpoint = "engines/stock/markets/bonds/securities.json"
        params = {"iss.meta": "off"}
        
        data = self._make_request(endpoint, params)
        
        if not data or "securities" not in data:
            return pd.DataFrame()
        
        cols = data["securities"]["columns"]
        rows = data["securities"]["data"]
        
        df = pd.DataFrame([dict(zip(cols, row)) for row in rows])
        
        # Filter to corporate bonds (exclude OFZ)
        if "SECTYPE" in df.columns:
            df = df[~df["SECTYPE"].str.contains("ofz", case=False, na=False)]
        
        return df


# Test function
def test_moex_fetcher():
    """Test MOEX fetcher functionality."""
    fetcher = MOEXFetcher()
    
    # Test OFZ search
    print("\nSearching for OFZ bonds...")
    ofz = fetcher.search_securities("ОФЗ")
    print(f"Found {len(ofz)} OFZ bonds")
    
    # Test single bond history
    print("\nFetching single bond history...")
    history = fetcher.fetch_bond_history("SU26238RMFS3", "2024-01-01", "2024-12-31")
    if not history.empty:
        print(f"Got {len(history)} records")
        print(history[["TRADEDATE", "CLOSE", "YIELDCLOSE"]].head())
    
    # Test OFZ yields
    print("\nFetching OFZ yields...")
    yields = fetcher.fetch_ofz_yields("2024-01-01", "2024-12-31")
    if not yields.empty:
        print(yields.head(10))
    
    # Test RGBI
    print("\nFetching RGBI index...")
    rgbi = fetcher.fetch_rgbi_index("2024-01-01", "2024-12-31")
    if not rgbi.empty:
        print(f"RGBI: {len(rgbi)} records")


if __name__ == "__main__":
    test_moex_fetcher()

