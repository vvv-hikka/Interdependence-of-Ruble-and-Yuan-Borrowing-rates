"""
Database module for storing and managing financial data
========================================================
"""

import sqlite3
import pandas as pd
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Any

try:
    from config import DB_PATH, DB_TABLES, BASE_TABLES_FOR_COMBINED_VIEW
except ImportError:
    DB_PATH = Path(__file__).parent.parent.parent / "bond_rates_database.db"
    DB_TABLES = {}
    BASE_TABLES_FOR_COMBINED_VIEW = [
        'cbr_key_rate', 'cbr_gcurve', 'currency_rates', 'russian_bond_yields',
        'russian_macro', 'pboc_lpr', 'chinese_bond_yields', 'chinese_macro',
        'global_indicators', 'business_activity',
    ]


class DatabaseManager:
    """Manager for SQLite database operations."""
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or str(DB_PATH)
        self._init_db()
    
    def _init_db(self):
        """Initialize database with required tables."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Create metadata table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS _metadata (
                table_name TEXT PRIMARY KEY,
                description TEXT,
                source TEXT,
                frequency TEXT,
                last_updated TEXT
            )
        """)
        
        # Create data update log
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS _update_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                table_name TEXT,
                rows_added INTEGER,
                update_time TEXT
            )
        """)
        
        conn.commit()
        conn.close()
    
    def get_connection(self) -> sqlite3.Connection:
        """Get database connection."""
        return sqlite3.connect(self.db_path)
    
    # =========================================================================
    # TABLE OPERATIONS
    # =========================================================================
    
    def save_dataframe(self, df: pd.DataFrame, table_name: str,
                       description: str = "", source: str = "",
                       frequency: str = "monthly",
                       if_exists: str = "replace") -> bool:
        """
        Save DataFrame to database table.
        
        Args:
            df: DataFrame to save
            table_name: Name of the table
            description: Table description
            source: Data source
            frequency: Data frequency
            if_exists: What to do if table exists ('replace', 'append', 'fail')
        
        Returns:
            True if successful
        """
        if df is None or df.empty:
            print(f"  [ERROR] No data to save for {table_name}")
            return False
        
        try:
            conn = self.get_connection()
            
            # Save DataFrame
            df.to_sql(table_name, conn, if_exists=if_exists, index=False)
            
            # Update metadata
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO _metadata 
                (table_name, description, source, frequency, last_updated)
                VALUES (?, ?, ?, ?, ?)
            """, (table_name, description, source, frequency, datetime.now().isoformat()))
            
            # Log update
            cursor.execute("""
                INSERT INTO _update_log (table_name, rows_added, update_time)
                VALUES (?, ?, ?)
            """, (table_name, len(df), datetime.now().isoformat()))
            
            conn.commit()
            conn.close()
            
            print(f"  [OK] Saved {len(df)} rows to '{table_name}'")
            return True
            
        except Exception as e:
            print(f"  [ERROR] Error saving to {table_name}: {e}")
            return False
    
    def load_dataframe(self, table_name: str) -> pd.DataFrame:
        """Load DataFrame from database table."""
        try:
            conn = self.get_connection()
            df = pd.read_sql(f"SELECT * FROM {table_name}", conn)
            conn.close()
            
            # Convert date column if present
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'])
            
            return df
        except Exception as e:
            print(f"  [ERROR] Error loading {table_name}: {e}")
            return pd.DataFrame()
    
    def query(self, sql: str) -> pd.DataFrame:
        """Execute SQL query and return DataFrame."""
        try:
            conn = self.get_connection()
            df = pd.read_sql(sql, conn)
            conn.close()
            return df
        except Exception as e:
            print(f"  [ERROR] Query error: {e}")
            return pd.DataFrame()
    
    def list_tables(self) -> List[str]:
        """List all tables in database."""
        df = self.query("SELECT name FROM sqlite_master WHERE type='table'")
        return df['name'].tolist() if not df.empty else []
    
    def get_metadata(self) -> pd.DataFrame:
        """Get metadata for all tables."""
        return self.query("SELECT * FROM _metadata")
    
    def get_update_log(self, limit: int = 20) -> pd.DataFrame:
        """Get recent update log."""
        return self.query(f"SELECT * FROM _update_log ORDER BY update_time DESC LIMIT {limit}")
    
    def drop_table(self, table_name: str) -> bool:
        """Drop a table from database."""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute(f"DROP TABLE IF EXISTS {table_name}")
            cursor.execute("DELETE FROM _metadata WHERE table_name = ?", (table_name,))
            conn.commit()
            conn.close()
            print(f"  [OK] Dropped table '{table_name}'")
            return True
        except Exception as e:
            print(f"  [ERROR] Error dropping {table_name}: {e}")
            return False
    
    # =========================================================================
    # COMBINED DATA VIEWS
    # =========================================================================
    
    def create_combined_monthly_view(self) -> pd.DataFrame:
        """
        Create a combined view of all monthly data from base tables only.
        Drops existing combined_monthly so each run produces a clean view.
        """
        print("\nCreating combined monthly view...")
        
        # Drop existing combined view so we rebuild from base tables only
        self.drop_table('combined_monthly')
        
        # Use only base tables (exclude derived/view tables like combined_monthly)
        all_tables = self.list_tables()
        tables = [t for t in all_tables if t in BASE_TABLES_FOR_COMBINED_VIEW and not t.startswith('_')]
        
        # Start with date range
        combined = None
        
        for table in tables:
            df = self.load_dataframe(table)
            if df.empty or 'date' not in df.columns:
                continue
            
            # Rename columns to avoid conflicts (prefix with table name)
            cols_to_rename = {col: f"{table}_{col}" for col in df.columns if col != 'date'}
            df = df.rename(columns=cols_to_rename)
            
            if combined is None:
                combined = df
            else:
                combined = combined.merge(df, on='date', how='outer')
        
        if combined is not None:
            combined = combined.sort_values('date')
            
            # Save combined view
            self.save_dataframe(
                combined, 
                'combined_monthly',
                description='Combined view of all monthly data',
                source='Derived from other tables'
            )
        
        return combined if combined is not None else pd.DataFrame()
    
    # =========================================================================
    # DATA SUMMARY
    # =========================================================================
    
    def print_summary(self):
        """Print database summary."""
        print("\n" + "="*70)
        print(f"DATABASE SUMMARY: {self.db_path}")
        print("="*70)
        
        metadata = self.get_metadata()
        if metadata.empty:
            print("No tables in database")
            return
        
        for _, row in metadata.iterrows():
            table = row['table_name']
            df = self.load_dataframe(table)
            
            print(f"\n{table}:")
            print(f"  Description: {row.get('description', 'N/A')}")
            print(f"  Source: {row.get('source', 'N/A')}")
            print(f"  Rows: {len(df)}")
            # Safely print columns (handle non-ASCII)
            cols_safe = [str(c).encode('ascii', 'replace').decode() for c in df.columns]
            print(f"  Columns ({len(df.columns)}): {cols_safe[:10]}{'...' if len(df.columns) > 10 else ''}")
            print(f"  Last updated: {row.get('last_updated', 'N/A')}")
            
            if 'date' in df.columns and len(df) > 0:
                print(f"  Date range: {df['date'].min()} to {df['date'].max()}")
        
        print("\n" + "="*70)


# Convenience functions
def get_db() -> DatabaseManager:
    """Get database manager instance."""
    return DatabaseManager()


def query_db(sql: str) -> pd.DataFrame:
    """Quick query function."""
    return get_db().query(sql)


def save_to_db(df: pd.DataFrame, table_name: str, **kwargs) -> bool:
    """Quick save function."""
    return get_db().save_dataframe(df, table_name, **kwargs)


def load_from_db(table_name: str) -> pd.DataFrame:
    """Quick load function."""
    return get_db().load_dataframe(table_name)


# Test function
def test_database():
    """Test database functionality."""
    db = DatabaseManager()
    
    # Test save
    test_df = pd.DataFrame({
        'date': pd.date_range('2024-01-01', periods=5, freq='ME'),
        'value': [1, 2, 3, 4, 5]
    })
    
    db.save_dataframe(test_df, 'test_table', 
                      description='Test table',
                      source='Test')
    
    # Test load
    loaded = db.load_dataframe('test_table')
    print(f"Loaded {len(loaded)} rows")
    
    # Test summary
    db.print_summary()
    
    # Cleanup
    db.drop_table('test_table')


if __name__ == "__main__":
    test_database()
