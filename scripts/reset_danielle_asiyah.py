#!/usr/bin/env python3
import os
import sys
import secrets
import string

sys.path.insert(0, os.path.abspath('.'))
try:
    from app.module3.database.db import get_connection
except Exception:
    # fallback for direct execution
    from database.db import get_connection

try:
    from werkzeug.security import generate_password_hash
except Exception:
    def generate_password_hash(x):
        return x

TARGETS = ['danielle', 'asiyah']

def gen_password(length=12):
    alphabet = string.ascii_letters + string.digits + "!@#$%&*"
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def main():
    conn = get_connection()
    cur = conn.cursor()
    try:
        # Capture existing roles if present
        roles = {}
        for u in TARGETS:
            cur.execute("SELECT role FROM login_accounts WHERE LOWER(username) = LOWER(%s) LIMIT 1", (u,))
            r = cur.fetchone()
            roles[u] = r[0] if r and r[0] else None

        # Delete existing accounts for these usernames
        cur.execute("DELETE FROM login_accounts WHERE LOWER(username) IN (%s, %s)", (TARGETS[0], TARGETS[1]))

        creds = {}
        for u in TARGETS:
            role = roles[u] or 'Homeowner'
            pw = gen_password()
            hashed = generate_password_hash(pw)
            cur.execute(
                """
                INSERT INTO login_accounts (username, password, role, user_id, is_active)
                VALUES (%s, %s, %s, %s, TRUE)
                ON CONFLICT (username) DO UPDATE
                SET password = EXCLUDED.password, role = EXCLUDED.role, is_active = TRUE
                """,
                (u, hashed, role, None),
            )
            creds[u] = {'username': u, 'password': pw, 'role': role}

        conn.commit()
    finally:
        cur.close()
        conn.close()

    # Print credentials to stdout
    for u in TARGETS:
        info = creds[u]
        print(f"{info['username']}\trole={info['role']}\tpassword={info['password']}")

if __name__ == '__main__':
    main()
