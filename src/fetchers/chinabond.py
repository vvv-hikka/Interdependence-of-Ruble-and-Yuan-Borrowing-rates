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
5. Save to: data/manual/chinabond_yields.xlsx
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
    
    def _process_chinabond_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Process raw ChinaBond data into standard format.
        """
        if df.empty:
            return df
        
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

