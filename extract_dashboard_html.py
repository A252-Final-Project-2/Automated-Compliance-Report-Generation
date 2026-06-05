import requests

print("=== EXTRACTING DASHBOARD HTML ===\n")

session = requests.Session()
session.post("http://127.0.0.1:5000/login", data={
    'username': 'developer',
    'password': 'dev123',
    'role': 'Developer'
}, allow_redirects=False)

response = session.get("http://127.0.0.1:5000/")
html = response.text

# Look for project_claimants_map in the page (it's rendered as JavaScript data)
if "project_claimants_map" in html:
    print("✓ Found project_claimants_map in HTML\n")
    
    # Extract the JavaScript variable
    import re
    match = re.search(r'var\s+project_claimants_map\s*=\s*({[^;]+});', html, re.DOTALL)
    if match:
        js_data = match.group(1)
        # Count projects
        projects = re.findall(r'"([^"]+)"\s*:\s*\[', js_data)
        print(f"Projects found: {len(projects)}")
        for p in projects:
            print(f"  • {p}")
    else:
        print("Could not extract project_claimants_map variable")
else:
    print("✗ project_claimants_map not found in HTML")

# Look for available_projects
if "available_projects" in html:
    print("\n✓ Found available_projects in HTML")
else:
    print("\n✗ available_projects not found")

# Check if it's Developer dashboard
if "dashboard_developer" in response.url.lower() or "Developer" in html:
    print("✓ Confirmed Developer dashboard")
else:
    print("? Could not confirm dashboard type")

# Save a sample of the HTML
with open("dashboard_sample.html", "w") as f:
    f.write(html[:3000])
print("\n✓ Saved first 3000 chars to dashboard_sample.html for inspection")
