#!/usr/bin/env python3
import os, sys
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)
from app.module3.routes import get_defects_for_role

def main():
    defects = get_defects_for_role('Developer')
    counts = {}
    for d in defects:
        pn = d.get('project_name') or '<EMPTY>'
        counts[pn] = counts.get(pn, 0) + 1
    print('Defects by project_name (from get_defects_for_role):')
    for k,v in sorted(counts.items(), key=lambda x: x[1], reverse=True):
        print(f'{k}: {v}')
    print('\nSample:')
    for d in defects[:20]:
        print(d['id'], d['unit'], d['project_name'])

if __name__ == '__main__':
    main()
