"""The scan engine: any app or site, from its settings file.

Opens the app in throwaway headless browsers (sample data only, the clock frozen, motion off). Starting from the
settings' starting screens (or a site's start address), it captures each screen (top of screen and full length), maps
what's on it, taps every button on a reset copy and records where each one lands. Whatever a tap opens that isn't
captured yet is opened next through that same button (or, on a site, its address), captured and tapped in turn, until
nothing new turns up. Then it walks the settings' flows, captures any proposed screens, reads screen IDs, and compares
with earlier scans.

Rules (kept from the first Atlas): screens open through their real buttons; a full reset before every tap; a sheet
that didn't open is "Failed", never captured as the screen underneath; buttons the scan won't press get an honest
"Not tested" reason, never "Broken".

Writes <out>/atlas.json and <out>/shots/. Used by atlas.py.
"""
import concurrent.futures as cf
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import time

from . import VERSION
from . import browser as B
from . import compare as CMP
from . import docs as DOCS
from . import ids as IDS
from . import settings as SET


def slug(s):
    return re.sub(r'[^a-z0-9]+', '-', str(s).lower()).strip('-') or 'home'


# ---------- one worker: capture some screens and tap their buttons ----------
class Runner:
    """Everything one worker needs to open, read and reset the app."""

    def __init__(self, b, st, ctx):
        self.b, self.st, self.ctx = b, st, ctx
        self.opts = B.page_opts(st)
        self.errors, self.statuses = [], []
        self.register = None

    def fresh(self, setup):
        st = self.st
        pg = B.new_page(self.b, st, dark='dark' in setup, errors=self.errors, statuses=self.statuses)
        if st.kind == 'screens':
            st.mod.load(pg, list(setup), self.ctx)
        if st.snapshot_js: pg.evaluate(st.snapshot_js)
        if st.reset_js: pg.evaluate(st.reset_js)
        pg.wait_for_timeout(60)
        if st.ids and self.register is None:
            self.register = IDS.read_register(st, pg, self.ctx)
        return pg

    def where(self, pg):
        st = self.st
        if st.has('where'): raw = st.mod.where(pg)
        elif st.kind == 'pages':
            raw = B.rel(pg.url, self.ctx['url'])
            if raw is None: raw = pg.url
        elif st.where_js: raw = pg.evaluate(st.where_js)
        else: raw = pg.evaluate('location.pathname+location.hash')
        return st.call('key', raw, default=raw if isinstance(raw, str) else json.dumps(raw, sort_keys=True))

    def tap(self, pg, sel, force=False):
        loc = pg.locator(self.fill(sel)).first
        if force: loc.dispatch_event('click')
        else: loc.click(timeout=2500)
        if self.st.kind == 'pages':
            try: pg.wait_for_load_state('load', timeout=5000)
            except Exception: pass
        pg.wait_for_timeout(self.st.tap_wait)

    def fill(self, sel):
        """Selectors may name values the settings' prepare() worked out, like {song} for a sample song's id."""
        v = self.ctx.get('vars') or {}
        for k, x in v.items(): sel = sel.replace('{' + k + '}', str(x))
        return sel

    def open(self, pg, ent):
        for stp in ent['steps']:
            kind, arg = stp[0], stp[1]
            if kind == 'goto':
                self.statuses.clear()
                pg.goto(self.ctx['url'] + arg.lstrip('/'), wait_until='load')
                continue
            if kind == 'js':  # a shortcut, for set-up only
                pg.evaluate(arg); pg.wait_for_timeout(self.st.tap_wait); continue
            if kind == 'wait':
                pg.wait_for_timeout(arg); continue
            try:
                self.tap(pg, arg, force=(kind == 'force'))
            except Exception:
                raise RuntimeError('Didn’t open: couldn’t tap ' + self.fill(arg) + ' on the way there (not on screen)')
        pg.wait_for_timeout(80)
        return self.where(pg)

    def sheet_open(self, pg):
        return bool(self.st.sheet) and pg.evaluate(B.SHEET_OPEN_JS, self.st.sheet)

    def reset(self, pg, ent):
        """Back to how the screen was before the last tap."""
        if self.st.reset_js:
            pg.evaluate(self.st.reset_js)
            return pg, self.open(pg, ent)
        if self.st.kind == 'pages':
            return pg, self.open(pg, ent)
        pg.context.close()
        pg = self.fresh(ent['setup'])
        return pg, self.open(pg, ent)

    def title(self, pg):
        if self.st.title_js: return pg.evaluate(self.st.title_js)
        if self.st.kind == 'pages':
            t = pg.evaluate('document.title') or ''
            return re.split(r'\s+[·|—–-]\s+', t)[0].strip() or pg.evaluate(B.TITLE_JS, self.opts)
        return pg.evaluate(B.TITLE_JS, self.opts)

    def hidden(self, loc):
        js = getattr(self.st.mod, 'HIDDEN_JS', None) or "e=>!!e.closest('[aria-hidden=true],[inert]')"
        return loc.evaluate(js)


