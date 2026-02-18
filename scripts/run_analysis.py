"""
Example script for running statistical analysis
===============================================

Uses combined_monthly (canonical column names from base tables). For more comparable
series, restrict the window, e.g. --start-date 2019-01-01 --end-date 2025-12-31.

Usage:
    python scripts/run_analysis.py                    # Run full analysis
    python scripts/run_analysis.py --report report.txt  # Save report to file
    python scripts/run_analysis.py --start-date 2019-01-01 --end-date 2025-12-31
"""

import argparse

from src.analysis.statistics import StatisticalAnalyzer


def main():
    parser = argparse.ArgumentParser(description='Run statistical analysis')
    parser.add_argument('--start-date', type=str, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str, help='End date (YYYY-MM-DD)')
    parser.add_argument('--report', type=str, help='Save report to file')
    
    args = parser.parse_args()
    
    # Initialize analyzer
    analyzer = StatisticalAnalyzer()
    
    # Load data
    print("Loading data...")
    analyzer.load_data(args.start_date, args.end_date)
    
    if analyzer.data.empty:
        print("No data available. Run data pipeline first.")
        return
    
    # Run descriptive statistics
    print("\n" + "="*60)
    print("DESCRIPTIVE STATISTICS")
    print("="*60)
    desc_stats = analyzer.descriptive_stats()
    if not desc_stats.empty:
        print(desc_stats.head(20))
    
    # Run correlation analysis
    print("\n" + "="*60)
    print("CORRELATION ANALYSIS")
    print("="*60)
    corr_matrix = analyzer.correlation_matrix()
    if not corr_matrix.empty:
        print(corr_matrix.head(10))
    
    # Example: Cross-correlation between Ruble and Yuan rates
    print("\n" + "="*60)
    print("CROSS-CORRELATION: Ruble vs Yuan Rates")
    print("="*60)
    try:
        cross_corr = analyzer.cross_correlation('RU_', 'LPR', max_lags=6)
        if not cross_corr.empty:
            print(cross_corr)
    except Exception as e:
        print(f"Cross-correlation analysis failed: {e}")
    
    # Example: Simple regression
    print("\n" + "="*60)
    print("REGRESSION ANALYSIS")
    print("="*60)
    try:
        reg_result = analyzer.simple_regression('LPR', 'cbr_key_rate')
        if 'error' not in reg_result:
            print(f"Dependent: {reg_result['dependent_var']}")
            print(f"Independent: {reg_result['independent_var']}")
            print(f"R-squared: {reg_result['r_squared']:.4f}")
            print(f"Coefficient: {reg_result['coefficients']['slope']:.4f}")
            print(f"P-value: {reg_result['pvalues']['slope']:.4f}")
    except Exception as e:
        print(f"Regression analysis failed: {e}")
    
    # Generate full report
    if args.report:
        print(f"\nGenerating report and saving to {args.report}...")
        report = analyzer.generate_report(args.report)
    else:
        print("\nGenerating report...")
        report = analyzer.generate_report()
        print(report)


if __name__ == "__main__":
    main()

