"""
Statistical Analysis Module
===========================
Provides statistical analysis of Ruble-Yuan borrowing rate interdependence.

Features:
- Descriptive statistics
- Correlation analysis
- Regression analysis
- Time series analysis (stationarity, cointegration, Granger causality)
"""

import pandas as pd
import numpy as np
from typing import Optional, Dict, List, Any, Tuple
from pathlib import Path
from datetime import datetime

try:
    from src.database import DatabaseManager
except ImportError:
    DatabaseManager = None

try:
    from config import ANALYSIS_VARIABLE_PREFIXES, FRED_TABLE_PREFIXES
except ImportError:
    ANALYSIS_VARIABLE_PREFIXES = [
        'cbr_key_rate', 'cbr_gcurve', 'currency_rates', 'russian_bond_yields',
        'russian_macro', 'pboc_lpr', 'chinese_bond_yields', 'chinese_macro',
        'global_indicators', 'business_activity',
    ]
    FRED_TABLE_PREFIXES = ['russian_macro', 'chinese_macro', 'global_indicators', 'business_activity']

# Statistical libraries
try:
    import statsmodels.api as sm
    from statsmodels.tsa.stattools import adfuller, kpss, coint, grangercausalitytests
    from statsmodels.tsa.vector_ar.var_model import VAR
    STATSMODELS_AVAILABLE = True
except ImportError:
    STATSMODELS_AVAILABLE = False
    print("Warning: statsmodels not available. Some advanced features will be disabled.")

try:
    from scipy import stats
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
    print("Warning: scipy not available. Some statistical tests will be disabled.")


