#!/usr/bin/env python3
import os, sys
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)
from app.module3.database.db import get_connection

def main():
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id, unit_number, project_id FROM project_units ORDER BY id DESC LIMIT 40")
        rows = cur.fetchall()
        print('Recent project_units:')
        for r in rows:
            print(r)
    finally:
        cur.close()
        conn.close()

if __name__ == '__main__':
    main()
