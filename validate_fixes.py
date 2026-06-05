#!/usr/bin/env python3
"""Validate that the performance fixes work correctly."""
import sys
import os
sys.path.insert(0, 'app')
sys.path.insert(0, 'app/module3')

# Set environment
os.environ.setdefault('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/compliance_report')

from flask import Flask

# Create Flask app
app = Flask(__name__, template_folder='app/module3/templates')
app.config['TESTING'] = True
app.config['SECRET_KEY'] = 'test'
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']

# Register bluepmarks
from module3.routes import routes
app.register_blueprint(routes)

# Import to trigger schema initialization
from module3.report_data import ensure_profile_encryption_at_rest

with app.app_context():
    ensure_profile_encryption_at_rest()
    print('OK Schema initialized')

# Create test client
client = app.test_client()

# 1. LOGIN
print('TEST Login')
response = client.post('/login', data={
    'username': 'homeowner',
    'password': 'home123',
    'remember_me': 'on'
})
print(f'  Status: {response.status_code}')
if response.status_code == 302:
    print(f'  OK Redirected to: {response.location}')

# 2. SAVE HOMEOWNER CLAIM DETAILS
print('TEST Save claim details')
save_response = client.post('/save_homeowner_claim_details', json={
    'court_location': 'Tribunal Tuntutan Kecil Kuala Lumpur',
    'state_name': 'Kuala Lumpur',
    'item_service': 'Defect Repair During DLP',
    'transaction_date': '2023-01-15',
    'claim_amount': '50000'
})
print(f'  Status: {save_response.status_code}')
import json
try:
    resp = json.loads(save_response.data.decode())
    print(f'  Response: {resp}')
except:
    print(f'  Response (not JSON): {save_response.data.decode()[:100]}')

# 3. GENERATE REPORT
print('TEST Generate report')
report_response = client.post('/generate_report', json={
    'language': 'en'
})
print(f'  Status: {report_response.status_code}')
try:
    resp_data = json.loads(report_response.data.decode())
    if 'error' in resp_data:
        print(f'  Error: {resp_data.get("error")}')
        if 'details' in resp_data:
            print(f'  Details: {resp_data.get("details")}')
    elif 'report_html' in resp_data:
        html_len = len(resp_data['report_html'])
        print(f'  OK Report generated ({html_len} bytes)')
    else:
        print(f'  Keys: {list(resp_data.keys())}')
except Exception as e:
    print(f'  Error parsing response: {e}')
    print(f'  Raw: {report_response.data.decode()[:200]}')
