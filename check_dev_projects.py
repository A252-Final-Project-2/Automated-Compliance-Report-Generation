import sys
sys.path.insert(0, 'app/module3')
from database.db import get_connection

conn = get_connection()
cur = conn.cursor()

print("=== CHECK PLS-01-02 MAPPING ===")

# Check if PLS-01-02 is in project_units
cur.execute("""
    SELECT pu.unit_number, dp.project_name, dp.state_name 
    FROM project_units pu
    JOIN developer_projects dp ON pu.project_id = dp.id
    WHERE pu.unit_number = 'PLS-01-02'
""")

result = cur.fetchone()
if result:
    print(f"✓ PLS-01-02 maps to: {result[1]} (State: {result[2]})")
else:
    print("✗ PLS-01-02 NOT in project_units table!")

print("\n=== DEVELOPER USER PROJECTS ===")
# Check what projects developer user has
cur.execute("""
    SELECT DISTINCT dp.project_name, dp.state_name
    FROM developer_projects dp
    JOIN developer_users du ON du.project_id = dp.id
    WHERE du.user_id = (SELECT id FROM users WHERE username = 'developer' LIMIT 1)
    ORDER BY dp.project_name
""")

dev_projects = cur.fetchall()
print(f"Developer has access to {len(dev_projects)} projects:")
for proj_name, state in dev_projects:
    print(f"  - {proj_name} ({state})")

print("\n=== ISSUE ===")
if not dev_projects:
    print("⚠ Developer user has NO project assignments!")
    print("This means the query returns NO defects (filtered out)")
else:
    # Check if PLS project is in their list
    pls_found = any("Kangar" in name or "Perlis" in state for name, state in dev_projects)
    if pls_found:
        print("✓ Developer HAS access to Perlis/Kangar project")
        print("✓ PLS-01-02 SHOULD appear mapped to Perlis")
    else:
        print("✗ Developer does NOT have access to Perlis/Kangar project")
        print("✗ PLS-01-02 will appear as unmapped (going to 'Others / Unrelated')")

cur.close()
conn.close()
