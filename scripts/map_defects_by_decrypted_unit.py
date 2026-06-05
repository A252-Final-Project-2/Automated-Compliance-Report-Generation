#!/usr/bin/env python3
import os, sys
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)
from app.module3.database.db import get_connection
from app.module3.encryption_utils import decrypt_text

conn = get_connection()
cur = conn.cursor()
try:
    cur.execute("SELECT id, unit FROM defects ORDER BY id DESC LIMIT 200")
    rows = cur.fetchall()
    units = []
    id_unit = []
    for r in rows:
        uid = r[0]
        unit_encrypted = r[1]
        unit_plain = decrypt_text(unit_encrypted) if unit_encrypted else ''
        units.append(unit_plain)
        id_unit.append((uid, unit_plain))
    uniq = sorted(set([u for u in units if u]))
    print('Unique decrypted units count:', len(uniq))
    if uniq:
        cur.execute(
            "SELECT pu.unit_number, dp.project_name FROM project_units pu JOIN developer_projects dp ON pu.project_id = dp.id WHERE pu.unit_number = ANY(%s)",
            (uniq,)
        )
        mapping = {r[0]: r[1] for r in cur.fetchall()}
        print('Found mappings for', len(mapping))
        for uid, up in id_unit[:40]:
            print(uid, up or '<EMPTY>', '->', mapping.get(up) or '<NO MAP>')
finally:
    cur.close()
    conn.close()
