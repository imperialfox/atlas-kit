"""“Check my notes”: the notes from an Atlas page and from the prototypes it lists, together, in one format.

In a Claude chat, Claude reads the Atlas page's store (its `notes` and `proposed` collections), then each listed
prototype's `notes`, and reports them with this, grouped by screen, oldest open first, each with its source.

    python3 -m atlas_kit.notes atlas_notes.json [prototype_notes.json ...] [--all]

Each file can be a list of notes, the lines a store listing gives (one JSON object per line, with `data`), or
{"notes": [...]}. Notes follow note format v1 (SHARED.md); fields a reader doesn't know are ignored.
"""
import datetime as dt
import json
import sys

STATUS = {'open': 'Open', 'looking': 'Looking into it', 'fixed': 'Fixed', 'dismissed': 'Dismissed'}


def read(path):
    txt = open(path, encoding='utf-8').read().strip()
    try:
        v = json.loads(txt)
        if isinstance(v, dict):
            rows = v.get('notes') or v.get('documents') or ([v] if ('data' in v or 'source' in v) else [])
        else:
            rows = v
    except json.JSONDecodeError:
        rows = [json.loads(l) for l in txt.splitlines() if l.strip().startswith('{')]
    out = []
    for r in rows:
        d = dict(r.get('data', r)) if isinstance(r, dict) else None
        if not d: continue
        if 'id' in r and 'id' not in d: d['id'] = r['id']
        out.append(d)
    return out


def when(iso):
    try: return dt.datetime.fromisoformat(iso.replace('Z', '+00:00')).strftime('%-d %b %H:%M')
    except Exception: return iso or ''


def label(n):
    pre = 'N' if n.get('source') == 'atlas' else 'P'
    return f"{pre}-{int(n.get('n') or 0):03d}"


def line(n):
    src = n.get('source', '?')
    f = n.get('from') or {}
    if src == 'prototype':
        src += ' (' + ', '.join(x for x in [str(f.get('prototype') or ''), 'version ' + str(f['version']) if f.get('version') else ''] if x) + ')'
    elif f.get('scan'):
        src += ' (scan ' + str(f['scan'].get('id', '')) + ((', ' + str(f['scan']['version'])) if f['scan'].get('version') else '') + ')'
    bits = [label(n), src, STATUS.get(n.get('status'), n.get('status') or 'Open'), when(n.get('created'))]
    if n.get('part'): bits.append('part ' + n['part'])
    elif n.get('name'): bits.append(n['name'])
    px = n.get('px')
    if px: bits.append(f"{px.get('x')}, {px.get('y')} · {px.get('w')}×{px.get('h')} pt")
    ed = n.get('edits') or {}
    if ed:
        e = []
        if ed.get('move'): e.append(f"move {ed['move'].get('dx', 0):+g}, {ed['move'].get('dy', 0):+g}")
        for k in ('width', 'height', 'corners'):
            if ed.get(k): e.append(f'{k} {ed[k][0]} → {ed[k][1]}')
        if ed.get('copyOf'): e.append('copy of ' + str(ed['copyOf']))
        if e: bits.append('edits: ' + ', '.join(e))
    return '- ' + ' · '.join(str(b) for b in bits if b) + ('\n  “' + n['text'] + '”' if n.get('text') else '')


def report(notes, everything=False, today=None):
    keep = [n for n in notes if everything or n.get('status', 'open') in ('open', 'looking')]
    groups = {}
    for n in keep:
        groups.setdefault(n.get('screen') or '(no screen)', []).append(n)
    for g in groups.values(): g.sort(key=lambda n: n.get('created') or '')
    order = sorted(groups, key=lambda k: groups[k][0].get('created') or '')
    apps = sorted({n.get('app') for n in keep if n.get('app')})
    srcs = sorted({n.get('source') for n in keep if n.get('source')})
    d = today or dt.date.today().strftime('%-d %b %Y')
    out = [f'Notes · note format v1 · {d}', 'Sources: ' + (' and '.join(srcs) or 'none') + (' · App: ' + ', '.join(apps) if apps else ''), '']
    if not keep: out.append('No open notes.')
    for k in order:
        g = groups[k]
        title = next((n.get('screenTitle') for n in g if n.get('screenTitle')), '')
        sid = next((n.get('sid') for n in g if n.get('sid')), None)
        out.append('## ' + ' · '.join(x for x in [sid if sid and sid != k else None, k, title] if x))
        out += [line(n) for n in g]
        out.append('')
    return '\n'.join(out).rstrip() + '\n'


def main(argv):
    everything = '--all' in argv
    files = [a for a in argv if not a.startswith('--')]
    if not files: sys.exit(__doc__)
    notes = [n for f in files for n in read(f)]
    sys.stdout.write(report(notes, everything))


if __name__ == '__main__':
    main(sys.argv[1:])
