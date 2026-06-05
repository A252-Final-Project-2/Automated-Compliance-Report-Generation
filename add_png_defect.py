import sys
sys.path.insert(0, 'app/module3')
from database.db import get_connection
from encryption_utils import encrypt_text

conn = get_connection()
cur = conn.cursor()

# Add test PNG defect
encrypted_unit = encrypt_text("PNG-01-02")
cur.execute("""
    INSERT INTO defects (unit, description, reported_date, status, user_id, urgency)
    VALUES (%s, %s, NOW(), %s, %s, %s)
""", (encrypted_unit, "Test PNG defect", "Pending", 1, "High"))

conn.commit()
print("✓ Added PNG-01-02 defect with status 'Pending'")

# Check all defects now
print("\n=== ALL DEFECTS ===")
cur.execute('SELECT id, unit, status FROM defects ORDER BY id')
for row in cur.fetchall():
    from encryption_utils import decrypt_text
    unit = decrypt_text(row[1]) if row[1] else row[1]
    print(f'  ID: {row[0]}, Unit: {unit}, Status: {row[2]}')

cur.close()
conn.close()
