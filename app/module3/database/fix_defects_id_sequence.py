#!/usr/bin/env python3
"""
Script to fix the defects table id column SERIAL sequence issue
Run this once to restore the auto-incrementing id functionality
"""

import os
import sys
import psycopg2
from dotenv import load_dotenv

def _load_env_files():
    """Load environment variables from .env files"""
    module_dir = os.path.dirname(__file__)
    module3_dir = os.path.abspath(os.path.join(module_dir, ".."))
    project_root = os.path.abspath(os.path.join(module3_dir, "..", ".."))
    candidates = [
        os.path.join(project_root, ".env"),
        os.path.join(module3_dir, ".env"),
        os.path.join(module_dir, ".env"),
    ]
    for env_path in candidates:
        if os.path.exists(env_path):
            print(f"Loading env from: {env_path}")
            load_dotenv(env_path, override=False)

def fix_defects_id_sequence():
    """Fix the defects table id SERIAL sequence"""
    _load_env_files()
    
    db_password = os.getenv("DB_PASSWORD")
    if not db_password:
        print("ERROR: DB_PASSWORD is not set in .env")
        return False
    
    db_host = os.getenv("DB_HOST", "localhost")
    db_name = os.getenv("DB_NAME", "compliance_db")
    db_user = os.getenv("DB_USER", "postgres")
    db_port = os.getenv("DB_PORT", "5432")
    
    try:
        conn = psycopg2.connect(
            host=db_host,
            database=db_name,
            user=db_user,
            password=db_password,
            port=db_port,
        )
        cur = conn.cursor()
        
        print("Fixing defects table id sequence...")
        
        # Create sequence if it doesn't exist
        cur.execute("CREATE SEQUENCE IF NOT EXISTS defects_id_seq;")
        print("✓ Sequence created/verified")
        
        # Set the sequence as default for id column
        cur.execute(
            "ALTER TABLE defects ALTER COLUMN id SET DEFAULT nextval('defects_id_seq');"
        )
        print("✓ Column default set to sequence")
        
        # Own the sequence to the table
        cur.execute("ALTER SEQUENCE defects_id_seq OWNED BY defects.id;")
        print("✓ Sequence ownership established")
        
        # Set sequence to start after highest id
        cur.execute(
            "SELECT setval('defects_id_seq', COALESCE((SELECT MAX(id) FROM defects), 0) + 1);"
        )
        print("✓ Sequence position updated")
        
        conn.commit()
        print("\n✅ Defects table id sequence fixed successfully!")
        print("   New defects can now be saved without id errors.")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error fixing defects id sequence: {e}")
        if conn:
            conn.rollback()
        return False
        
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

if __name__ == "__main__":
    success = fix_defects_id_sequence()
    sys.exit(0 if success else 1)
