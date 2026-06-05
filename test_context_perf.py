import sys
import time
sys.path.insert(0, 'app/module3')
from routes import _build_project_dashboard_context

print("=== TESTING CONTEXT BUILDER PERFORMANCE ===\n")

print("Building context for Developer role...")
start = time.time()

try:
    context = _build_project_dashboard_context('Developer', 1)
    elapsed = time.time() - start
    
    print(f"✓ Context built in {elapsed:.2f}s\n")
    
    print("Context keys:", list(context.keys()))
    print(f"Available projects: {len(context.get('available_projects', []))} projects")
    print(f"Project claimants map: {len(context.get('project_claimants_map', {}))} entries")
    print(f"Homeowner claimants: {len(context.get('homeowner_claimants', []))} claimants")
    
    # Show sample data
    if context.get('available_projects'):
        print(f"\nFirst 3 projects:")
        for p in context['available_projects'][:3]:
            print(f"  - {p.get('project_name', 'N/A')}")
    
    if context.get('project_claimants_map'):
        print(f"\nFirst 3 project entries:")
        for i, (proj, claimants) in enumerate(list(context['project_claimants_map'].items())[:3]):
            print(f"  - {proj}: {len(claimants)} claimants")
    
    if elapsed < 2.0:
        print(f"\n✓ Context building is FAST")
    elif elapsed < 5.0:
        print(f"\n⚠ Context building is SLOW")
    else:
        print(f"\n✗ Context building is TOO SLOW ({elapsed:.2f}s)")
        
except Exception as e:
    elapsed = time.time() - start
    print(f"✗ Error building context in {elapsed:.2f}s:")
    print(f"  {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