def capture_entry(R, ent, out, taps):
    st = R.st
    sid = ent['id']
    r = {'id': sid, 'status': 'captured', 'errors': [], 'links': []}
    R.errors.clear()
    pg = None
    try:
        pg = R.fresh(ent['setup'])
        landed = R.open(pg, ent)
        r['sig'] = landed
        if st.kind == 'pages' and R.statuses and R.statuses[-1] >= 400:
            raise RuntimeError(f'Didn’t open: the address answered {R.statuses[-1]} (not found)')
        want = ent.get('expect')
        if want and st.family(landed) != st.family(want):
            raise RuntimeError('Didn’t open: landed on ' + st.describe(landed) + ' instead')
        if not want and ent.get('key') and st.kind == 'screens' and not st.family(landed).startswith(st.family(ent['key'])):
            raise RuntimeError('Didn’t open: landed on ' + st.describe(landed) + ' instead')
        sheet = R.sheet_open(pg)
        if ent.get('kind') == 'Sheet' and not sheet:
            raise RuntimeError('Didn’t open: the sheet isn’t on screen')
        r['sheet'] = sheet
        r['title'] = R.title(pg)
        if st.ids: r['ids'] = pg.evaluate(B.IDS_JS, R.opts)
        pg.screenshot(path=os.path.join(out, 'shots', sid + '.jpg'), type='jpeg', quality=82)
        pg.screenshot(path=os.path.join(out, 'shots', sid + '-full.jpg'), type='jpeg', quality=78, full_page=True)
        r['fullHeight'] = pg.evaluate('Math.max(document.documentElement.scrollHeight, document.body ? document.body.scrollHeight : 0)')
        r['elements'] = pg.evaluate(B.ELEMENTS_JS, R.opts)
        r['errors'] = list(dict.fromkeys(R.errors))
        if not taps or not ent.get('taps', True):
            pg.context.close(); return r
        btns = pg.evaluate(B.BUTTONS_JS, R.opts)
        look = [x['sel'] for x in btns]       # how the screen should look each time it's put back
        for bt in btns[:st.max_buttons]:
            act = bt['a'] or bt['part'] or ('link' if bt['href'] else 'button')
            link = {'action': act, 'value': bt['v'], 'label': bt['label'] or act, 'selector': bt['sel']}
            if bt['part']: link['part'] = bt['part']
            if bt['bar']: link['bar'] = True
            why = st.skip_reason(bt['a'] or bt['part'], bt['v'], bt['label'])
            if not why and bt['href']:
                if re.match(r'^(mailto|tel|sms):', bt['href']): why = 'Not tested: opens email, phone or messages'
                elif B.rel(bt['href'], R.ctx['url']) is None and not bt['href'].startswith('javascript:'):
                    why = 'Not tested: goes outside the app (' + re.sub(r'^https?://', '', bt['href']).split('/')[0] + ')'
                    link['outside'] = bt['href']
                elif bt['target'] == '_blank': why = 'Not tested: opens in a new tab'
            if why:
                link.update(how='not-tested', why=why); r['links'].append(link); continue
            try:
                pg, before = R.reset(pg, ent)
                if before != landed or [x['sel'] for x in pg.evaluate(B.BUTTONS_JS, R.opts)] != look:
                    # something from the last tap is still showing: start this screen again on a fresh copy
                    pg.context.close(); pg = R.fresh(ent['setup']); before = R.open(pg, ent)
                if before != landed:
                    link.update(how='not-tested', why='Not tested: couldn’t put the screen back as it was to try it'); r['links'].append(link); continue
                loc = pg.locator(R.fill(bt['sel'])).first
                if not loc.count() or not loc.is_visible() or R.hidden(loc):
                    link.update(how='not-tested', why='Not tested: only shows after a swipe, a hold or a menu'); r['links'].append(link); continue
                n = len(R.errors); R.statuses.clear()
                try:
                    R.tap(pg, bt['sel'])
                except Exception as e:
                    msg = str(e)
                    if 'intercept' in msg or 'not stable' in msg or 'outside of the viewport' in msg or 'Timeout' in msg:
                        R.tap(pg, bt['sel'], force=True)   # another layer covers it: tap the button itself
                        link['forced'] = True
                    else: raise
                after = R.where(pg)
                if len(R.errors) > n: link.update(how='broken', why=R.errors[-1][:200])
                elif R.statuses and R.statuses[-1] >= 400: link.update(how='broken', why=f'The address answered {R.statuses[-1]} (not found)', toLabel=after)
                elif after == before and not (R.sheet_open(pg) and not r['sheet']): link.update(how='stays')
                else:
                    link.update(how='seen', toSig=after)
                    if R.sheet_open(pg) and not r['sheet']: link['opensSheet'] = True
            except Exception as e:
                first = str(e).strip().splitlines()[0][:160] if str(e).strip() else type(e).__name__
                link.update(how='not-tested', why='Not tested: couldn’t tap it (' + first + ')')
            r['links'].append(link)
        pg.context.close()
    except Exception as e:
        r['status'] = 'failed'; r['why'] = (str(e).strip().splitlines() or [type(e).__name__])[0][:220]
        r['errors'] = list(dict.fromkeys(R.errors))
        for f in (sid + '.jpg', sid + '-full.jpg'):  # a failed capture never keeps a picture
            try: os.remove(os.path.join(out, 'shots', f))
            except OSError: pass
        try:
            if pg: pg.context.close()
        except Exception: pass
    return r


