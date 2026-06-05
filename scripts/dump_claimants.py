import os
import json
import sys

# Ensure app module can be imported from workspace
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from app.module3.report_data import get_homeowner_claimants
    from app.module3.database.db import get_connection
except Exception as e:
    print('Import error:', e)
    raise

if __name__ == '__main__':
    # Use env var to control role and user id if needed
    role = os.getenv('DIAG_ROLE', 'Developer')
    user_id = os.getenv('DIAG_USER_ID')
    try:
        user_id = int(user_id) if user_id else None
    except Exception:
        user_id = None

    claimants = get_homeowner_claimants(respondent_id=user_id, project_name=None, role=role, include_unrestricted=True)
    out_path = os.path.join(os.path.dirname(__file__), 'claimants_dump.json')
    with open(out_path, 'w', encoding='utf-8') as fh:
        fh.write(json.dumps(claimants, ensure_ascii=False, indent=2))
    print('Wrote', out_path)
