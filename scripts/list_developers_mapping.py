import os
import json
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.module3.database.db import get_connection

out_path = os.path.join(os.path.dirname(__file__), 'developers_mapping.json')
conn = None
try:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, full_name, unit, role, email, avatar_url FROM users WHERE role = 'Developer' ORDER BY id ASC")
    users = cur.fetchall()
    results = []
    for u in users:
        uid = u[0]
        cur.execute("SELECT username, role FROM login_accounts WHERE user_id = %s LIMIT 1", (uid,))
        la = cur.fetchone()
        results.append({
            'id': uid,
            'full_name': u[1],
            'unit': u[2],
            'role': u[3],
            'email': u[4],
            'avatar_url': u[5] if len(u) > 5 else None,
            'login_account': {'username': la[0], 'role': la[1]} if la else None
        })
    with open(out_path, 'w', encoding='utf-8') as fh:
        fh.write(json.dumps(results, ensure_ascii=False, indent=2))
    print('Wrote', out_path)
except Exception as e:
    print('Error', e)
finally:
    if conn:
        conn.close()
