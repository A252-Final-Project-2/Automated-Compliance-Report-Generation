import sys
sys.path.insert(0, 'app/module3')
from database.db import get_connection

conn = get_connection()
cur = conn.cursor()

print("=== CHECKING LOGIN USERS ===\n")

# Check login_accounts table
cur.execute("SELECT username, role, user_id, is_active FROM login_accounts LIMIT 10")
accounts = cur.fetchall()
print(f"Found {len(accounts)} login accounts:")
for username, role, user_id, is_active in accounts:
    status = "✓ Active" if is_active else "✗ Inactive"
    print(f"  {username:15s} | Role: {role:10s} | UserID: {user_id} | {status}")

if not accounts:
    print("  ⚠️  NO LOGIN ACCOUNTS FOUND!")
    print("\n  Creating test accounts...")
    
    # Create test users first
    cur.execute("INSERT INTO users (full_name, email, role) VALUES (%s, %s, %s) RETURNING id",
                ("Test Homeowner 1", "homeowner1@test.com", "Homeowner"))
    homeowner_id = cur.fetchone()[0]
    
    cur.execute("INSERT INTO users (full_name, email, role) VALUES (%s, %s, %s) RETURNING id",
                ("Test Developer 1", "developer1@test.com", "Developer"))
    developer_id = cur.fetchone()[0]
    
    # Create login accounts
    from encryption_utils import encrypt_text
    pass1 = encrypt_text("pass123")
    pass2 = encrypt_text("dev123")
    
    cur.execute("""
        INSERT INTO login_accounts (username, password, role, user_id, is_active)
        VALUES (%s, %s, %s, %s, TRUE)
    """, ("homeowner1", pass1, "Homeowner", homeowner_id))
    
    cur.execute("""
        INSERT INTO login_accounts (username, password, role, user_id, is_active)
        VALUES (%s, %s, %s, %s, TRUE)
    """, ("developer", pass2, "Developer", developer_id))
    
    conn.commit()
    print(f"  ✓ Created homeowner1 (ID: {homeowner_id})")
    print(f"  ✓ Created developer (ID: {developer_id})")

print("\n=== USERS IN DATABASE ===\n")
cur.execute("SELECT id, full_name, role FROM users LIMIT 10")
users = cur.fetchall()
for user_id, full_name, role in users:
    print(f"  ID: {user_id:3d} | {full_name:25s} | {role}")

cur.close()
conn.close()

print("\n✓ Setup complete. Try logging in with:")
print("  Username: homeowner1")
print("  Password: pass123")
print("  Role: Homeowner")
print("\n  OR")
print("\n  Username: developer")
print("  Password: dev123")
print("  Role: Developer")
