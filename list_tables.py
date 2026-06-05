import sys
sys.path.insert(0, 'app/module3')
from database.db import get_connection

conn = get_connection()
cur = conn.cursor()

# List all tables
cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
tables = [row[0] for row in cur.fetchall()]
print('=== DATABASE TABLES ===')
for t in sorted(tables):
    print(f'  {t}')

# Check users table
print("\n=== USERS TABLE ===")
cur.execute("SELECT id, username, role FROM users LIMIT 10")
for row in cur.fetchall():
    print(f'  ID: {row[0]}, Username: {row[1]}, Role: {row[2]}')

cur.close()
conn.close()
