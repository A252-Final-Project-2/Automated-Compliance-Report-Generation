#!/usr/bin/env python
"""Clear old reports from database and backup files"""
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))

from app.module3.database.db import get_connection

conn = get_connection()
cur = conn.cursor()

# Delete all old reports from database
cur.execute("DELETE FROM report_versions")
rows_deleted = cur.rowcount
conn.commit()
print(f"✓ Deleted {rows_deleted} old reports from database")

# Verify it's empty
cur.execute("SELECT COUNT(*) FROM report_versions")
count = cur.fetchone()[0]
print(f"✓ Report versions table now has {count} records")

conn.close()

# Also delete the backup file
backup_file = os.path.join(os.path.dirname(__file__), "app", "module3", "audit_data", "backup_versions.json")
if os.path.exists(backup_file):
    os.remove(backup_file)
    print(f"✓ Deleted backup_versions.json")
else:
    print(f"✓ backup_versions.json not found (already deleted)")

print("\n✅ Database and backups cleaned. Fresh reports will be generated with 'AI DISCLAIMER:' on next generation.")
