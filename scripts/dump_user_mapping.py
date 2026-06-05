import os
import json
import sys

# Ensure app module can be imported from workspace
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from app.module3.database.db import get_connection
except Exception as e:
    print('Import error:', e)
    raise

if __name__ == '__main__':
    username = os.getenv('DIAG_USERNAME', 'daniellee')
    out_path = os.path.join(os.path.dirname(__file__), f'user_mapping_{username}.json')

    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT username, role, user_id, is_active FROM login_accounts WHERE LOWER(username) = LOWER(%s) LIMIT 1", (username,))
        la = cur.fetchone()

        user_row = None
        if la and la[2]:
            cur.execute("SELECT id, full_name, unit, role, email, avatar_url FROM users WHERE id = %s LIMIT 1", (la[2],))
            user_row = cur.fetchone()

        # Also try to find any users with matching full_name or username mapping
        cur.execute("SELECT id, full_name, unit, role, email FROM users WHERE LOWER(full_name) LIKE LOWER(%s) LIMIT 5", (f"%{username}%",))
        possible_users = cur.fetchall()

        payload = {
            'queried_username': username,
            'login_account': None,
            'mapped_user': None,
            'possible_users_by_full_name': [],
        }

        if la:
            payload['login_account'] = {
                'username': la[0],
                'role': la[1],
                'user_id': la[2],
                'is_active': la[3],
            }

        if user_row:
            payload['mapped_user'] = {
                'id': user_row[0],
                'full_name': user_row[1],
                'unit': user_row[2],
                'role': user_row[3],
                'email': user_row[4],
                'avatar_url': user_row[5] if len(user_row) > 5 else None,
            }

        for pu in possible_users:
            payload['possible_users_by_full_name'].append({
                'id': pu[0],
                'full_name': pu[1],
                'unit': pu[2],
                'role': pu[3],
                'email': pu[4],
            })

        with open(out_path, 'w', encoding='utf-8') as fh:
            fh.write(json.dumps(payload, ensure_ascii=False, indent=2))

        print('Wrote', out_path)
    except Exception as e:
        print('Error:', e)
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass
