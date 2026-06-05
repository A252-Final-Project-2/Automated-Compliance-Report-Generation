#!/usr/bin/env python3
"""
One-shot script to repair defect translation cache files.

Usage:
  python fix_defect_caches.py [--dry-run] [--backup-dir BACKUP]

This script will:
 - Iterate all files in `cache/defects/*.cache`
 - Parse JSON content (expected list)
 - Normalize item keys so that `id`, `unit`, `desc`, `priority`, `remarks` are present
 - Create a backup of the original cache file (timestamped) before overwriting
 - Overwrite the cache file with the normalized JSON (pretty-printed)

This makes the cached AI outputs robust against translated/renamed JSON keys.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


CACHE_DIR = Path(__file__).resolve().parents[1] / "cache" / "defects"


def _norm(k: str) -> str:
    return re.sub(r"[^a-z]", "", (k or "").lower())


def _find_value(obj: Dict[str, Any], keywords: Iterable[str]) -> Optional[Any]:
    for k, v in obj.items():
        nk = _norm(k)
        for kw in keywords:
            if kw in nk:
                return v
    return None


DESC_KEYS = ["desc", "description", "keterangan", "keterangan"]
REMARKS_KEYS = ["remarks", "ulasan", "catatan", "komen", "remark", "comment"]
PRIORITY_KEYS = ["priority", "keutamaan"]
ID_KEYS = ["id"]
UNIT_KEYS = ["unit"]


def normalize_item(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(item, dict):
        return None

    # find id
    item_id = None
    for k, v in item.items():
        if _norm(k) in ID_KEYS:
            item_id = v
            break
    if item_id is None:
        # try keys containing 'id'
        for k, v in item.items():
            if "id" in _norm(k):
                item_id = v
                break

    # find unit
    unit = _find_value(item, UNIT_KEYS) or item.get("unit")

    # find desc/description
    desc = _find_value(item, DESC_KEYS) or item.get("desc") or item.get("description")

    # find priority
    priority = _find_value(item, PRIORITY_KEYS) or item.get("priority")

    # find remarks
    remarks = _find_value(item, REMARKS_KEYS) or item.get("remarks") or item.get("remark")

    # If id is missing, we cannot map reliably; skip
    if item_id is None:
        return None

    normalized: Dict[str, Any] = {"id": item_id}
    if unit is not None:
        normalized["unit"] = unit
    if desc is not None:
        normalized["desc"] = desc
    if priority is not None:
        normalized["priority"] = priority
    if remarks is not None:
        normalized["remarks"] = remarks

    return normalized


def repair_cache_file(path: Path, backup_dir: Optional[Path] = None, dry_run: bool = False) -> Dict[str, Any]:
    result = {"file": str(path), "skipped": False, "changed": False, "items_read": 0, "items_written": 0, "error": None}
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except Exception as e:
        result["skipped"] = True
        result["error"] = f"invalid json: {e}"
        return result

    if not isinstance(data, list):
        result["skipped"] = True
        result["error"] = "not a list"
        return result

    normalized_list: List[Dict[str, Any]] = []
    for item in data:
        result["items_read"] += 1
        norm = normalize_item(item)
        if norm is None:
            # fallback: keep original item if it already looks correct
            if isinstance(item, dict) and "id" in item and ("desc" in item or "description" in item):
                normalized_list.append(item)
                result["items_written"] += 1
            else:
                # skip malformed entry
                continue
        else:
            normalized_list.append(norm)
            result["items_written"] += 1

    # Determine if rewrite is needed
    try:
        old_serial = json.dumps(data, ensure_ascii=False, sort_keys=True)
        new_serial = json.dumps(normalized_list, ensure_ascii=False, sort_keys=True)
    except Exception:
        old_serial = None
        new_serial = None

    if old_serial == new_serial:
        result["skipped"] = True
        return result

    result["changed"] = True

    if dry_run:
        return result

    # backup original
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    bak_name = path.with_suffix(path.suffix + f".orig.{timestamp}")
    if backup_dir:
        backup_dir.mkdir(parents=True, exist_ok=True)
        bak_name = backup_dir / (path.name + f".orig.{timestamp}")
    shutil.copy2(path, bak_name)

    # write normalized back
    path.write_text(json.dumps(normalized_list, ensure_ascii=False, indent=2), encoding="utf-8")

    return result


def main():
    parser = argparse.ArgumentParser(description="Repair defect translation cache files")
    parser.add_argument("--dry-run", action="store_true", help="Do not write files; just report")
    parser.add_argument("--backup-dir", type=str, default=None, help="Optional directory to store backups")
    args = parser.parse_args()

    backup_dir = Path(args.backup_dir) if args.backup_dir else None

    if not CACHE_DIR.exists():
        print(f"Cache directory not found: {CACHE_DIR}")
        return

    cache_files = sorted(CACHE_DIR.glob("*.cache"))
    if not cache_files:
        print(f"No cache files found in {CACHE_DIR}")
        return

    summary = {"total": 0, "repaired": 0, "skipped": 0, "errors": 0}
    for p in cache_files:
        summary["total"] += 1
        print(f"Processing {p.name}...")
        res = repair_cache_file(p, backup_dir=backup_dir, dry_run=args.dry_run)
        if res.get("error"):
            summary["errors"] += 1
            print(f"  skipped: {res['error']}")
            continue
        if res.get("changed"):
            summary["repaired"] += 1
            print(f"  repaired: read {res['items_read']} -> wrote {res['items_written']}")
        else:
            summary["skipped"] += 1
            print(f"  no changes needed")

    print("\nSummary:")
    print(f"  files processed: {summary['total']}")
    print(f"  repaired: {summary['repaired']}")
    print(f"  skipped (unchanged or invalid): {summary['skipped']}")
    print(f"  errors: {summary['errors']}")


if __name__ == '__main__':
    main()
