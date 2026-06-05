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
    cur.execute("SELECT id, unit FROM defects ORDER BY id DESC")
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
    print('Total unique decrypted units:', len(uniq))

    issues = []
    # Build mapping for normalized unit numbers
    normalized = [u.strip().lower() for u in uniq]
    if normalized:
        cur.execute(
            "SELECT LOWER(TRIM(pu.unit_number)) AS unit_norm, dp.project_name, dp.state_name FROM project_units pu JOIN developer_projects dp ON pu.project_id = dp.id WHERE LOWER(TRIM(pu.unit_number)) = ANY(%s)",
            (normalized,)
        )
        mapping = {r[0]: {'project_name': r[1], 'state_name': r[2]} for r in cur.fetchall()}
    else:
        mapping = {}

    png_ok = []
    png_missing = []
    johor_ok = []
    johor_missing = []

    for u in uniq:
        norm = u.strip().lower()
        if not norm:
            continue
        if norm.startswith('png') or 'png' in norm:
            m = mapping.get(norm)
            state = (m.get('state_name') or '').lower() if m else ''
            if m and (('penang' in state) or ('pinang' in state)):
                png_ok.append((u, m.get('project_name')))
            else:
                png_missing.append((u, m.get('project_name') if m else None))
        if norm.startswith('j-') or 'j-' in norm:
            m = mapping.get(norm)
            if m and m.get('state_name') and 'johor' in (m.get('state_name') or '').lower():
                johor_ok.append((u, m.get('project_name')))
            else:
                johor_missing.append((u, m.get('project_name') if m else None))

    print('\nPNG units mapped correctly (count={}):'.format(len(png_ok)))
    for u,p in png_ok[:50]:
        print('  ', u, '->', p)
    print('\nPNG units missing/wrong mapping (count={}):'.format(len(png_missing)))
    for u,p in png_missing[:200]:
        print('  ', u, '->', p)

    print('\nJohor units mapped correctly (count={}):'.format(len(johor_ok)))
    for u,p in johor_ok[:50]:
        print('  ', u, '->', p)
    print('\nJohor units missing/wrong mapping (count={}):'.format(len(johor_missing)))
    for u,p in johor_missing[:200]:
        print('  ', u, '->', p)

    # Print a short summary of other unmapped units
    other_unmapped = [u for u in uniq if u.strip().lower() not in mapping]
    print('\nTotal units without any project_unit mapping:', len(other_unmapped))
    if other_unmapped:
        print('Sample unmapped:', other_unmapped[:20])

finally:
    cur.close()
    conn.close()
