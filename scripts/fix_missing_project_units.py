#!/usr/bin/env python3
"""
Infer and insert missing project_units mappings from defect owner project profiles.

Logic:
- Read defects.unit (decrypt if needed)
- Skip units that already exist in project_units
- Infer project_name from report_homeowner_profile.project_name using defects.user_id
- Resolve project_id via developer_projects.project_name (case-insensitive)
- Insert missing (project_id, unit_number) pairs safely

Usage:
  python scripts/fix_missing_project_units.py --apply
  python scripts/fix_missing_project_units.py          # dry-run
"""

import os
import sys

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from app.module3.database.db import get_connection
from app.module3.encryption_utils import decrypt_text

STATE_PREFIX_MAP = {
    "JHR": "Johor",
    "KDH": "Kedah",
    "KTN": "Kelantan",
    "MLK": "Melaka",
    "NSN": "Negeri Sembilan",
    "PHG": "Pahang",
    "PNG": "Pulau Pinang",
    "PRK": "Perak",
    "PLS": "Perlis",
    "SBH": "Sabah",
    "SWK": "Sarawak",
    "SGR": "Selangor",
    "TRG": "Terengganu",
    "KUL": "Kuala Lumpur",
    "LBN": "Labuan",
    "PJY": "Putrajaya",
}


def normalize_text(value):
    return (value or '').strip().lower()


def main(apply_changes=False):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id, user_id, unit FROM defects ORDER BY id ASC")
        defects = cur.fetchall()

        cur.execute("SELECT unit_number, project_id FROM project_units")
        existing_rows = cur.fetchall()
        existing_unit_to_projects = {}
        for unit_number, project_id in existing_rows:
            unit_clean = (unit_number or '').strip()
            if not unit_clean:
                continue
            existing_unit_to_projects.setdefault(unit_clean, set()).add(project_id)

        homeowner_project_cache = {}
        project_id_cache = {}
        homeowner_known_project_counts = {}
        cur.execute("SELECT id, project_name, state_name FROM developer_projects")
        developer_projects = cur.fetchall()

        candidates = {}
        skipped_existing = 0
        skipped_no_unit = 0
        skipped_no_project = 0
        skipped_no_project_id = 0
        conflicts = []

        # Build homeowner-level known project hints from already-mapped units.
        for defect_id, homeowner_id, encrypted_unit in defects:
            unit_plain = (decrypt_text(encrypted_unit) or '').strip()
            if not unit_plain:
                continue
            mapped_projects = existing_unit_to_projects.get(unit_plain) or set()
            if homeowner_id is None or not mapped_projects:
                continue
            homeowner_known_project_counts.setdefault(homeowner_id, {})
            for pid in mapped_projects:
                homeowner_known_project_counts[homeowner_id][pid] = homeowner_known_project_counts[homeowner_id].get(pid, 0) + 1

        for defect_id, homeowner_id, encrypted_unit in defects:
            unit_plain = (decrypt_text(encrypted_unit) or '').strip()
            if not unit_plain:
                skipped_no_unit += 1
                continue

            if unit_plain in existing_unit_to_projects:
                skipped_existing += 1
                continue

            if homeowner_id not in homeowner_project_cache:
                cur.execute(
                    "SELECT project_name FROM report_homeowner_profile WHERE homeowner_id = %s LIMIT 1",
                    (homeowner_id,),
                )
                row = cur.fetchone()
                homeowner_project_cache[homeowner_id] = (decrypt_text(row[0]) if row and row[0] else '').strip()

            project_id = None

            # Heuristic 1: homeowner profile project_name exact match
            project_name = homeowner_project_cache.get(homeowner_id, '')
            if project_name:
                project_key = normalize_text(project_name)
                if project_key not in project_id_cache:
                    cur.execute(
                        """
                        SELECT id
                        FROM developer_projects
                        WHERE LOWER(TRIM(project_name)) = LOWER(TRIM(%s))
                        LIMIT 1
                        """,
                        (project_name,),
                    )
                    proj = cur.fetchone()
                    project_id_cache[project_key] = proj[0] if proj else None
                project_id = project_id_cache.get(project_key)

            # Heuristic 2: unit prefix -> state_name -> project
            if not project_id:
                prefix = unit_plain.split('-', 1)[0].strip().upper()
                state_name = STATE_PREFIX_MAP.get(prefix)
                if state_name:
                    matching_projects = [
                        p for p in developer_projects
                        if normalize_text(p[2]) == normalize_text(state_name)
                    ]
                    if len(matching_projects) == 1:
                        project_id = matching_projects[0][0]
                    elif len(matching_projects) > 1 and homeowner_id in homeowner_known_project_counts:
                        known_for_owner = homeowner_known_project_counts[homeowner_id]
                        # Pick the project with highest frequency for this homeowner.
                        ranked = sorted(known_for_owner.items(), key=lambda item: item[1], reverse=True)
                        for pid, _count in ranked:
                            if any(mp[0] == pid for mp in matching_projects):
                                project_id = pid
                                break

            if not project_id:
                if not project_name:
                    skipped_no_project += 1
                else:
                    skipped_no_project_id += 1
                continue

            if unit_plain in candidates and candidates[unit_plain] != project_id:
                conflicts.append((unit_plain, candidates[unit_plain], project_id, defect_id))
                continue

            candidates[unit_plain] = project_id

        print(f"Scanned defects: {len(defects)}")
        print(f"Existing mapped units skipped: {skipped_existing}")
        print(f"Skipped (empty unit): {skipped_no_unit}")
        print(f"Skipped (no homeowner project): {skipped_no_project}")
        print(f"Skipped (project not found in developer_projects): {skipped_no_project_id}")
        print(f"Conflicts: {len(conflicts)}")
        if conflicts:
            print("Conflict samples (unit, project_a, project_b, defect_id):")
            for item in conflicts[:10]:
                print("  ", item)

        print(f"Candidate new mappings: {len(candidates)}")
        preview = list(candidates.items())[:20]
        for unit, project_id in preview:
            print(f"  unit={unit} -> project_id={project_id}")

        if not apply_changes:
            print("Dry-run complete. Re-run with --apply to insert mappings.")
            return 0

        inserted = 0
        for unit, project_id in candidates.items():
            cur.execute(
                """
                INSERT INTO project_units (project_id, unit_number)
                SELECT %s, %s
                WHERE NOT EXISTS (
                    SELECT 1 FROM project_units WHERE unit_number = %s AND project_id = %s
                )
                """,
                (project_id, unit, unit, project_id),
            )
            inserted += cur.rowcount

        conn.commit()
        print(f"Inserted mappings: {inserted}")
        return 0

    except Exception as exc:
        conn.rollback()
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    finally:
        cur.close()
        conn.close()


if __name__ == '__main__':
    apply_mode = '--apply' in sys.argv
    raise SystemExit(main(apply_changes=apply_mode))
