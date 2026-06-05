#!/usr/bin/env python3
"""
Fill missing emails in report_homeowner_profile from users.email.
This script copies the encrypted email token from `users.email` into
`report_homeowner_profile.email` for rows where the latter is missing or empty.
Run from repo root: python scripts/fill_homeowner_emails.py
"""
import sys
import os
# Ensure repo root is on sys.path so we can import app.module3
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)
from app.module3.database.db import get_connection

SQL_SELECT = """
SELECT p.homeowner_id, u.email
FROM report_homeowner_profile p
JOIN users u ON u.id = p.homeowner_id
WHERE (
    p.email IS NULL
    OR trim(p.email) = ''
    OR trim(p.email) = '-'
    OR trim(p.email) = 'Unknown'
    OR NOT (p.email LIKE 'gAAAA%')
)
AND u.email IS NOT NULL
AND trim(u.email) <> ''
"""

SQL_UPDATE = """
UPDATE report_homeowner_profile p
SET email = u.email, updated_at = NOW()
FROM users u
WHERE p.homeowner_id = u.id
AND (
    p.email IS NULL
    OR trim(p.email) = ''
    OR trim(p.email) = '-'
    OR trim(p.email) = 'Unknown'
    OR NOT (p.email LIKE 'gAAAA%')
)
AND u.email IS NOT NULL
AND trim(u.email) <> ''
RETURNING p.homeowner_id
"""


def main():
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(SQL_SELECT)
        rows = cur.fetchall()
        if not rows:
            print('No missing homeowner emails found to update.')
            return 0

        print(f'Found {len(rows)} homeowner profile(s) to update. Sample IDs: {rows[:10]}')

        cur.execute(SQL_UPDATE)
        updated = cur.fetchall()
        conn.commit()
        print(f'Updated {len(updated)} homeowner profile(s).')
        return 0
    except Exception as e:
        print('Error:', e, file=sys.stderr)
        conn.rollback()
        return 2
    finally:
        cur.close()
        conn.close()


if __name__ == '__main__':
    sys.exit(main())