def job(args):
    spath, entries, app_dir, out, ctx, taps = args
    st = SET.load(spath)
    from playwright.sync_api import sync_playwright
    res = {}
    with sync_playwright() as p:
        b = p.chromium.launch()
        R = Runner(b, st, ctx)
        for ent in entries:
            res[ent['id']] = capture_entry(R, ent, out, taps)
        if R.register is not None: res['__register'] = R.register
        b.close()
    return res


def run_parallel(fn, items, workers, common):
    if not items: return {}
    n = max(1, min(workers, len(items)))
    parts = [items[i::n] for i in range(n)]
    out = {}
    if n == 1:
        out.update(fn((common[0], parts[0]) + common[1:]))
    else:
        with cf.ProcessPoolExecutor(n) as ex:
            for r in ex.map(fn, [(common[0], p) + common[1:] for p in parts]): out.update(r)
    return out


# ---------- flows: walk-throughs named in the settings ----------
def flow_job(args):
    spath, flows, app_dir, out, ctx, _ = args
    st = SET.load(spath)
    from playwright.sync_api import sync_playwright
    res = {}
    with sync_playwright() as p:
        b = p.chromium.launch()
        R = Runner(b, st, ctx)
        for f in flows:
            res[f['id']] = walk(R, f, out)
        b.close()
    return res