class StatisticalAnalyzer:
    """Statistical analysis of Ruble-Yuan borrowing rate interdependence."""
    
    def __init__(self, db_path: str = None):
        """
        Initialize statistical analyzer.
        
        Args:
            db_path: Path to database file (optional, uses default if not provided)
        """
        if DatabaseManager is None:
            raise ImportError("DatabaseManager not available. Install database package.")
        
        self.db = DatabaseManager(db_path) if db_path else DatabaseManager()
        self.data: Optional[pd.DataFrame] = None
    
    def load_data(self, start_date: str = None, end_date: str = None) -> pd.DataFrame:
        """
        Load combined monthly data from database.
        
        Args:
            start_date: Start date (YYYY-MM-DD format). Use to restrict analysis to a common period.
            end_date: End date (YYYY-MM-DD format). Use to restrict analysis to a common period.
        
        Returns:
            DataFrame with combined monthly data
        
        Note:
            Some series have limited history (e.g. Chinese bond yields may have only 12+ months).
            Restrict start_date/end_date to avoid short series dominating or to align samples.
        """
        # Load combined monthly view
        self.data = self.db.load_dataframe('combined_monthly')
        
        if self.data.empty:
            print("Warning: No data found in combined_monthly table")
            return self.data
        
        # Filter by date if provided
        if 'date' in self.data.columns:
            self.data['date'] = pd.to_datetime(self.data['date'])
            
            if start_date:
                start = pd.to_datetime(start_date)
                self.data = self.data[self.data['date'] >= start]
            
            if end_date:
                end = pd.to_datetime(end_date)
                self.data = self.data[self.data['date'] <= end]
            
            # Sort by date
            self.data = self.data.sort_values('date').reset_index(drop=True)
        
        print(f"Loaded {len(self.data)} rows of data")
        return self.data
    
    def load_yield_curves(self, currency: str, start_date: str = None,
                          end_date: str = None) -> pd.DataFrame:
        """
        Load yield curve data for RU or CN from database.
        
        Args:
            currency: 'RU' or 'CN'
            start_date: Start date (YYYY-MM-DD), optional
            end_date: End date (YYYY-MM-DD), optional
        
        Returns:
            DataFrame with date index and columns per maturity (e.g. RU_1Y, RU_2Y or CN_1Y, CN_5Y).
            Empty DataFrame if no data.
        """
        if currency.upper() == 'RU':
            gcurve = self.db.load_dataframe('cbr_gcurve')
            ofz = self.db.load_dataframe('russian_bond_yields')
            if gcurve.empty and ofz.empty:
                return pd.DataFrame()
            
            # Merge on date, coalesce overlapping columns (3Y, 5Y, 10Y may appear in both)
            if gcurve.empty:
                result = ofz.copy()
            elif ofz.empty:
                result = gcurve.copy()
            else:
                result = gcurve.merge(ofz, on='date', how='outer', suffixes=('', '_dup'))
                dup_cols = [c for c in result.columns if c.endswith('_dup')]
                for dup in dup_cols:
                    base = dup.replace('_dup', '')
                    if base in result.columns:
                        result[base] = result[base].combine_first(result[dup])
                    result = result.drop(columns=[dup])
            
            yield_cols = [c for c in result.columns if c.startswith('RU_') and c != 'date']
        elif currency.upper() == 'CN':
            result = self.db.load_dataframe('chinese_bond_yields')
            if result.empty:
                return pd.DataFrame()
            yield_cols = [c for c in result.columns if c.startswith('CN_') and c != 'date']
        else:
            return pd.DataFrame()
        
        result = result.sort_values('date')
        
        if start_date:
            start = pd.to_datetime(start_date)
            result = result[result['date'] >= start]
        if end_date:
            end = pd.to_datetime(end_date)
            result = result[result['date'] <= end]
        
        result = result.set_index('date')
        # Keep only yield columns
        keep = [c for c in result.columns if c in yield_cols]
        return result[keep].copy()
    
    def get_fred_columns(self) -> List[str]:
        """
        Return numeric columns in self.data that start with a FRED table prefix.
        Use for explicitly restricting analysis to FRED-sourced series.
        """
        if self.data is None or self.data.empty:
            return []
        numeric_cols = self.data.select_dtypes(include=[np.number]).columns.tolist()
        return [c for c in numeric_cols if any(c.startswith(p) for p in FRED_TABLE_PREFIXES)]
    
    def yield_curve_descriptive_stats(self, currency: str) -> pd.DataFrame:
        """
        Return descriptive stats for each maturity series (mean, std, min, max, count).
        """
        df = self.load_yield_curves(currency)
        if df.empty:
            return pd.DataFrame()
        return df.describe().T[['mean', 'std', 'min', 'max', 'count']]
    
    def _get_analysis_columns(self, variables: List[str] = None) -> List[str]:
        """Return numeric columns for analysis; when variables is None use canonical prefixes (combined view naming)."""
        if self.data is None or self.data.empty:
            return []
        numeric_cols = self.data.select_dtypes(include=[np.number]).columns.tolist()
        if variables:
            numeric_cols = [c for c in numeric_cols if any(v in c for v in variables)]
        else:
            # Prefer columns from base tables (combined view: table_col)
            preferred = [c for c in numeric_cols if any(c.startswith(p) for p in ANALYSIS_VARIABLE_PREFIXES)]
            numeric_cols = preferred if preferred else numeric_cols
        return numeric_cols
    
    def descriptive_stats(self, variables: List[str] = None) -> pd.DataFrame:
        """
        Calculate descriptive statistics for specified variables.
        
        Args:
            variables: List of variable names to analyze. If None, analyzes all numeric columns.
        
        Returns:
            DataFrame with descriptive statistics
        """
        if self.data is None or self.data.empty:
            self.load_data()
        
        if self.data.empty:
            return pd.DataFrame()
        
        numeric_cols = self._get_analysis_columns(variables)
        if not numeric_cols:
            print("No numeric variables found")
            return pd.DataFrame()
        
        # Calculate descriptive statistics
        stats_df = self.data[numeric_cols].describe()
        
        # Add additional statistics
        additional_stats = pd.DataFrame({
            col: {
                'skewness': self.data[col].skew(),
                'kurtosis': self.data[col].kurtosis(),
                'missing': self.data[col].isna().sum(),
                'missing_pct': (self.data[col].isna().sum() / len(self.data)) * 100
            }
            for col in numeric_cols
        }).T
        
        # Combine
        result = pd.concat([stats_df.T, additional_stats], axis=1)
        
        return result
    
    def correlation_matrix(self, variables: List[str] = None) -> pd.DataFrame:
        """
        Calculate correlation matrix.
        
        Args:
            variables: List of variable names. If None, uses all numeric columns.
        
        Returns:
            Correlation matrix DataFrame
        """
        if self.data is None or self.data.empty:
            self.load_data()
        
        if self.data.empty:
            return pd.DataFrame()
        
        numeric_cols = self._get_analysis_columns(variables)
        if len(numeric_cols) < 2:
            print("Need at least 2 variables for correlation")
            return pd.DataFrame()
        
        # Drop rows where any selected variable is NaN (common sample for correlation)
        sample = self.data[numeric_cols].dropna()
        if len(sample) < 3:
            print("Not enough non-missing observations for correlation")
            return pd.DataFrame()
        corr_matrix = sample.corr()
        return corr_matrix
    
    def cross_correlation(self, var1: str, var2: str, max_lags: int = 12) -> pd.DataFrame:
        """
        Calculate cross-correlation with lags.
        
        Args:
            var1: First variable name
            var2: Second variable name
            max_lags: Maximum number of lags to consider
        
        Returns:
            DataFrame with correlation at each lag
        """
        if self.data is None or self.data.empty:
            self.load_data()
        
        if self.data.empty:
            return pd.DataFrame()
        
        # Find columns matching variable names
        cols1 = [col for col in self.data.columns if var1 in col]
        cols2 = [col for col in self.data.columns if var2 in col]
        
        if not cols1 or not cols2:
            print(f"Variables {var1} or {var2} not found")
            return pd.DataFrame()
        
        # Use first matching column
        col1 = cols1[0]
        col2 = cols2[0]
        
        # Get data
        data1 = self.data[col1].dropna()
        data2 = self.data[col2].dropna()
        
        # Align by date
        if 'date' in self.data.columns:
            aligned = pd.DataFrame({
                col1: data1,
                col2: data2
            }).dropna()
        else:
            aligned = pd.DataFrame({
                col1: data1,
                col2: data2
            }).dropna()
        
        if len(aligned) < max_lags * 2:
            print("Not enough data for cross-correlation")
            return pd.DataFrame()
        
        # Calculate cross-correlations
        results = []
        for lag in range(-max_lags, max_lags + 1):
            if lag == 0:
                corr = aligned[col1].corr(aligned[col2])
            elif lag > 0:
                # var2 leads var1
                shifted = aligned[col2].shift(-lag)
                corr = aligned[col1].corr(shifted)
            else:
                # var1 leads var2
                shifted = aligned[col1].shift(lag)
                corr = shifted.corr(aligned[col2])
            
            results.append({
                'lag': lag,
                'correlation': corr,
                'interpretation': f"{var2} leads {var1} by {abs(lag)} periods" if lag > 0 
                                 else f"{var1} leads {var2} by {abs(lag)} periods" if lag < 0
                                 else "No lag"
            })
        
        return pd.DataFrame(results)
    
    def simple_regression(self, y_var: str, x_var: str) -> Dict:
        """
        Simple linear regression analysis.
        
        Args:
            y_var: Dependent variable name
            x_var: Independent variable name
        
        Returns:
            Dictionary with regression results
        """
        if self.data is None or self.data.empty:
            self.load_data()
        
        if self.data.empty:
            return {}
        
        # Find columns
        y_cols = [col for col in self.data.columns if y_var in col]
        x_cols = [col for col in self.data.columns if x_var in col]
        
        if not y_cols or not x_cols:
            return {'error': f"Variables {y_var} or {x_var} not found"}
        
        y_col = y_cols[0]
        x_col = x_cols[0]
        
        # Prepare data
        data = self.data[[y_col, x_col]].dropna()
        
        if len(data) < 10:
            return {'error': 'Not enough data for regression'}
        
        X = data[x_col].values
        y = data[y_col].values
        
        # Add constant
        X = sm.add_constant(X)
        
        # Fit model
        model = sm.OLS(y, X).fit()
        
        # Extract results
        results = {
            'dependent_var': y_var,
            'independent_var': x_var,
            'n_observations': len(data),
            'r_squared': model.rsquared,
            'adj_r_squared': model.rsquared_adj,
            'f_statistic': model.fvalue,
            'f_pvalue': model.f_pvalue,
            'coefficients': {
                'intercept': model.params[0],
                'slope': model.params[1]
            },
            'pvalues': {
                'intercept': model.pvalues[0],
                'slope': model.pvalues[1]
            },
            'summary': str(model.summary())
        }
        
        return results
    
    def multiple_regression(self, y_var: str, x_vars: List[str]) -> Dict:
        """
        Multiple regression analysis.
        
        Args:
            y_var: Dependent variable name
            x_vars: List of independent variable names
        
        Returns:
            Dictionary with regression results
        """
        if self.data is None or self.data.empty:
            self.load_data()
        
        if self.data.empty:
            return {}
        
        # Find columns
        y_cols = [col for col in self.data.columns if y_var in col]
        if not y_cols:
            return {'error': f"Dependent variable {y_var} not found"}
        
        y_col = y_cols[0]
        
        # Find independent variable columns
        x_cols = []
        for x_var in x_vars:
            matches = [col for col in self.data.columns if x_var in col]
            if matches:
                x_cols.append(matches[0])
        
        if not x_cols:
            return {'error': 'No independent variables found'}
        
        # Prepare data
        all_cols = [y_col] + x_cols
        data = self.data[all_cols].dropna()
        
        if len(data) < len(x_cols) + 5:
            return {'error': 'Not enough data for regression'}
        
        X = data[x_cols].values
        y = data[y_col].values
        
        # Add constant
        X = sm.add_constant(X)
        
        # Fit model
        model = sm.OLS(y, X).fit()
        
        # Extract results
        results = {
            'dependent_var': y_var,
            'independent_vars': x_vars,
            'n_observations': len(data),
            'r_squared': model.rsquared,
            'adj_r_squared': model.rsquared_adj,
            'f_statistic': model.fvalue,
            'f_pvalue': model.f_pvalue,
            'coefficients': dict(zip(['intercept'] + x_vars, model.params)),
            'pvalues': dict(zip(['intercept'] + x_vars, model.pvalues)),
            'summary': str(model.summary())
        }
        
        return results
    
    def cointegration_test(self, var1: str, var2: str) -> Dict:
        """
        Test for cointegration between two series.
        
        Args:
            var1: First variable name
            var2: Second variable name
        
        Returns:
            Dictionary with cointegration test results
        """
        if not STATSMODELS_AVAILABLE:
            return {'error': 'statsmodels not available'}
        
        if self.data is None or self.data.empty:
            self.load_data()
        
        if self.data.empty:
            return {}
        
        # Find columns
        cols1 = [col for col in self.data.columns if var1 in col]
        cols2 = [col for col in self.data.columns if var2 in col]
        
        if not cols1 or not cols2:
            return {'error': f"Variables {var1} or {var2} not found"}
        
        col1 = cols1[0]
        col2 = cols2[0]
        
        # Prepare data
        data = self.data[[col1, col2]].dropna()
        
        if len(data) < 20:
            return {'error': 'Not enough data for cointegration test'}
        
        # Perform cointegration test
        score, pvalue, _ = coint(data[col1], data[col2])
        
        results = {
            'var1': var1,
            'var2': var2,
            'test_statistic': score,
            'pvalue': pvalue,
            'is_cointegrated': pvalue < 0.05,
            'interpretation': 'Series are cointegrated' if pvalue < 0.05 else 'Series are not cointegrated'
        }
        
        return results
    
    def granger_causality(self, var1: str, var2: str, max_lag: int = 4) -> Dict:
        """
        Granger causality test.
        
        Args:
            var1: First variable name
            var2: Second variable name
            max_lag: Maximum lag to test
        
        Returns:
            Dictionary with Granger causality test results
        """
        if not STATSMODELS_AVAILABLE:
            return {'error': 'statsmodels not available'}
        
        if self.data is None or self.data.empty:
            self.load_data()
        
        if self.data.empty:
            return {}
        
        # Find columns
        cols1 = [col for col in self.data.columns if var1 in col]
        cols2 = [col for col in self.data.columns if var2 in col]
        
        if not cols1 or not cols2:
            return {'error': f"Variables {var1} or {var2} not found"}
        
        col1 = cols1[0]
        col2 = cols2[0]
        
        # Prepare data
        data = self.data[[col1, col2]].dropna()
        
        if len(data) < max_lag * 3:
            return {'error': 'Not enough data for Granger causality test'}
        
        try:
            # Perform Granger causality test
            test_result = grangercausalitytests(data[[col1, col2]], max_lag, verbose=False)
            
            # Extract p-values for each lag
            pvalues = {}
            for lag in range(1, max_lag + 1):
                if lag in test_result:
                    pvalue = test_result[lag][0]['ssr_ftest'][1]
                    pvalues[f'lag_{lag}'] = pvalue
            
            # Find best lag (lowest p-value)
            best_lag = min(pvalues.items(), key=lambda x: x[1]) if pvalues else None
            
            results = {
                'var1': var1,
                'var2': var2,
                'test_direction': f"{var2} Granger-causes {var1}",
                'pvalues_by_lag': pvalues,
                'best_lag': best_lag[0] if best_lag else None,
                'best_pvalue': best_lag[1] if best_lag else None,
                'is_significant': best_lag[1] < 0.05 if best_lag else False,
                'interpretation': f"{var2} Granger-causes {var1} at lag {best_lag[0]}" if best_lag and best_lag[1] < 0.05 
                                 else f"{var2} does not Granger-cause {var1}"
            }
            
            return results
            
        except Exception as e:
            return {'error': f'Granger causality test failed: {str(e)}'}
    
    def generate_report(self, output_path: str = None) -> str:
        """
        Generate comprehensive statistical analysis report.
        
        Args:
            output_path: Path to save report (optional)
        
        Returns:
            Report as string
        """
        if self.data is None or self.data.empty:
            self.load_data()
        
        if self.data.empty:
            return "No data available for analysis"
        
        report_lines = []
        report_lines.append("=" * 80)
        report_lines.append("STATISTICAL ANALYSIS REPORT")
        report_lines.append("Ruble-Yuan Borrowing Rate Interdependence")
        report_lines.append("=" * 80)
        report_lines.append(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report_lines.append(f"Data period: {self.data['date'].min()} to {self.data['date'].max()}")
        report_lines.append(f"Number of observations: {len(self.data)}")
        
        # Descriptive statistics
        report_lines.append("\n" + "=" * 80)
        report_lines.append("DESCRIPTIVE STATISTICS")
        report_lines.append("=" * 80)
        desc_stats = self.descriptive_stats()
        if not desc_stats.empty:
            report_lines.append("\n" + desc_stats.to_string())
        
        # FRED-sourced indicators section
        fred_cols = self.get_fred_columns()
        if fred_cols:
            report_lines.append("\n" + "=" * 80)
            report_lines.append("FRED-SOURCED INDICATORS")
            report_lines.append("=" * 80)
            report_lines.append(f"\nFRED columns in data: {fred_cols}")
            fred_stats = self.descriptive_stats(variables=fred_cols[:5])
            if not fred_stats.empty:
                report_lines.append("\nDescriptive stats (sample):")
                report_lines.append(fred_stats.to_string())
        
        # Yield curve statistics
        for curr in ['RU', 'CN']:
            yc_stats = self.yield_curve_descriptive_stats(curr)
            if not yc_stats.empty:
                report_lines.append(f"\n" + "=" * 80)
                report_lines.append(f"YIELD CURVE STATISTICS ({curr})")
                report_lines.append("=" * 80)
                report_lines.append("\n" + yc_stats.to_string())
        
        # Correlation matrix (sample of key variables)
        report_lines.append("\n" + "=" * 80)
        report_lines.append("CORRELATION ANALYSIS")
        report_lines.append("=" * 80)
        
        # Use canonical analysis columns (combined view naming)
        corr_vars = self._get_analysis_columns(None)
        if corr_vars:
            corr_matrix = self.correlation_matrix(corr_vars[:10])  # Limit to 10 vars
            if not corr_matrix.empty:
                report_lines.append("\nCorrelation Matrix (key variables):")
                report_lines.append(corr_matrix.to_string())
        
        report_lines.append("\n" + "=" * 80)
        report_lines.append("END OF REPORT")
        report_lines.append("=" * 80)
        
        report = "\n".join(report_lines)
        
        # Save if path provided
        if output_path:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(report)
            print(f"Report saved to {output_path}")
        
        return report

