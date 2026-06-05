import sys
sys.path.insert(0, 'app/module3')
from database.db import get_connection

conn = get_connection()
cur = conn.cursor()

# Test the query directly to see if it includes unmapped defects

# Get available projects for a Developer (assumed to have some projects)
available_projects = [
    'skyline kangar harmoni',
    'skyline residence johor', 
    'skyline kedah residence'
]

print("=== Testing Developer Query Fix ===")
print(f"Available projects (normalized): {available_projects}")
print()

# This is the query from get_defects_for_role with the fix
cur.execute("""
    SELECT d.id, d.unit, d.description, d.status, COALESCE(dp.project_name, 'NULL') as project_name
    FROM defects d
    LEFT JOIN project_units pu ON d.unit = pu.unit_number
    LEFT JOIN developer_projects dp ON pu.project_id = dp.id
    WHERE LOWER(TRIM(COALESCE(dp.project_name, ''))) = ANY(%s) OR dp.project_name IS NULL
    ORDER BY d.id
""", (available_projects,))

print("Defects returned with fixed query (includes unmapped):")
rows = cur.fetchall()
for row in rows:
    from encryption_utils import decrypt_text
    unit = decrypt_text(row[1]) if row[1] else 'NULL'
    print(f'  ID: {row[0]}, Unit: {unit}, Status: {row[3]}, Project: {row[4]}')

print(f"\nTotal: {len(rows)} defects")

# Now test the OLD query to show the difference
print("\n=== Old Query (WITHOUT fix) ===")
cur.execute("""
    SELECT d.id, d.unit, d.description, d.status, COALESCE(dp.project_name, 'NULL') as project_name
    FROM defects d
    LEFT JOIN project_units pu ON d.unit = pu.unit_number
    LEFT JOIN developer_projects dp ON pu.project_id = dp.id
    WHERE LOWER(TRIM(COALESCE(dp.project_name, ''))) = ANY(%s)
    ORDER BY d.id
""", (available_projects,))

print("Defects returned with OLD query (excludes unmapped):")
rows_old = cur.fetchall()
for row in rows_old:
    from encryption_utils import decrypt_text
    unit = decrypt_text(row[1]) if row[1] else 'NULL'
    print(f'  ID: {row[0]}, Unit: {unit}, Status: {row[3]}, Project: {row[4]}')

print(f"\nTotal: {len(rows_old)} defects")

missing = len(rows) - len(rows_old)
print(f"\n✓ Fixed query retrieves {missing} additional unmapped defects!")

cur.close()
conn.close()
