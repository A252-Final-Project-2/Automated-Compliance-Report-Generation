import requests
import time

print("=== TESTING FIXED LOGIN + DASHBOARD ACCESS ===\n")

url = "http://127.0.0.1:5000/login"
session = requests.Session()

# Test login
data = {
    'username': 'developer',
    'password': 'dev123',
    'role': 'Developer'
}

print(f"1. Posting login to {url}")
response = session.post(url, data=data, allow_redirects=False, timeout=30)
print(f"   Status: {response.status_code}")

if response.status_code == 302:
    print("   ✓ Login successful\n")
    
    # Access dashboard
    print("2. Accessing dashboard (this may take 15-20 seconds)...")
    start = time.time()
    dashboard_response = session.get("http://127.0.0.1:5000/", timeout=60)
    elapsed = time.time() - start
    print(f"   Status: {dashboard_response.status_code}")
    print(f"   Time: {elapsed:.1f}s\n")
    
    if dashboard_response.status_code == 200:
        print("   ✓ Dashboard loaded successfully!\n")
        
        # Extract some info
        if "Project" in dashboard_response.text or "project" in dashboard_response.text.lower():
            print("   ✓ Dashboard contains project information")
        if "defect" in dashboard_response.text.lower() or "unit" in dashboard_response.text.lower():
            print("   ✓ Dashboard contains defect information")
    else:
        print(f"   ✗ Dashboard failed: {dashboard_response.status_code}")
else:
    print(f"   ✗ Login failed: {response.status_code}")

print("\n✓ Test complete!")
