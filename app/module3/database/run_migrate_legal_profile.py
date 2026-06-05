#!/usr/bin/env python3
"""
Migration runner for legal_profile schema update
Executes the migration SQL to add legal_user_id column
"""

import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db import get_connection

def run_migration():
    """Execute the legal profile migration"""
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        migration_file = os.path.join(
            os.path.dirname(__file__),
            'migrate_legal_profile.sql'
        )
        
        with open(migration_file, 'r') as f:
            migration_sql = f.read()
        
        print("🔄 Running legal_profile migration...")
        print(migration_sql)
        print()
        
        # Execute the migration
        cur.execute(migration_sql)
        conn.commit()
        
        print("✅ Migration completed successfully!")
        print("✅ Column 'legal_user_id' added to report_legal_profile")
        print("✅ Foreign key constraint applied")
        
        return True
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        conn.rollback()
        return False
    finally:
        cur.close()
        conn.close()

if __name__ == '__main__':
    success = run_migration()
    sys.exit(0 if success else 1)
