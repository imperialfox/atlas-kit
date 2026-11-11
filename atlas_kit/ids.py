"""Stable screen IDs, and finding screens by any of their names.

When an app keeps a register of its screens (an ID like `AB-012` for each, with its name, its place in the code and
any older code keys as aliases) and marks each screen and sheet with its ID on the page (`data-screen`), the scan reads
the ID from the screen itself. IDs then become the keys for screens, notes, flows, captions, tags since a version and
the saved map layout, so all of those survive renames and redesigns. Apps without IDs keep code-based keys.

- A captured screen with no ID is flagged "No ID yet", with a suggested next number (a suggestion only: the app's own
  register changes in an app build, never from the Atlas).
- A register entry the scan can't find is shown as "Not found this scan", never deleted.
"""
import json
import os
import re


def slug(s):
    return re.sub(r'[^a-z0-9]+', '-', str(s).lower()).strip('-')


def read_register(st, pg, ctx):
    """The app's register as a list of entries, from the running page, a file, or the settings' register(ctx)."""
    cfg = st.ids or {}
    raw = None
    try:
        if st.has('register'):
            raw = st.mod.register(ctx)
        elif cfg.get('register') and pg is not None:
            raw = pg.evaluate('()=>{try{return JSON.parse(JSON.stringify(' + cfg['register'] + '))}catch(e){return null}}')
        elif cfg.get('register_file'):
            p = os.path.join(ctx['app'], cfg['register_file'])
            if os.path.exists(p): raw = json.load(open(p, encoding='utf-8'))
    except Exception:
        raw = None
    return normalize(raw)


def normalize(raw):
    if isinstance(raw, dict):
        raw = raw.get('screens') or [dict(v, id=k) for k, v in raw.items() if isinstance(v, dict)]
    out = []
    for r in raw or []:
        if not isinstance(r, dict) or not r.get('id'): continue
        al = r.get('aliases') or []
        # parts are names, or {name, sel, was} (where the part is inside the screen, and its older names)
        names, sels, was = [], {}, {}
        for p in r.get('parts') or []:
            if isinstance(p, dict):
                if not p.get('name') or str(p.get('status', '')).lower().startswith('retired'): continue
                names.append(str(p['name']))
                if p.get('sel'): sels[str(p['name'])] = str(p['sel'])
                for o in (p.get('was') or []) if isinstance(p.get('was'), list) else [p.get('was')] if p.get('was') else []:
                    was[str(o)] = str(p['name'])
            elif p: names.append(str(p))
        e = {'id': str(r['id']), 'name': r.get('name') or r.get('title') or str(r['id']), 'area': r.get('area'),
             'kind': r.get('kind'), 'key': r.get('key'), 'aliases': [str(a) for a in (al if isinstance(al, list) else [al])],
             'docs': r.get('docs'), 'status': r.get('status') or 'Live', 'parts': names}
        if sels: e['partSel'] = sels
        if was: e['partWas'] = was
        out.append(e)
    return out


def part_map(register):
    """What a part-name tap needs from the register: each screen's part selectors and older part names."""
    return {r['id']: {'sel': r.get('partSel') or {}, 'was': r.get('partWas') or {}}
            for r in register or [] if r.get('partSel') or r.get('partWas')}


def live(r):
    return not str(r.get('status', 'Live')).lower().startswith('retired')


