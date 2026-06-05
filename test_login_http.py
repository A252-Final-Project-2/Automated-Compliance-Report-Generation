import requests
import sys

print("=== TESTING LOGIN VIA HTTP ===\n")

url = "http://127.0.0.1:5000/login"
session = requests.Session()

# Test login
data = {
    'username': 'developer',
    'password': 'dev123',
    'role': 'Developer'
}

print(f"Posting to {url}")
print(f"Data: {data}\n")

response = session.post(url, data=data, allow_redirects=False)
print(f"Response Status: {response.status_code}")
print(f"Response Headers:\n  Location: {response.headers.get('Location', 'N/A')}")
print(f"Response Cookies: {session.cookies}\n")

if response.status_code == 302:
    print("✓ Login successful (redirect)")
    # Try to access dashboard
    print("\nAttempting to access dashboard...")
    dashboard_url = response.headers.get('Location', '/')
    if not dashboard_url.startswith('http'):
        dashboard_url = f"http://127.0.0.1:5000{dashboard_url}"
    
    dashboard_response = session.get(dashboard_url)
    print(f"Dashboard Status: {dashboard_response.status_code}")
    print(f"Dashboard Title: {dashboard_response.text[dashboard_response.text.find('<title>')+7:dashboard_response.text.find('</title>')]}")
else:
    print(f"✗ Login failed")
    print(f"Response Text (first 500 chars):\n{response.text[:500]}")
