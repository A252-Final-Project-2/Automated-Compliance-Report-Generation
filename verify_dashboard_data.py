import requests
import re
from html.parser import HTMLParser

print("=== VERIFYING DASHBOARD DATA ===\n")

session = requests.Session()
session.post("http://127.0.0.1:5000/login", data={
    'username': 'developer',
    'password': 'dev123',
    'role': 'Developer'
}, allow_redirects=False)

response = session.get("http://127.0.0.1:5000/")
html = response.text

# Extract project options from dropdown
projects = re.findall(r'<option[^>]*value="([^"]*)"[^>]*>([^<]+)</option>', html)
print(f"Projects in dropdown: {len(projects)} options\n")
for value, label in projects:
    print(f"  • {label} (value={value})")

# Check for Others / Unrelated
if any("Others" in label or "Unrelated" in label for _, label in projects):
    print("\n  ✓ 'Others / Unrelated' project found")
else:
    print("\n  ✗ 'Others / Unrelated' project NOT found")

# Extract defect data from page
defects = re.findall(r'<tr[^>]*data-defect-id="(\d+)"', html)
print(f"\nDefects on page: {len(defects)} defects loaded")
if defects:
    print(f"  Sample IDs: {defects[:5]}")

# Check for PNG and J- units
png_match = re.search(r'PNG-?\d+-\d+', html)
j_match = re.search(r'J-?\d+-\d+', html)
print(f"\nUnit mappings:")
print(f"  {'✓' if png_match else '✗'} PNG units found: {png_match.group() if png_match else 'none'}")
print(f"  {'✓' if j_match else '✗'} J- units found: {j_match.group() if j_match else 'none'}")

# Look for claimant format (name(unit))
claimant_pattern = re.findall(r'>([^<]+\([A-Z0-9\-]+\))<', html)
print(f"\nClaimant names in format 'name(unit)':")
if claimant_pattern:
    for i, name in enumerate(set(claimant_pattern[:3]), 1):
        print(f"  {i}. {name}")
    if len(set(claimant_pattern)) > 3:
        print(f"  ... and {len(set(claimant_pattern))-3} more")
else:
    print("  ✗ No claimant names found in expected format")

print("\n✓ Dashboard verification complete!")
