#!/usr/bin/env python3
"""
Inspect defects grouped by project_name.
Run: python scripts/inspect_defects_by_project.py
"""
import os, sys
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)
from app.module3.database.db import get_connection

def main():
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT COALESCE(dp.project_name, '') as project_name, COUNT(*)
            FROM defects d
            LEFT JOIN project_units pu ON d.unit = pu.unit_number
            LEFT JOIN developer_projects dp ON pu.project_id = dp.id
            GROUP BY COALESCE(dp.project_name, '')
            ORDER BY COUNT(*) DESC
        """)
        rows = cur.fetchall()
        print('Defect counts by project_name:')
        for r in rows:
            print(f"{r[0] or '<EMPTY>'}: {r[1]}")

        cur.execute("""
            SELECT d.id, d.unit, dp.project_name
            FROM defects d
            LEFT JOIN project_units pu ON d.unit = pu.unit_number
            LEFT JOIN developer_projects dp ON pu.project_id = dp.id
            ORDER BY d.id DESC
            LIMIT 20
        """)
        print('\nSample defects:')
        for r in cur.fetchall():
            print(r)
    finally:
        cur.close()
        conn.close()

if __name__ == '__main__':
    main()
