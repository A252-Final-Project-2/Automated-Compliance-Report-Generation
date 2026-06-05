#!/usr/bin/env python3
"""
Clear translation caches to force fresh translations.

Usage:
  python clear_translation_cache.py [--all] [--defects] [--remarks] [--reports] [--fields]

Examples:
  python clear_translation_cache.py --all      # Clear everything
  python clear_translation_cache.py --defects  # Clear defect cache only
  python clear_translation_cache.py --remarks  # Clear remark cache only
"""

import os
import shutil
import sys
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parent / "app" / "module3" / "cache"

CACHE_TYPES = {
    "defects": CACHE_DIR / "defects",
    "remarks": CACHE_DIR / "remarks",
    "reports": CACHE_DIR / "reports",
    "fields": CACHE_DIR / "fields",
}


def clear_cache(cache_type):
    """Clear a specific cache type."""
    cache_path = CACHE_TYPES.get(cache_type)
    if not cache_path or not cache_path.exists():
        print(f"⚠ Cache directory not found: {cache_path}")
        return False

    try:
        # Get count before deletion
        file_count = len(list(cache_path.glob("*")))
        
        # Clear directory
        for file in cache_path.glob("*"):
            if file.is_file():
                file.unlink()
            elif file.is_dir():
                shutil.rmtree(file)
        
        print(f"✓ Cleared {cache_type}: {file_count} files deleted")
        return True
    except Exception as e:
        print(f"✗ Error clearing {cache_type}: {e}")
        return False


def main():
    if not CACHE_DIR.exists():
        print(f"✗ Cache directory not found: {CACHE_DIR}")
        print("Please ensure you're running this from the project root.")
        sys.exit(1)

    args = sys.argv[1:]
    
    if not args or "--help" in args:
        print(__doc__)
        sys.exit(0)

    if "--all" in args:
        print("Clearing all translation caches...")
        for cache_type in CACHE_TYPES:
            clear_cache(cache_type)
        print("\n✓ All caches cleared. Fresh translations will be generated on next use.")
        return

    # Clear specified cache types
    cleared_any = False
    if "--defects" in args:
        clear_cache("defects")
        cleared_any = True
    if "--remarks" in args:
        clear_cache("remarks")
        cleared_any = True
    if "--reports" in args:
        clear_cache("reports")
        cleared_any = True
    if "--fields" in args:
        clear_cache("fields")
        cleared_any = True

    if cleared_any:
        print("\n✓ Selected caches cleared. Fresh translations will be generated on next use.")
    else:
        print("No cache types specified. Use --all or specify: --defects --remarks --reports --fields")


if __name__ == "__main__":
    main()
