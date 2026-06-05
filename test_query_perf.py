import sys
import time
sys.path.insert(0, 'app/module3')
from database.db import get_connection

conn = get_connection()
cur = conn.cursor()

print("=== TESTING QUERY PERFORMANCE ===\n")

# Simulating Developer role with these projects
project_names = ['skyline kangar harmoni', 'skyline residence johor']

print(f"Projects: {project_names}\n")
print("Running query (with optimized WHERE clause)...")

start = time.time()

cur.execute("""
    SELECT d.id, d.unit, d.description, d.status, COALESCE(dp.project_name, 'Others / Unrelated') as project_name
    FROM defects d
    LEFT JOIN project_units pu ON d.unit = pu.unit_number
    LEFT JOIN developer_projects dp ON pu.project_id = dp.id
    WHERE LOWER(TRIM(COALESCE(dp.project_name, ''))) = ANY(%s) 
       OR pu.id IS NULL
    ORDER BY d.id
""", (project_names,))

rows = cur.fetchall()
elapsed = time.time() - start

print(f"✓ Query completed in {elapsed:.2f}s")
print(f"✓ Returned {len(rows)} defects\n")

for i, row in enumerate(rows[:5], 1):
    print(f"  {i}. ID:{row[0]} Unit:{row[1]:15s} Status:{row[3]:15s} Project:{row[4]}")

if len(rows) > 5:
    print(f"  ... and {len(rows)-5} more")

print(f"\n{'RESULT':-^50}")
if elapsed < 2.0:
    print(f"✓ Query is FAST ({elapsed:.2f}s)")
elif elapsed < 5.0:
    print(f"⚠ Query is SLOW ({elapsed:.2f}s)")
else:
    print(f"✗ Query is TOO SLOW ({elapsed:.2f}s)")

cur.close()
conn.close()