def apply(st, screens, register, out):
    cfg = st.ids or {}
    prefix, digits = cfg.get('prefix', ''), int(cfg.get('digits', 3))
    reg = register or []
    by_id = {r['id']: r for r in reg}
    by_key = {}
    for r in reg:
        for k in [r['key']] + r['aliases']:
            if k: by_key.setdefault(str(k), r['id'])

    def from_key(s):
        if s['status'] != 'captured':   # what it was meant to open, not where it landed
            keys = [s.get('key')] + (list(st.keys_of(s['key'])) if s.get('key') else [])
        else:
            keys = [s.get('family'), s.get('key'), s.get('sig')]
            if s.get('sig') is not None: keys += list(st.keys_of(s['sig']))
        for k in keys:
            if k is not None and str(k) in by_key: return by_key[str(k)]
        return None

    for s in screens:
        ids = s.get('ids') or {}
        v = (ids.get('sheet') if ids.get('sheetOpen') else ids.get('screen')) if ids and s['status'] == 'captured' else None
        if v: s['sid'], s['idFrom'] = v, 'screen'
        elif s.get('screen') and s['status'] != 'captured':   # a state that failed: still listed under the ID it names
            s['sid'], s['idFrom'] = str(s['screen']), 'state'
        else:
            k = from_key(s)
            if k: s['sid'], s['idFrom'] = k, 'register'
            else: s['sid'] = None
        if s['sid'] and s['sid'] in by_id:
            r = by_id[s['sid']]
            s['reg'] = {'name': r['name'], 'status': r['status'], 'docs': r['docs'], 'parts': r['parts']}
            s['aliasKeys'] = [r['key']] + r['aliases'] if r['key'] else r['aliases']
            if not s.get('stateOf'): s['title'] = r['name']
            elif s.get('state'): s['title'] = r['name'] + ' · ' + s['state']
        elif s['sid']:
            s['idProblem'] = 'On the screen as ' + s['sid'] + ', but not in the register'

    # suggested numbers for captured screens with no ID, after the highest number in the register
    nums = [int(m.group(1)) for r in reg for m in [re.match(re.escape(prefix) + r'(\d+)$', r['id'])] if m]
    nxt = max(nums, default=0) + 1
    no_id = []
    for s in screens:
        if s['status'] == 'captured' and not s['sid'] and not s.get('stateOf'):
            s['suggested'] = f'{prefix}{nxt:0{digits}d}'; nxt += 1
            no_id.append({'id': s['id'], 'title': s['title'], 'suggested': s['suggested']})
        elif s['status'] == 'captured' and not s['sid'] and s.get('stateOf'):
            s['noIdState'] = True

    # final ids: the screen's ID, with the state after it ("AB-001~first-launch")
    used, ren = set(), {}
    order = sorted(screens, key=lambda s: (bool(s.get('stateOf')), s['status'] != 'captured'))
    for s in order:
        new = s['id']
        if s['sid']:
            new = s['sid'] + ('~' + slug(s.get('state') or s['id']) if s.get('stateOf') else '')
            while new in used: new = new + '~' + slug(s['id'])
        used.add(new)
        if new != s['id']:
            ren[s['id']] = new
            s['slug'] = s['id']; s['id'] = new
    for s in screens:  # rename pictures and every reference
        if s['id'] in ren.values() and s.get('slug') and s.get('shot'):
            for a, b in ((s['slug'] + '.jpg', s['id'] + '.jpg'), (s['slug'] + '-full.jpg', s['id'] + '-full.jpg')):
                pa, pb = os.path.join(out, 'shots', a), os.path.join(out, 'shots', b)
                if os.path.exists(pa): os.replace(pa, pb)
            s['shot'] = 'shots/' + s['id'] + '.jpg'
            # the full length is its own picture only when the screen is taller than the view (1.2)
            s['full'] = 'shots/' + s['id'] + '-full.jpg' if os.path.exists(os.path.join(out, 'shots', s['id'] + '-full.jpg')) else s['shot']
        for l in s.get('links', []):
            if l.get('to') in ren: l['to'] = ren[l['to']]
        for f in s.get('from', []):
            if f.get('from') in ren: f['from'] = ren[f['from']]
        if s.get('via') and s['via'].get('from') in ren: s['via'] = dict(s['via'], **{'from': ren[s['via']['from']]})
        for k in ('stateOf', 'linksOf'):
            if s.get(k) in ren: s[k] = ren[s[k]]

    # register entries no screen showed: kept, as "Not found this scan"
    seen = {s['sid'] for s in screens if s.get('sid')}
    not_found = []
    for r in reg:
        if r['id'] in seen or not live(r): continue
        not_found.append(r['id'])
        screens.append({'id': r['id'], 'sid': r['id'], 'idFrom': 'register', 'title': r['name'], 'kind': r['kind'] or 'Screen',
                        'key': r['key'], 'family': r['key'], 'area': 'Not found this scan', 'status': 'notfound',
                        'why': 'In the register' + (' (code key ' + r['key'] + ')' if r['key'] else '') + ', but this scan didn’t find it on any screen. Kept, never deleted.',
                        'reg': {'name': r['name'], 'status': r['status'], 'docs': r['docs'], 'parts': r['parts']},
                        'aliasKeys': [r['key']] + r['aliases'] if r['key'] else r['aliases'],
                        'links': [], 'from': [], 'docs': [], 'errors': []})
    return {'prefix': prefix, 'digits': digits, 'register': len(reg), 'noId': no_id, 'notFound': not_found,
            'retired': [r['id'] for r in reg if not live(r)]}


class Resolver:
    """Finds a screen by any of its names: its id, its screen ID, its first id, its family or its code key."""

    def __init__(self, st, screens):
        self.st, self.screens = st, screens
        self.names = {}
        for pri in (0, 1):  # plain screens first, then states
            for s in screens:
                if bool(s.get('stateOf')) != bool(pri): continue
                for n in (s['id'], s.get('sid'), s.get('slug'), s.get('family'), s.get('key'), s.get('sig'), *(s.get('aliasKeys') or [])):
                    if n is not None: self.names.setdefault(str(n), s['id'])

    def find(self, ref):
        return self.names.get(str(ref)) if ref is not None else None

    def from_capture(self, sig, ids):
        if ids:
            v = ids.get('sheet') if ids.get('sheetOpen') else ids.get('screen')
            if v and v in self.names: return self.names[v]
        if sig is None: return None
        return self.names.get(str(sig)) or self.names.get(str(self.st.family(sig)))

    def lookup_table(self, table, s):
        for n in (s['id'], s.get('sid'), s.get('slug'), s.get('family'), s.get('key')):
            if n is not None and str(n) in table: return table[str(n)]
        return None


def site_files(folder):
    """A site's pages, from its folder: every .html file, keyed by its address from the site's root."""
    out = {}
    for d, _, files in os.walk(folder):
        if '/.' in d or os.path.basename(d).startswith('.'): continue
        for f in files:
            if not f.endswith('.html'): continue
            p = os.path.relpath(os.path.join(d, f), folder).replace(os.sep, '/')
            k = '/' + (p[:-len('index.html')] if p.endswith('index.html') else p)
            t = ''
            try:
                m = re.search(r'<title>(.*?)</title>', open(os.path.join(d, f), encoding='utf-8').read(), re.S | re.I)
                t = m.group(1).strip() if m else ''
            except Exception: pass
            out[k] = {'kind': 'Page', 'name': re.split(r'\s+[·|—–-]\s+', t)[0].strip() if t else p, 'where': p}
    return out
