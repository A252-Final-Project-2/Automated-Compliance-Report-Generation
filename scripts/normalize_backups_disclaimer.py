import json
import re
import shutil
from pathlib import Path

BACKUPS_DIR = Path(__file__).resolve().parents[0] / '..' / 'app' / 'module3' / 'audit_data' / 'backups'
BACKUPS_DIR = BACKUPS_DIR.resolve()

LANG_MAP = {
    'ms': 'PENAFIAN AI:',
    'en': 'AI DISCLAIMER:'
}

pattern_variants = re.compile(r"AI\s*DISCLAIMER[:\s]*", flags=re.IGNORECASE)
pattern_repeats = re.compile(r"(AI\s*DISCLAIMER)[:]{2,}", flags=re.IGNORECASE)

files = list(BACKUPS_DIR.glob('*.json'))
if not files:
    print('No backup JSON files found in', BACKUPS_DIR)
    raise SystemExit(1)

for f in files:
    print('Processing', f)
    orig = f.with_suffix(f.suffix + '.orig')
    if not orig.exists():
        shutil.copy2(f, orig)
        print('  .orig backup created')
    else:
        print('  .orig already exists')
    raw = f.read_text(encoding='utf-8')
    try:
        data = json.loads(raw)
    except Exception as e:
        print('  unable to parse JSON, skipping file:', e)
        continue
    changed = False
    # Walk versions
    versions = data.get('versions', {})
    for role, entries in versions.items():
        for entry in entries:
            text = entry.get('report_text')
            lang = entry.get('language') or 'en'
            if not text or not isinstance(text, str):
                continue
            localized = LANG_MAP.get(lang, LANG_MAP['en'])
            # normalize localized heading: single colon + newline
            localized = localized.rstrip(':').rstrip() + ':'
            localized = localized + '\n'
            new = text
            new = pattern_variants.sub(localized, new)
            new = pattern_repeats.sub(lambda m: (m.group(1) + ':\n'), new)
            # For English entries, ensure AI title + tribunal title + generated date + subtitle header present
            if lang == 'en':
                try:
                    ai_title = 'AI-GENERATED CLAIM SUMMARY REPORT'
                    # attempt to extract report_title from the text by known constant
                    report_title = 'TRIBUNAL SUPPORT REPORT – DEFECT LIABILITY PERIOD (DLP)'
                    generated_at_val = entry.get('generated_at') or entry.get('generated_at')
                    gen_line = f"Generated Date: {generated_at_val}" if generated_at_val else 'Generated Date:'
                    subtitle = 'Overview Report on Defect Liability Period (DLP) Compliance'
                    header = f"{ai_title}\n{report_title}\n{gen_line}\n\n{subtitle}\n\n"
                    if not new.lstrip().upper().startswith(ai_title):
                        new = header + new
                except Exception:
                    pass
            if new != text:
                entry['report_text'] = new
                changed = True
    if changed:
        f.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        print('  updated file')
    else:
        print('  no changes needed')

print('Done')
