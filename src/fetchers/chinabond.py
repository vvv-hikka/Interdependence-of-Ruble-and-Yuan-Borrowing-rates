"""
ChinaBond Loader - Manual data import
=====================================
Source: https://www.chinabond.com.cn/
Data: Chinese government bond yield curves
Automation: Manual (download files, then import)
Cost: Free

HOW TO GET DATA:
1. Go to https://www.chinabond.com.cn/ (or https://yield.chinabond.com.cn/)
2. Navigate to: Yield Curves / 收益率曲线
3. Select "中债国债收益率曲线" (ChinaBond Treasury Yield Curve)
4. Download historical data in Excel/CSV format
5. Save to: src/data_manual/ or data/manual/ (all .xlsx/.csv in the directory are loaded and combined)
6. Run this loader to import into database
"""

import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict


class ChinaBondLoader:
    """Loader for manually downloaded ChinaBond data."""
    
    # Standard maturities (in years)
    STANDARD_MATURITIES = [0.5, 1, 2, 3, 5, 7, 10, 15, 20, 30]
    
    def __init__(self, data_dir: str = None):
        if data_dir:
            self.data_dir = Path(data_dir)
        else:
            self.data_dir = Path(__file__).parent.parent / "data_manual"
        
        self.data_dir.mkdir(parents=True, exist_ok=True)
    
    def load_from_excel(self, filepath: str = None) -> pd.DataFrame:
        """
        Load ChinaBond yield curve data from Excel file.
        
        Args:
            filepath: Path to Excel file. If None, looks for chinabond_yields.xlsx
        
        Returns:
            DataFrame with date and yield columns for each maturity
        """
        if filepath is None:
            filepath = self.data_dir / "chinabond_yields.xlsx"
        
        filepath = Path(filepath)
        
        if not filepath.exists():
            print(f"  [ERROR] File not found: {filepath}")
            print(f"  -> Download ChinaBond yield curve data and save to: {filepath}")
            return pd.DataFrame()
        
        try:
            # Try to read Excel file
            df = pd.read_excel(filepath)
            print(f"  [OK] Loaded {len(df)} rows from {filepath.name}")
            return self._process_chinabond_data(df)
        except Exception as e:
            print(f"  [ERROR] Error reading Excel file: {e}")
            return pd.DataFrame()
    
    def load_from_csv(self, filepath: str = None) -> pd.DataFrame:
        """
        Load ChinaBond yield curve data from CSV file.
        """
        if filepath is None:
            filepath = self.data_dir / "chinabond_yields.csv"
        
        filepath = Path(filepath)
        
        if not filepath.exists():
            print(f"  [ERROR] File not found: {filepath}")
            return pd.DataFrame()
        
        try:
            # Try different encodings
            for encoding in ['utf-8', 'gbk', 'gb2312', 'utf-16']:
                try:
                    df = pd.read_csv(filepath, encoding=encoding)
                    print(f"  [OK] Loaded {len(df)} rows from {filepath.name}")
                    return self._process_chinabond_data(df)
                except UnicodeDecodeError:
                    continue
            
            print(f"  [ERROR] Could not decode file with common encodings")
            return pd.DataFrame()
            
        except Exception as e:
            print(f"  [ERROR] Error reading CSV file: {e}")
            return pd.DataFrame()
    
    def load_from_directory(self) -> pd.DataFrame:
        """
        Load and combine all .xlsx and .csv files in self.data_dir.
        
        Scans the directory for ChinaBond yield files, loads each, processes via
        _process_chinabond_data, and merges on date (outer). For columns that
        appear in multiple files (same maturity), coalesces to first non-null.
        
        Returns:
            Combined DataFrame with date and CN_* columns, or empty if no files found.
        """
        files = list(self.data_dir.glob("*.xlsx")) + list(self.data_dir.glob("*.csv"))
        # Exclude template/placeholder files
        files = [f for f in files if "template" not in f.name.lower() and "placeholder" not in f.name.lower()]
        
        if not files:
            return pd.DataFrame()
        
        all_dfs = []
        for fp in sorted(files):
            if fp.suffix.lower() == ".xlsx":
                df = self.load_from_excel(str(fp))
            else:
                df = self.load_from_csv(str(fp))
            if not df.empty and "date" in df.columns:
                all_dfs.append(df)
        
        if not all_dfs:
            return pd.DataFrame()
        
        if len(all_dfs) == 1:
            return self.resample_to_monthly(all_dfs[0])
        
        # Merge all on date (outer)
        result = all_dfs[0]
        for df in all_dfs[1:]:
            result = result.merge(df, on="date", how="outer", suffixes=("", "_dup"))
            # Coalesce duplicate columns (drop _dup, keep first non-null)
            dup_cols = [c for c in result.columns if c.endswith("_dup")]
            for dup in dup_cols:
                base = dup.replace("_dup", "")
                if base in result.columns:
                    result[base] = result[base].combine_first(result[dup])
                result = result.drop(columns=[dup])
        
        result = result.sort_values("date").reset_index(drop=True)
        result = self.resample_to_monthly(result)
        print(f"  [OK] Combined {len(all_dfs)} files from {self.data_dir} -> {len(result)} rows")
        return result
    
    def _is_long_format(self, df: pd.DataFrame) -> bool:
        """Check if DataFrame is in long format (Date, maturity column, yield column)."""
        if df.empty or len(df.columns) < 3:
            return False
        cols_lower = [str(c).lower() for c in df.columns]
        has_yield = any("yield" in c or "rate" in c or "收益率" in c for c in cols_lower)
        has_terms = any("standard terms" in c or "maturity" in c or "term" in c or "期限" in c for c in cols_lower)
        return bool(has_yield and has_terms)

    def _process_chinabond_long_format(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Process long-format ChinaBond data (Date, Standard Terms(Years), Yield Rate(%))
        into wide format with one column per maturity (CN_3M, CN_6M, CN_1Y, ...).
        """
        # Find date column
        date_col = None
        for col in df.columns:
            if "date" in str(col).lower() or "日期" in str(col):
                date_col = col
                break
        if date_col is None:
            date_col = df.columns[0]
        # Find maturity column (years) — must be numeric maturity (e.g. "Standard Terms(Years)" or "Standard Terms(Yrs)")
        # Avoid "Instructions for Standard Terms" which has "0d", "1m" etc.
        mat_col = None
        for col in df.columns:
            s = str(col).lower()
            if ("yrs" in s or "years" in s or "年" in s) and ("term" in s or "maturity" in s):
                mat_col = col
                break
        if mat_col is None:
            for col in df.columns:
                s = str(col).lower()
                if "term" in s and "instruction" not in s and ("year" in s or "yrs" in s or "maturity" in s):
                    mat_col = col
                    break
        if mat_col is None:
            for col in df.columns:
                s = str(col).lower()
                if "term" in s or "maturity" in s or "期限" in s:
                    mat_col = col
                    break
        # Find yield column
        yield_col = None
        for col in df.columns:
            s = str(col).lower()
            if "yield" in s or "rate" in s or "收益率" in s:
                yield_col = col
                break
        if mat_col is None or yield_col is None:
            return pd.DataFrame()
        df = df.copy()
        df["date"] = pd.to_datetime(df[date_col])
        df["_mat"] = pd.to_numeric(df[mat_col], errors="coerce")
        # If maturity column is string (e.g. "1年", "2年"), try to extract numeric part
        if df["_mat"].isna().all() and df[mat_col].dtype == object:
            def parse_mat(x):
                try:
                    s = str(x).strip()
                    for sep in ["年", "Y", "y", "Yrs", "yr"]:
                        if sep in s:
                            return pd.to_numeric(s.split(sep)[0].strip(), errors="coerce")
                    return pd.to_numeric(s, errors="coerce")
                except Exception:
                    return float("nan")
            df["_mat"] = df[mat_col].apply(parse_mat)
        df["_yield"] = pd.to_numeric(df[yield_col], errors="coerce")
        df = df.dropna(subset=["date", "_mat", "_yield"])
        # Map maturity (years) to CN_* column names
        # 0.25->3M, 0.5->6M, 0.75->9M, 1->1Y, 2->2Y, 3->3Y, 5->5Y, 7->7Y, 10->10Y, 15->15Y, 20->20Y, 30->30Y
        year_to_col = {
            0.25: "CN_3M", 0.5: "CN_6M", 0.75: "CN_9M",
            1.0: "CN_1Y", 2.0: "CN_2Y", 3.0: "CN_3Y", 5.0: "CN_5Y", 7.0: "CN_7Y",
            10.0: "CN_10Y", 15.0: "CN_15Y", 20.0: "CN_20Y", 30.0: "CN_30Y",
        }
        # Round to avoid float key issues
        def mat_to_col(y):
            y = round(float(y), 2)
            return year_to_col.get(y)
        df["_col"] = df["_mat"].apply(mat_to_col)
        df = df.dropna(subset=["_col"])
        wide = df.pivot_table(index="date", columns="_col", values="_yield", aggfunc="first").reset_index()
        wide.columns.name = None
        wide = wide.sort_values("date").reset_index(drop=True)
        print(f"  Processed long format -> columns: {list(wide.columns)}")
        return wide

    def _process_chinabond_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Process raw ChinaBond data into standard format.
        Supports both long format (Date, Standard Terms(Years), Yield Rate(%)) and wide format.
        """
        if df.empty:
            return df

        if self._is_long_format(df):
            return self._process_chinabond_long_format(df)

        # Try to identify date column
        date_col = None
        for col in df.columns:
            col_lower = str(col).lower()
            if '日期' in col_lower or 'date' in col_lower or '时间' in col_lower:
                date_col = col
                break
        
        if date_col is None:
            # Assume first column is date
            date_col = df.columns[0]
        
        # Convert date column
        try:
            df['date'] = pd.to_datetime(df[date_col])
        except Exception:
            print(f"  [ERROR] Could not parse date column: {date_col}")
            return pd.DataFrame()
        
        # Identify yield columns (look for numeric columns with maturity indicators)
        result_cols = {'date': df['date']}
        
        for col in df.columns:
            if col == date_col or col == 'date':
                continue
            
            col_str = str(col)
            
            # Try to extract maturity from column name
            maturity = None
            
            # Check for common patterns
            for mat in self.STANDARD_MATURITIES:
                if f"{int(mat)}年" in col_str or f"{mat}Y" in col_str.upper():
                    maturity = mat
                    break
                elif f"{mat}年" in col_str:
                    maturity = mat
                    break
            
            if maturity is not None:
                # Convert to numeric
                values = pd.to_numeric(df[col], errors='coerce')
                if values.notna().sum() > 0:
                    result_cols[f'CN_{int(maturity)}Y'] = values
        
        result = pd.DataFrame(result_cols)
        result = result.sort_values('date')
        
        print(f"  Processed columns: {list(result.columns)}")
        return result
    
    def create_sample_template(self) -> pd.DataFrame:
        """
        Create a sample template showing expected data format.
        """
        dates = pd.date_range('2024-01-01', periods=12, freq='ME')
        
        template = pd.DataFrame({
            'date': dates,
            'CN_1Y': [2.1 + i*0.05 for i in range(12)],
            'CN_2Y': [2.2 + i*0.05 for i in range(12)],
            'CN_3Y': [2.3 + i*0.05 for i in range(12)],
            'CN_5Y': [2.5 + i*0.05 for i in range(12)],
            'CN_7Y': [2.7 + i*0.05 for i in range(12)],
            'CN_10Y': [2.9 + i*0.05 for i in range(12)],
        })
        
        # Save template
        template_path = self.data_dir / "chinabond_template.xlsx"
        template.to_excel(template_path, index=False)
        print(f"  [OK] Created template: {template_path}")
        
        return template
    
    def create_placeholder_data(self, start_date: str = '2015-01-01',
                                 end_date: str = None) -> pd.DataFrame:
        """
        Create placeholder DataFrame with expected structure.
        Fill with NaN values - user should replace with actual data.
        """
        if end_date is None:
            end_date = datetime.now().strftime('%Y-%m-%d')
        
        dates = pd.date_range(start_date, end_date, freq='ME')
        
        placeholder = pd.DataFrame({
            'date': dates,
            'CN_1Y': [None] * len(dates),
            'CN_2Y': [None] * len(dates),
            'CN_3Y': [None] * len(dates),
            'CN_5Y': [None] * len(dates),
            'CN_7Y': [None] * len(dates),
            'CN_10Y': [None] * len(dates),
            'CN_15Y': [None] * len(dates),
            'CN_20Y': [None] * len(dates),
            'CN_30Y': [None] * len(dates),
        })
        
        return placeholder
    
    def resample_to_monthly(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Resample daily data to monthly (last value of each month).
        """
        if df.empty or 'date' not in df.columns:
            return df
        
        df = df.set_index('date')
        numeric_cols = df.select_dtypes(include=['number']).columns
        monthly = df[numeric_cols].resample('ME').last().reset_index()
        
        return monthly


# PBOC LPR Data (historical, can be updated manually)
PBOC_LPR_DATA = """date,pboc_lpr_1y,pboc_lpr_5y
2019-08-20,4.25,4.85
2019-09-20,4.20,4.85
2019-10-21,4.20,4.85
2019-11-20,4.15,4.80
2019-12-20,4.15,4.80
2020-01-20,4.15,4.80
2020-02-20,4.05,4.75
2020-03-20,4.05,4.75
2020-04-20,3.85,4.65
2020-05-20,3.85,4.65
2020-06-22,3.85,4.65
2020-07-20,3.85,4.65
2020-08-20,3.85,4.65
2020-09-21,3.85,4.65
2020-10-20,3.85,4.65
2020-11-20,3.85,4.65
2020-12-21,3.85,4.65
2021-01-20,3.85,4.65
2021-02-20,3.85,4.65
2021-03-22,3.85,4.65
2021-04-20,3.85,4.65
2021-05-20,3.85,4.65
2021-06-21,3.85,4.65
2021-07-20,3.85,4.65
2021-08-20,3.85,4.65
2021-09-22,3.85,4.65
2021-10-20,3.85,4.65
2021-11-22,3.85,4.65
2021-12-20,3.80,4.65
2022-01-20,3.70,4.60
2022-02-21,3.70,4.60
2022-03-21,3.70,4.60
2022-04-20,3.70,4.60
2022-05-20,3.70,4.45
2022-06-20,3.70,4.45
2022-07-20,3.70,4.45
2022-08-22,3.65,4.30
2022-09-20,3.65,4.30
2022-10-20,3.65,4.30
2022-11-21,3.65,4.30
2022-12-20,3.65,4.30
2023-01-20,3.65,4.30
2023-02-20,3.65,4.30
2023-03-20,3.65,4.30
2023-04-20,3.65,4.30
2023-05-22,3.65,4.30
2023-06-20,3.55,4.20
2023-07-20,3.55,4.20
2023-08-21,3.45,4.20
2023-09-20,3.45,4.20
2023-10-20,3.45,4.20
2023-11-20,3.45,4.20
2023-12-20,3.45,4.20
2024-01-22,3.45,4.20
2024-02-20,3.45,4.20
2024-03-20,3.45,3.95
2024-04-22,3.45,3.95
2024-05-20,3.45,3.95
2024-06-20,3.45,3.95
2024-07-22,3.35,3.85
2024-08-20,3.35,3.85
2024-09-20,3.35,3.85
2024-10-21,3.10,3.60
2024-11-20,3.10,3.60
2024-12-20,3.10,3.60
2025-01-20,3.10,3.60
"""


def load_pboc_lpr() -> pd.DataFrame:
    """Load PBOC LPR data from embedded dataset."""
    from io import StringIO
    
    df = pd.read_csv(StringIO(PBOC_LPR_DATA.strip()), parse_dates=['date'])
    df = df.sort_values('date')
    
    # Resample to monthly (forward fill)
    df = df.set_index('date')
    monthly = df.resample('ME').last().ffill().reset_index()
    
    return monthly


def test_chinabond_loader():
    """Test ChinaBond loader functionality."""
    loader = ChinaBondLoader()
    
    # Create template
    template = loader.create_sample_template()
    print(f"Template:\n{template.head()}")
    
    # Create placeholder
    placeholder = loader.create_placeholder_data()
    print(f"\nPlaceholder shape: {placeholder.shape}")
    
    # Load PBOC LPR
    lpr = load_pboc_lpr()
    print(f"\nPBOC LPR:\n{lpr.tail()}")


if __name__ == "__main__":
    test_chinabond_loader()

