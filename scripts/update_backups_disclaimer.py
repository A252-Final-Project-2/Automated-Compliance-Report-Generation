import os
from pathlib import Path

BACKUP_DIR = Path(__file__).resolve().parents[1] / 'app' / 'module3' / 'audit_data' / 'backups'

if not BACKUP_DIR.exists():
    print('Backup directory not found:', BACKUP_DIR)
    raise SystemExit(1)

updated = []
for p in sorted(BACKUP_DIR.iterdir()):
    if p.is_file() and p.suffix == '.json':
        text = p.read_text(encoding='utf-8')
        if 'AI DISCLAIMER:' in text:
            # create a .orig backup
            orig = p.with_suffix(p.suffix + '.orig')
            if not orig.exists():
                orig.write_text(text, encoding='utf-8')
            new_text = text.replace('AI DISCLAIMER:', 'PENAFIAN AI:')
            p.write_text(new_text, encoding='utf-8')
            updated.append(str(p))

print('Updated files:')
for u in updated:
    print('-', u)
print('Done. Replaced occurrences of "AI DISCLAIMER:" with "PENAFIAN AI:" in backups.')