def walk(R, f, out):
    """Each step: do its actions (tap, fill, a set-up shortcut, wait), then capture what's showing."""
    st = R.st
    fid = slug(f['id'])
    res = {'id': f['id'], 'title': f.get('title') or f['id'], 'caption': f.get('caption'), 'status': 'captured', 'steps': []}
    R.errors.clear()
    pg = None
    try:
        start = f.get('start', [])
        root = next((r for r in st.roots if r['id'] == start), None) if isinstance(start, str) else None
        setup = list(f.get('setup', root['setup'] if root else []))
        steps = root['steps'] if root else [tuple(x) for x in start]
        pg = R.fresh(setup)
        R.open(pg, {'steps': steps, 'setup': setup})

        def shoot(i, info):
            name = f'flows/{fid}-{i}.jpg'
            pg.screenshot(path=os.path.join(out, 'shots', name), type='jpeg', quality=82)
            info.update(shot='shots/' + name, sig=R.where(pg), sheet=R.sheet_open(pg), title=R.title(pg))
            if st.ids: info['ids'] = pg.evaluate(B.IDS_JS, R.opts)
            return info

        if f.get('capture_start', True):
            res['steps'].append(shoot(0, {'n': 0, 'moment': f.get('start_moment', ''), 'label': None, 'caption': f.get('start_caption')}))
        for i, s in enumerate(f.get('steps', []), 1):
            info = {'n': i, 'moment': s.get('moment', ''), 'caption': s.get('caption'), 'label': s.get('label')}
            try:
                for sel, text in (s.get('fill') or {}).items():
                    pg.locator(sel).first.fill(text)
                if s.get('js'): pg.evaluate(s['js'])
                if s.get('tap'):
                    loc = pg.locator(s['tap']).first
                    box = loc.evaluate(B.BOX_JS)
                    info['tapped'] = {k: box[k] for k in ('x', 'y', 'w', 'h')}
                    if not info['label']: info['label'] = box['label'] or s['tap']
                    if res['steps']: res['steps'][-1]['next'] = info['tapped']
                    R.tap(pg, s['tap'], force=s.get('force', False))
                if s.get('wait'): pg.wait_for_timeout(s['wait'])
            except Exception as e:
                res['status'] = 'failed'
                res['why'] = f'Step {i} didn’t work: ' + ((str(e).strip().splitlines() or [type(e).__name__])[0][:160])
                break
            if s.get('capture', True): res['steps'].append(shoot(i, info))
        res['errors'] = list(dict.fromkeys(R.errors))
        pg.context.close()
    except Exception as e:
        res['status'] = 'failed'; res['why'] = (str(e).strip().splitlines() or [type(e).__name__])[0][:220]
        try:
            if pg: pg.context.close()
        except Exception: pass
    return res


# ---------- proposed screens: prototypes listed against the real screen they change ----------
KIT_UI_HIDDEN = ('.kit-launcher,.kit-panel,.kit-dock,.kit-pin,.kit-ruler,.kit-ov,.kit-tip,.kit-hint,.kit-msg,.kit-real,'
                 '.kit-real-side,.kit-insp,.kit-ins,.kit-gl,.kit-store{visibility:hidden!important}')

def proposed_job(args):
    spath, items, app_dir, out, ctx, _ = args
    st = SET.load(spath)
    from playwright.sync_api import sync_playwright
    opts = B.page_opts(st)
    res = {}
    with sync_playwright() as p:
        b = p.chromium.launch()
        for it in items:
            r = dict(it, status='captured')
            try:
                pg = B.new_page(b, st)
                src = it.get('file')
                url = ('file://' + os.path.abspath(src)) if src else it['url']
                pg.goto(url, wait_until='load')
                pg.wait_for_timeout(300)
                # a Prototype kit page: Inspect off and the kit's own controls hidden, so it shows as it would be used
                pg.evaluate("()=>{try{if(window.Kit&&Kit.inspect)Kit.inspect(false)}catch(e){}}")
                pg.add_style_tag(content=KIT_UI_HIDDEN)
                pg.wait_for_timeout(150)
                scr = pg.locator('.kit-screen').first
                path = os.path.join(out, 'shots', 'proposed', it['pid'] + '.jpg')
                if scr.count() and scr.is_visible():
                    scr.screenshot(path=path, type='jpeg', quality=82)
                    box = scr.bounding_box()
                    r['elements'] = [e for e in pg.evaluate(B.ELEMENTS_JS, dict(opts, root='.kit-screen', sheet=None))]
                    for e in r['elements']: e['x'] -= round(box['x']); e['y'] -= round(box['y'])
                else:
                    pg.screenshot(path=path, type='jpeg', quality=82)
                    r['elements'] = pg.evaluate(B.ELEMENTS_JS, dict(opts, sheet=None))
                r['shot'] = 'shots/proposed/' + it['pid'] + '.jpg'
                r['version'] = it.get('version') or pg.evaluate("()=>{try{return (window.Kit&&Kit.state&&Kit.state().version)||''}catch(e){return ''}}")
                pg.context.close()
            except Exception as e:
                r['status'] = 'failed'; r['why'] = (str(e).strip().splitlines() or [type(e).__name__])[0][:200]
            res[it['pid']] = r
        b.close()
    return res


