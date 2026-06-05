#!/usr/bin/env python3
"""Verify the legal_profile schema migration"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db import get_connection

conn = get_connection()
cur = conn.cursor()
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='report_legal_profile' ORDER BY ordinal_position")
columns = [row[0] for row in cur.fetchall()]
print("✅ report_legal_profile columns:")
for col in columns:
    print(f"  • {col}")
cur.close()
conn.close()
