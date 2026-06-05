#!/usr/bin/env python3
import os, sys
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)
from app.module3.database.db import get_connection

conn = get_connection()
cur = conn.cursor()
try:
    cur.execute("SELECT id, project_name, state_name FROM developer_projects ORDER BY id")
    for r in cur.fetchall():
        print(r)
finally:
    cur.close()
    conn.close()
