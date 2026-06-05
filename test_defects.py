import sys
sys.path.insert(0, 'app/module3')
from routes import get_defects_for_role

defects = get_defects_for_role('Developer')
print(f'Total defects for Developer: {len(defects)}')
print()
for d in defects:
    print(f'Unit: {d["unit"]}, Project: {d["project_name"]}')
