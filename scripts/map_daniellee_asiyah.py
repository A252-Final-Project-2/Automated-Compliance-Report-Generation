#!/usr/bin/env python3
import os, sys, secrets, string
sys.path.insert(0, os.path.abspath('.'))
try:
    from app.module3.database.db import get_connection
except Exception:
    from database.db import get_connection

from werkzeug.security import generate_password_hash

def genpw(n=12):
    alphabet = string.ascii_letters + string.digits + '!@#$%&*'
    return ''.join(secrets.choice(alphabet) for _ in range(n))

conn = get_connection()
cur = conn.cursor()
created = {}
try:
    # Find developer users
    cur.execute("SELECT id, full_name, unit, email FROM users WHERE role = 'Developer' ORDER BY id")
    devs = cur.fetchall()
    # Find legal users
    cur.execute("SELECT id, full_name, unit, email FROM users WHERE role = 'Legal' ORDER BY id")
    legs = cur.fetchall()

    print('Developer users:')
    for d in devs:
        print(d)
    print('\nLegal users:')
    for l in legs:
        print(l)

    # choose dev: look for name match
    dev_id = None
    for d in devs:
        if d[1] and 'daniel' in d[1].lower():
            dev_id = d[0]
            break
    if not dev_id and devs:
        dev_id = devs[0][0]

    # choose legal
    legal_id = None
    for l in legs:
        if l[1] and 'aisyah' in l[1].lower():
            legal_id = l[0]
            break
    if not legal_id and legs:
        legal_id = legs[0][0]

    print('\nSelected mappings:')
    print('dev_id=', dev_id, 'legal_id=', legal_id)

    # ensure login_accounts for daniellee
    for username, role, uid in [('daniellee', 'Developer', dev_id), ('asiyah', 'Legal', legal_id)]:
        if uid is None:
            print(f"Warning: no user id found for role {role}; creating login without user mapping")
        cur.execute("SELECT username, role, user_id FROM login_accounts WHERE LOWER(username)=LOWER(%s) LIMIT 1", (username,))
        if cur.fetchone():
            cur.execute("UPDATE login_accounts SET role=%s, user_id=%s, is_active=TRUE WHERE LOWER(username)=LOWER(%s)", (role, uid, username))
            print(f'Updated existing login: {username} -> user_id={uid}')
        else:
            pw = genpw()
            cur.execute("INSERT INTO login_accounts (username, password, role, user_id, is_active) VALUES (%s, %s, %s, %s, TRUE)", (username, generate_password_hash(pw), role, uid))
            created[username] = pw
            print(f'Created login: {username} -> user_id={uid} (password printed below)')

    conn.commit()
finally:
    cur.close()
    conn.close()

if created:
    print('\nNew credentials:')
    for u,p in created.items():
        print(f"{u}\t{p}")
else:
    print('\nNo new credentials created.')
