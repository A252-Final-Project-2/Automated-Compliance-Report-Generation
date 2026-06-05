import sys
import time
sys.path.insert(0, 'app/module3')

print("=== DEBUGGING CONTEXT BUILDER TIMING ===\n")

# Patch the function to add timing
import report_data
original_get_homeowner_claimants = report_data.get_homeowner_claimants
original_get_available_projects = report_data.get_available_projects

def timed_get_homeowner_claimants(*args, **kwargs):
    start = time.time()
    result = original_get_homeowner_claimants(*args, **kwargs)
    elapsed = time.time() - start
    print(f"  get_homeowner_claimants(...) took {elapsed:.2f}s, returned {len(result)} rows")
    return result

def timed_get_available_projects(*args, **kwargs):
    start = time.time()
    result = original_get_available_projects(*args, **kwargs)
    elapsed = time.time() - start
    print(f"  get_available_projects(...) took {elapsed:.2f}s, returned {len(result)} rows")
    return result

report_data.get_homeowner_claimants = timed_get_homeowner_claimants
report_data.get_available_projects = timed_get_available_projects

# Now test
from routes import _build_project_dashboard_context

print("Building context for Developer role (user_id=1)...\n")
start = time.time()

context = _build_project_dashboard_context('Developer', 1)

elapsed = time.time() - start
print(f"\nTotal time: {elapsed:.2f}s")