# ---------- the whole scan ----------
def scan(spath, app_dir, out, workers=2, taps=True, only=None, prev=None, baselines=(), proposed=None,
         say=print, scan_id=None):
    t0 = time.time()
    st = SET.load(spath)
    app_dir = os.path.abspath(app_dir); out = os.path.abspath(out)
    for d in ('shots', 'shots/flows', 'shots/proposed'):
        os.makedirs(os.path.join(out, d), exist_ok=True)

    site = st.site if st.kind == 'pages' else None
    server = None
    if site and re.match(r'^https?://', site):
        base = site if site.endswith('/') else site + '/'
    else:
        server = B.Server(os.path.join(app_dir, site) if site else app_dir)
        base = server.url
    try:
        ctx = {'app': app_dir, 'url': base}
        extra = st.call('prepare', ctx, default=None)
        if extra: ctx.update(extra)
        inv = st.inventory(app_dir)
        if st.kind == 'pages' and not inv and not (site and re.match(r'^https?://', site)):
            inv = IDS.site_files(os.path.join(app_dir, site) if site else app_dir)
        if inv: say(f'Code: {len(inv)} screens and sheets the app can show')
        common = (spath, app_dir, out, ctx, taps)

        # starting screens
        entries = []
        if st.kind == 'pages':
            start = st.start
            entries.append(dict(id=B.page_slug(start), title=None, area=None, kind='Page', key=None,
                                steps=[('goto', start)], setup=[], how='Root'))
        for r in st.roots if st.kind == 'screens' else []:
            if only and r['id'] not in only: continue
            e = dict(r, docs=r.get('docs', []), how='Root', steps=[tuple(x) for x in r.get('steps', [])], setup=list(r.get('setup', [])))
            if e.get('state_of') and 'taps' not in e: e['taps'] = False  # a state shares its screen's links
            entries.append(e)
        gone_roots = [e for e in entries if inv and e.get('key') and not any(k in inv for k in st.keys_of(e['key']))]
        queue = [e for e in entries if e not in gone_roots]
        results, fams, passes, register = {}, {}, 0, None
        limit = st.max_pages if st.kind == 'pages' else st.max_passes
        while queue and passes < limit:
            passes += 1
            say(f'Pass {passes}: {len(queue)} screen' + ('s' if len(queue) != 1 else ''))
            got = run_parallel(job, queue, workers, common)
            if '__register' in got: register = register or got.pop('__register')
            got.pop('__register', None)
            results.update(got)
            for e in queue:
                r = results[e['id']]
                if r.get('sig') is not None and r['status'] == 'captured' and not e.get('state_of'):
                    fams.setdefault(st.family(r['sig']), e['id'])
                elif r.get('sig') is None and e.get('expect'):
                    fams.setdefault(st.family(e['expect']), e['id'])
            if only or not taps: break
            queue = []
            for e in list(entries):  # every link seen working that opens something not captured yet becomes its door
                r = results.get(e['id'])
                if not r or r['status'] != 'captured': continue
                for l in r['links']:
                    if l.get('how') != 'seen': continue
                    fam = st.family(l['toSig'])
                    if fam in fams: continue
                    if st.kind == 'pages' and len(entries) >= st.max_pages: continue
                    nid = B.page_slug(fam) if st.kind == 'pages' else slug(fam)
                    while any(x['id'] == nid for x in entries): nid += '-2'
                    if st.kind == 'pages':
                        steps = [('goto', l['toSig'])]
                        how = 'Opened by its address'
                    else:
                        steps = list(e['steps']) + [('force' if l.get('forced') else 'tap', l['selector'])]
                        how = None
                    ne = dict(id=nid, fam=fam, title=None, area=st.area_of(l['toSig'], e.get('area')), kind=None, key=None,
                              steps=steps, setup=list(e['setup']), expect=l['toSig'], docs=[], how='Found', opened=how,
                              via={'from': e['id'], 'label': l['label']})
                    fams[fam] = nid; entries.append(ne); queue.append(ne)

        flows = run_parallel(flow_job, st.flows, workers, common) if st.flows and not only else {}
        props = []
        for i, p in enumerate(proposed or []):
            q = dict(p, pid='P-' + str(i + 1))
            if q.get('file') and not os.path.isabs(q['file']): q['file'] = os.path.join(st.dir, q['file'])
            props.append(q)
        props = run_parallel(proposed_job, props, workers, common) if props else {}
        if st.ids and register is None:
            register = IDS.read_register(st, None, ctx)
    finally:
        if server: server.close()

    atlas = assemble(st, app_dir, out, entries, results, gone_roots, inv, flows, props, register, passes, ctx)
    atlas['scan']['id'] = scan_id or dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    atlas['scan']['seconds'] = round(time.time() - t0)
    CMP.compare_all(atlas, out, prev, baselines, say)
    json.dump(atlas, open(os.path.join(out, 'atlas.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    summary(atlas, say, time.time() - t0)
    return atlas


# ---------- putting it together ----------
def assemble(st, app_dir, out, entries, results, gone_roots, inv, flows, props, register, passes, ctx):
    log = DOCS.changelog(app_dir, st.changelog_file, st.docs_url, st.change_id)
    sections = DOCS.doc_sections(app_dir, st.doc_files, st.docs_url)
    problems = set()
    plain_by_sig, by_fam = {}, {}
    for e in entries:
        r = results.get(e['id'])
        if not r or r['status'] != 'captured' or r.get('sig') is None or e.get('state_of'): continue
        plain_by_sig.setdefault(r['sig'], e['id'])
        by_fam.setdefault(st.family(r['sig']), e['id'])
    for e in entries:  # a state's key points to its plain screen
        r = results.get(e['id'])
        if r and r.get('sig') is not None and e.get('state_of'): plain_by_sig.setdefault(r['sig'], e['state_of'])

    def resolve(sig):
        to = plain_by_sig.get(sig)
        fam = None
        if not to:
            to = by_fam.get(st.family(sig))
            if to and sig != results.get(to, {}).get('sig'): fam = st.describe(sig)
        return to, fam

    screens = []
    for e in entries:
        r = results.get(e['id']) or {'status': 'gone', 'errors': [], 'links': []}
        if e in gone_roots:
            r = {'status': 'gone', 'why': 'In the settings’ starting screens, but the code no longer has ' + str(e['key']), 'errors': [], 'links': []}
        sig = r.get('sig')
        fam = st.family(sig) if sig is not None else (e.get('fam') or e.get('key') or e['id'])
        for l in r['links']:
            a = l['action']
            if l.get('toSig') is not None:
                to, family = resolve(l['toSig'])
                l['to'] = to
                if family: l['family'] = family
                if not to: l['toLabel'] = st.describe(l['toSig'])
            kind = st.call('link_kind', l, default=None)
            l['kind'] = kind or ('Tab bar' if l.get('bar') else 'Back' if re.search(r'(?i)(^|[^a-z])back$|^close$|^done$', a) or re.search(r'(?i)^(back|close|done|cancel)$', l['label'])
                                 else 'Opens a sheet' if l.get('opensSheet') else 'Button')
        head = (r.get('title') or '').strip()
        title = (e.get('title') or st.titles.get(fam) or st.titles.get(e.get('key') or '')
                 or (st.title_prefix[fam] + (' · ' + head if head else '') if fam in st.title_prefix else None)
                 or head or st.describe(sig if sig is not None else (e.get('expect') or e.get('key') or e['id'])))
        area = e.get('area') or (st.area_of(sig, None) if sig is not None else None)
        if st.areas and area not in st.areas: area = 'Other'
        area = area or 'Screens'
        kind = e.get('kind') or st.kind_of(fam, bool(r.get('sheet')))
        shot = 'shots/' + e['id'] + '.jpg' if r['status'] == 'captured' else None
        if st.kind == 'pages':
            how = e.get('opened') or 'Opened by its address'
            how += ': ' + (e['steps'][0][1] if e['steps'] else '')
        else:
            how = ' → '.join(('tap ' if s[0] == 'tap' else 'forced tap ' if s[0] == 'force' else 'shortcut ') + str(s[1]) for s in e['steps']) or 'the app as it opens'
            if e['setup']: how = 'set up with ' + ', '.join(e['setup']) + '; ' + how
        screens.append({
            'id': e['id'], 'title': title, 'area': area, 'kind': kind, 'key': e.get('key') or fam, 'family': fam, 'setup': e['setup'],
            'state': e.get('state'), 'stateOf': e.get('state_of'), 'found': e['how'], 'via': e.get('via'), 'how': how,
            'status': r['status'], 'why': r.get('why'), 'errors': r.get('errors', []), 'sig': sig, 'ids': r.get('ids'),
            'shot': shot, 'full': 'shots/' + e['id'] + '-full.jpg' if shot else None, 'fullHeight': r.get('fullHeight'),
            'hash': hashlib.sha1(open(os.path.join(out, shot), 'rb').read()).hexdigest()[:12] if shot else None,
            'elements': r.get('elements', []), 'links': r['links'],
            'docs': docs_for(st, e, fam, area, sections, problems), 'mention': mention_for(st, fam, title, log)})
    by = {s['id']: s for s in screens}
    for s in screens:
        s['from'] = [{'from': o['id'], 'label': l['label'], 'how': l['how']} for o in screens for l in o['links']
                     if l.get('to') == s['id'] and o['id'] != s['id'] and not o.get('stateOf')]
        if s.get('stateOf') and not s['links'] and s['stateOf'] in by: s['linksOf'] = s['stateOf']

    # what the code (or the site's folder) can show that this scan didn't reach
    have = set()
    for s in screens:
        if s['status'] == 'captured' and s['sig'] is not None: have.update(st.keys_of(s['sig']))
    tried = {s['key'] for s in screens if s['status'] == 'failed'}
    uncaptured = []
    for k, v in sorted(inv.items()):
        if k in have or k in tried: continue
        uncaptured.append({'id': 'code-' + slug(k), 'title': v.get('name', k), 'kind': v.get('kind', 'Screen'), 'key': k, 'family': k,
                           'area': 'Not captured yet', 'status': 'uncaptured',
                           'why': 'Found in the ' + ('site’s files' if st.kind == 'pages' else 'code') + ' (' + v.get('where', k) + '), but nothing the scan tapped opened it',
                           'links': [], 'from': [], 'docs': [], 'errors': []})
    all_screens = screens + uncaptured

    # screen IDs: the keys for screens, notes, flows, captions, tags and the map layout, when the app has them
    idinfo = IDS.apply(st, all_screens, register, out) if st.ids else None

    # flows, captions and hand-written doors, now that every screen has its final id
    ref = IDS.Resolver(st, all_screens)
    flow_list = []
    for f in st.flows:
        fr = flows.get(f['id'])
        if not fr: continue
        for stp in fr['steps']:
            stp['screen'] = ref.from_capture(stp.get('sig'), stp.get('ids'))
        flow_list.append(fr)
    for s in all_screens:
        c = ref.lookup_table(st.captions, s)
        if c: s['caption'] = c
    doors = []
    for d in st.doors:
        a, b = ref.find(d.get('from')), ref.find(d.get('to'))
        doors.append({'from': a, 'to': b, 'fromRef': d.get('from'), 'toRef': d.get('to'), 'how': d.get('how', ''),
                      'kind': d.get('kind', 'Hand-written'), 'label': d.get('label') or d.get('how', '')})
        if not a or not b: problems.add('Door not matched to a screen: ' + str(d.get('from')) + ' → ' + str(d.get('to')))
    proposed = []
    for pid, p in sorted(props.items()):
        p['screen'] = ref.find(p.get('screen')) or p.get('screen')
        p.pop('file', None)
        proposed.append(p)

    # aliases: the other names a screen had (its first id, its code key), so notes and layouts made under them still find it
    aliases = {}
    for s in all_screens:
        for a in [s.get('slug'), s.get('family'), s.get('key')] + list(s.get('aliasKeys') or []):
            if a and a != s['id']: aliases.setdefault(a, s['id'])

    head = subprocess.run(['git', '-C', app_dir, 'log', '-1', '--format=%h %s'], capture_output=True, text=True).stdout.strip()
    now = dt.datetime.now(dt.timezone.utc)
    app = dict(st.app)
    if st.queue: app['queue'] = st.queue
    return {'format': 4, 'kit': VERSION, 'app': app, 'kind': st.kind,
            'scan': {'at': now.isoformat(timespec='seconds'), 'commit': head, 'version': st.version(app_dir, log),
                     'viewport': st.viewport, 'data': st.data, 'clock': st.fixed_time.isoformat(), 'passes': passes,
                     'codeStates': len(inv), 'docProblems': sorted(problems)},
            'areas': [a for a in st.areas] or sorted({s['area'] for s in screens}),
            'inventory': sorted(inv), 'changelog': log[:40], 'ids': idinfo, 'aliases': aliases,
            'flows': flow_list, 'doors': doors, 'proposed': proposed, 'screens': all_screens}


def docs_for(st, e, fam, area, sections, problems):
    want = list(e.get('docs') or []) + list(st.docs(e.get('key') or fam, fam, area))
    out = []
    for f, label in want:
        hit = next((d for d in sections if d['file'] == f and d['label'] == label), None)
        if not hit: problems.add(f + ' › ' + label); continue
        d = {'file': f, 'heading': hit['label'], 'url': hit['url'], 'anchor': hit['anchor']}
        if d not in out: out.append(d)
    return out[:3]


def mention_for(st, fam, title, log):
    words = [w.lower() for w in (st.words.get(fam) or [title.split(' · ')[0]]) if w]
    for c in log:
        t = c['title'].lower()
        if any(re.search(r'\b' + re.escape(w) + r'\b', t) for w in words): return c
    return None


def summary(atlas, say, secs):
    c = lambda stt: sum(s['status'] == stt for s in atlas['screens'])
    nl = [l for s in atlas['screens'] for l in s.get('links', [])]
    say(f"{c('captured')} captured, {c('failed')} failed, {c('uncaptured')} found in code only, {len(nl)} buttons "
        f"({sum(l['how'] == 'seen' for l in nl)} seen working, {sum(l['how'] == 'stays' for l in nl)} change their screen, "
        f"{sum(l['how'] == 'not-tested' for l in nl)} not tested, {sum(l['how'] == 'broken' for l in nl)} broken), {round(secs)} s")
    if atlas['flows']:
        say('Flows: ' + ', '.join(f"{f['id']} {len(f['steps'])} steps" + ('' if f['status'] == 'captured' else ' (failed: ' + f.get('why', '') + ')') for f in atlas['flows']))
    ids = atlas.get('ids')
    if ids:
        if ids['noId']: say('No ID yet: ' + ', '.join(f"{x['title']} (suggested {x['suggested']})" for x in ids['noId']))
        if ids['notFound']: say('In the register, not found this scan: ' + ', '.join(ids['notFound']))
    if atlas['scan']['docProblems']: say('Not matched: ' + '; '.join(atlas['scan']['docProblems']))
