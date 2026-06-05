#!/usr/bin/env python3
"""
Fix defect remarks (mailbox -> tile) and update AI disclaimer text.
"""
import os
import json
import shutil
from datetime import datetime

# Add module path
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app', 'module3'))

from database.db import get_connection

def fix_defect_remarks():
    """Update defect 121 remarks from mailbox to tile."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        # Fix remarks for defect 121
        cur.execute(
            """
            UPDATE remarks
            SET remark = %s
            WHERE defect_id = 121
            AND remark = %s
            """,
            ("The tile has not been repaired yet", "The damaged mailbox has not been repaired yet")
        )
        conn.commit()
        rows = cur.rowcount
        print(f"[OK] Updated {rows} remark(s) for defect 121")
    except Exception as e:
        print(f"[ERROR] Failed to update remarks: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

def clear_cache():
    """Clear cache directory to force regeneration."""
    cache_dir = os.path.join(os.path.dirname(__file__), 'app', 'module3', 'cache')
    if os.path.isdir(cache_dir):
        try:
            shutil.rmtree(cache_dir)
            os.makedirs(cache_dir, exist_ok=True)
            # Recreate subdirectories
            for subdir in ['defects', 'fields', 'remarks', 'reports']:
                os.makedirs(os.path.join(cache_dir, subdir), exist_ok=True)
            print(f"[OK] Cleared cache directory: {cache_dir}")
        except Exception as e:
            print(f"[ERROR] Failed to clear cache: {e}")

def update_ai_disclaimer():
    """Update AI disclaimer in report_generator.py to match BM version."""
    routes_file = os.path.join(os.path.dirname(__file__), 'app', 'module3', 'routes.py')
    
    old_disclaimer = (
        "This report was generated with the assistance of an artificial intelligence (AI) system "
        "for the purpose of organising and summarising information based on records submitted by the Claimant. "
        "This report is provided to present information in a clear and neutral manner and should not be construed as legal advice. "
        "The AI system bears no responsibility for any action taken based on this report, and this report does not replace "
        "the determination or decision of the Malaysia Consumer Claims Tribunal."
    )
    
    new_disclaimer = (
        "This report was generated with the assistance of an artificial intelligence (AI) system "
        "for the purpose of organising and summarising information based on records submitted by the Claimant. "
        "This report is provided to present information in a clear and neutral manner and should not be construed as legal advice. "
        "The AI system bears no responsibility for any action taken based on this report, and this report does not replace "
        "or affect the determination or decision of the Malaysia Consumer Claims Tribunal."
    )
    
    try:
        with open(routes_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        if old_disclaimer in content:
            content = content.replace(old_disclaimer, new_disclaimer)
            with open(routes_file, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"[OK] Updated AI disclaimer in routes.py")
        else:
            print(f"[INFO] AI disclaimer not found or already updated in routes.py")
    except Exception as e:
        print(f"[ERROR] Failed to update AI disclaimer: {e}")

if __name__ == '__main__':
    print("=" * 60)
    print("Fixing defect remarks and clearing cache...")
    print("=" * 60)
    fix_defect_remarks()
    clear_cache()
    update_ai_disclaimer()
    print("=" * 60)
    print("Done!")
