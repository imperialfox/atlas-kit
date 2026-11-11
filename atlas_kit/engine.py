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
from . import states as STATES


class TapError(RuntimeError):
    pass


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
        self.parts = None
        self.kept = None     # (set-up, page): one page reused for states with the same set-up (1.2)
        self.reused = 0

    def page(self, setup):
        """A page for this set-up: the kept one put back with the app's RESET when it has the same set-up, else a fresh one."""
        st, key = self.st, tuple(setup)
        if self.kept and self.kept[0] == key and self.reusing():
            pg = self.kept[1]; self.kept = None
            try:
                pg.clock.set_system_time(st.fixed_time.timestamp())
                pg.evaluate(st.reset_js)
                pg.wait_for_timeout(60)
                self.reused += 1
                return pg
            except Exception:
                try: pg.context.close()
                except Exception: pass
        self.drop()
        return self.fresh(setup)

    def keep(self, pg, setup):
        """Done with this page: keep it for the next state with the same set-up, when the app can put itself back."""
        if self.reusing():
            self.drop(); self.kept = (tuple(setup), pg)
        else:
            pg.context.close()

    def reusing(self):
        st = self.st
        return bool(st.reuse and st.reset_js and st.kind == 'screens' and self.ctx.get('reuse', True))

    def drop(self):
        if self.kept:
            try: self.kept[1].context.close()
            except Exception: pass
            self.kept = None

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

    def target(self, pg, sel):
        """The selector to tap: as written, or for a part name ('AB-001 › add-button'), the part found on the page."""
        if not STATES.is_ref(sel): return self.fill(sel)
        if self.parts is None: self.parts = IDS.part_map(self.register)
        renamed, o = STATES.js_args(self.st, self.parts, sel, self.fill)
        r = pg.evaluate(B.TAP_JS, o)
        where = (o['screen'] + ' ' if o['screen'] else '') + '› ' + o['name']
        if r.get('err') == 'showing': raise TapError('couldn’t tap ' + where + ': ' + r['showing'] + ' is showing, not ' + o['screen'])
        if r.get('err') == 'css': raise TapError('couldn’t tap ' + where + ': what narrows it isn’t a selector (' + o['css'] + ')')
        if r.get('err'): raise TapError('couldn’t tap ' + where + ': no part by that name is on screen')
        return B.TAPPED

    def tap(self, pg, sel, force=False):
        loc = pg.locator(self.target(pg, sel)).first
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
            except TapError as e:
                raise RuntimeError('Didn’t open: ' + str(e) + ' (on the way there)')
            except Exception:
                raise RuntimeError('Didn’t open: couldn’t tap ' + (STATES.described(arg) if STATES.is_ref(arg) else self.fill(arg)) + ' on the way there (not on screen)')
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
        pg = R.page(ent['setup'])
        landed = R.open(pg, ent)
        r['sig'] = landed
        if st.kind == 'pages' and R.statuses and R.statuses[-1] >= 400:
            raise RuntimeError(f'Didn’t open: the address answered {R.statuses[-1]} (not found)')
        want = ent.get('expect')
        if ent.get('screen'):   # a state by screen ID (1.2): the screen it opened must carry that ID
            got = pg.evaluate(B.IDS_JS, R.opts)
            shown = got['sheet'] if got['sheetOpen'] else got['screen']
            if shown != ent['screen']:
                raw = got['rawSheet'] if got['sheetOpen'] else got['rawScreen']
                raise RuntimeError('Didn’t open: opened ' + (shown or ('a ' + ('sheet' if got['sheetOpen'] else 'screen') + ' with no ID'
                                   + (' (' + raw + ')' if raw else ''))) + ' instead of ' + ent['screen'])
        elif want and st.family(landed) != st.family(want):
            raise RuntimeError('Didn’t open: landed on ' + st.describe(landed) + ' instead')
        elif not want and ent.get('key') and st.kind == 'screens' and not st.family(landed).startswith(st.family(ent['key'])):
            raise RuntimeError('Didn’t open: landed on ' + st.describe(landed) + ' instead')
        sheet = R.sheet_open(pg)
        if ent.get('kind') == 'Sheet' and not sheet:
            raise RuntimeError('Didn’t open: the sheet isn’t on screen')
        r['sheet'] = sheet
        r['title'] = R.title(pg)
        if st.ids: r['ids'] = pg.evaluate(B.IDS_JS, R.opts)
        pg.screenshot(path=os.path.join(out, 'shots', sid + '.jpg'), type='jpeg', quality=82)
        r['fullHeight'] = pg.evaluate('Math.max(document.documentElement.scrollHeight, document.body ? document.body.scrollHeight : 0)')
        if r['fullHeight'] > st.viewport['h'] + 1:   # the full length only when there's more than the view (1.2)
            pg.screenshot(path=os.path.join(out, 'shots', sid + '-full.jpg'), type='jpeg', quality=78, full_page=True)
        r['elements'] = pg.evaluate(B.ELEMENTS_JS, R.opts)
        r['errors'] = list(dict.fromkeys(R.errors))
        if not taps or not ent.get('taps', True):
            R.keep(pg, ent['setup']); return r
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
        R.keep(pg, ent['setup'])
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
        for ent in sorted(entries, key=lambda e: tuple(e['setup'])):   # same set-up together, so one page serves them
            res[ent['id']] = capture_entry(R, ent, out, taps)
        R.drop()
        if R.register is not None: res['__register'] = R.register
        res['__reused'] = R.reused
        b.close()
    return res


def run_parallel(fn, items, workers, common):
    if not items: return {}
    n = max(1, min(workers, len(items)))
    parts = [items[i::n] for i in range(n)]
    out, reused = {}, 0
    if n == 1:
        res = [fn((common[0], parts[0]) + common[1:])]
    else:
        with cf.ProcessPoolExecutor(n) as ex:
            res = list(ex.map(fn, [(common[0], p) + common[1:] for p in parts]))
    for r in res:
        reused += r.pop('__reused', 0)
        out.update(r)
    if reused: out['__reused'] = reused
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
        root = None
        if isinstance(start, str):   # a starting screen by its id, or (1.2) the plain state of a screen ID
            root = next((r for r in st.roots if r['id'] == start), None) or \
                next((r for r in st.roots if r.get('screen') == start and not r.get('state_of')), None)
            if not root: raise RuntimeError('The flow starts at ' + start + ', which isn’t a starting screen or a state')
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
                    pg.locator(R.target(pg, sel)).first.fill(text)
                if s.get('js'): pg.evaluate(s['js'])
                if s.get('tap'):
                    loc = pg.locator(R.target(pg, s['tap'])).first
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
         say=print, scan_id=None, pictures=False, full=None, reuse=None):
    """pictures=True (1.2): every starting screen and state through its steps, no button tests, no extra passes; the
    links, doors and map lines come from `full` (the folder of the latest full scan), labelled with its date.
    reuse=False turns page reuse off for this scan (the settings' REUSE otherwise)."""
    t0 = time.time()
    if pictures: taps = False
    mode = 'pictures' if pictures else 'quick' if not taps else 'part' if only else 'full'
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
        if reuse is not None: ctx['reuse'] = bool(reuse)
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
            e['named'] = list(e['steps'])
            if e.get('state_of') and 'taps' not in e: e['taps'] = False  # a state shares its screen's links
            entries.append(e)
        gone_roots = [e for e in entries if inv and e.get('key') and not any(k in inv for k in st.keys_of(e['key']))]
        queue = [e for e in entries if e not in gone_roots]
        results, fams, passes, register, reused = {}, {}, 0, None, 0
        limit = st.max_pages if st.kind == 'pages' else st.max_passes
        while queue and passes < limit:
            passes += 1
            say(f'Pass {passes}: {len(queue)} screen' + ('s' if len(queue) != 1 else ''))
            got = run_parallel(job, queue, workers, common)
            reused += got.pop('__reused', 0)
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
                    if st.kind == 'screens':   # the same taps by part name, for suggested states (1.2)
                        ne['named'] = STATES.suggestion_steps(e.get('named', e['steps']), r.get('ids'), l, ctx.get('vars'))
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

    fa = None
    if pictures and full:
        fa = CMP.load(full)
        if not fa: say('No full scan found at ' + str(full) + ': buttons not checked yet')
    atlas = assemble(st, app_dir, out, entries, results, gone_roots, inv, flows, props, register, passes, ctx,
                     full=(os.path.abspath(full), fa) if fa else None)
    atlas['scan']['id'] = scan_id or dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    atlas['scan']['seconds'] = round(time.time() - t0)
    atlas['scan']['mode'] = mode
    atlas['scan']['reused'] = reused
    if mode == 'full':
        atlas['scan']['buttons'] = {'id': atlas['scan']['id'], 'at': atlas['scan']['at'], 'version': atlas['scan'].get('version')}
    elif fa:
        atlas['scan']['buttons'] = {'id': fa['scan']['id'], 'at': fa['scan']['at'], 'version': fa['scan'].get('version')}
    CMP.compare_all(atlas, out, prev, baselines, say)
    if mode == 'full' and st.kind == 'screens':
        sugg = suggestions(st, atlas, entries)
        STATES.write_suggestions(os.path.join(out, 'suggested_states.py'), atlas, sugg)
        atlas['scan']['suggested'] = len(sugg)
    json.dump(atlas, open(os.path.join(out, 'atlas.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    summary(atlas, say, time.time() - t0)
    return atlas


def suggestions(st, atlas, entries):
    """Screens found by tapping that have no state yet, with the taps that reached them (by part name where named)."""
    by_first = {}
    for s in atlas['screens']: by_first[s.get('slug') or s['id']] = s
    covered = set(st.state_screens())
    out = []
    for e in entries:
        if e['how'] != 'Found' or not e.get('named'): continue
        s = by_first.get(e['id'])
        if not s or s['status'] != 'captured' or s.get('stateOf'): continue
        if s.get('sid') and (s['sid'] in covered or s['sid'] in st.no_state): continue
        if not s.get('sid') and any(r.get('key') == s.get('key') for r in st.roots): continue
        out.append({'screen': s.get('sid'), 'id': (s['sid'].lower() if s.get('sid') else e['id']), 'title': s['title'],
                    'key': s.get('key'), 'setup': e['setup'], 'steps': e['named']})
    return out


# ---------- putting it together ----------
def assemble(st, app_dir, out, entries, results, gone_roots, inv, flows, props, register, passes, ctx, full=None):
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

    reg_by = {r['id']: r for r in register or []}
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
        reg = reg_by.get(str(e.get('screen'))) if e.get('screen') else None   # a state by screen ID: the register's area and kind
        area = e.get('area') or (reg or {}).get('area') or (st.area_of(sig, None) if sig is not None else None)
        if st.areas and area not in st.areas: area = 'Other'
        area = area or 'Screens'
        kind = e.get('kind') or (('State' if e.get('state_of') else reg.get('kind')) if reg and reg.get('kind') else None) or st.kind_of(fam, bool(r.get('sheet')))
        shot = 'shots/' + e['id'] + '.jpg' if r['status'] == 'captured' else None
        has_full = shot and os.path.exists(os.path.join(out, 'shots', e['id'] + '-full.jpg'))
        if st.kind == 'pages':
            how = e.get('opened') or 'Opened by its address'
            how += ': ' + (e['steps'][0][1] if e['steps'] else '')
        else:
            how = ' → '.join(('tap ' if s[0] == 'tap' else 'forced tap ' if s[0] == 'force' else 'shortcut ') + str(s[1]) for s in e['steps']) or 'the app as it opens'
            if e['setup']: how = 'set up with ' + ', '.join(e['setup']) + '; ' + how
        screens.append({
            'id': e['id'], 'title': title, 'area': area, 'kind': kind, 'key': e.get('key') or fam, 'family': fam, 'setup': e['setup'],
            'state': e.get('state'), 'stateOf': e.get('state_of'), 'found': e['how'], 'via': e.get('via'), 'how': how,
            'screen': e.get('screen'),
            'status': r['status'], 'why': r.get('why'), 'errors': r.get('errors', []), 'sig': sig, 'ids': r.get('ids'),
            'shot': shot, 'full': ('shots/' + e['id'] + '-full.jpg' if has_full else shot) if shot else None, 'fullHeight': r.get('fullHeight'),
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
    for s in screens:   # a failed state by screen ID accounts for that screen's code keys (1.2)
        r = reg_by.get(str(s.get('screen'))) if s['status'] == 'failed' and s.get('screen') else None
        if r: tried.update(str(k) for k in [r.get('key')] + list(r.get('aliases') or []) if k)
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

    # a pictures-only scan (1.2): buttons, links and the screens only tapping reached, from the latest full scan
    if full: carry(st, out, all_screens, full, idinfo)

    # states (1.2): every Live register screen has a state, or a written reason
    states = coverage_marks(st, all_screens, register) if st.ids and register is not None else None

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
            'flows': flow_list, 'doors': doors, 'proposed': proposed, 'states': states, 'screens': all_screens}


def coverage_marks(st, screens, register):
    """Marks each Live register screen with no state "No state yet", or with its written reason (NO_STATE)."""
    named = st.state_screens()
    covered = set(named)
    for s in screens:   # a starting screen that opened a screen with an ID is a state of it, named or not
        if s.get('found') == 'Root' and s['status'] == 'captured' and s.get('sid') and not s.get('fromFull'): covered.add(s['sid'])
    missing, reasons = [], {}
    for r in register:
        if not IDS.live(r): continue
        why = st.no_state.get(r['id'])
        if why: reasons[r['id']] = why
        elif r['id'] not in covered: missing.append(r['id'])
        for s in screens:
            if s.get('sid') != r['id'] or s.get('stateOf'): continue
            if why: s['noState'] = why
            elif r['id'] not in covered: s['stateMissing'] = True
    known = {r['id'] for r in register}
    return {'named': sum(len(v) for v in named.values()), 'screens': len(covered & known), 'missing': missing, 'reasons': reasons,
            'unknown': sorted({i for i in list(named) + list(st.no_state) if i not in known})}


def carry(st, out, screens, full, idinfo):
    """A pictures-only scan keeps the latest full scan's buttons and links for each screen, marks a screen whose picture
    changed since then, and keeps the full scan's screens this scan has no state for, with their pictures."""
    fdir, fa = full
    pv, find = CMP.matcher(fa)
    got = set()
    for s in screens:
        o = find(s)
        if not o: continue
        if s['status'] in ('uncaptured', 'notfound') and o['status'] == 'captured': continue   # kept from the full scan, below
        got.add(o['id'])
        if s['status'] != 'captured' or o['status'] != 'captured': continue
        if not s['links'] and o.get('links'): s['links'] = json.loads(json.dumps(o['links']))
        if o.get('linksOf') and not s.get('linksOf'): s['linksOf'] = o['linksOf']
        a, b = os.path.join(fdir, o['shot']), os.path.join(out, s['shot'])
        if os.path.exists(a) and os.path.exists(b):
            d = CMP.picture_diff(a, b)
            if d: s['buttonsStale'] = {k: d[k] for k in ('pct', 'box') if d.get(k) is not None}
    carried = []
    for oid, o in pv.items():
        if oid in got or o['status'] != 'captured' or not o.get('shot'): continue
        if not os.path.exists(os.path.join(fdir, o['shot'])): continue
        c = json.loads(json.dumps(o))
        for k in ('shot', 'full'):
            if c.get(k) and os.path.exists(os.path.join(fdir, c[k])):
                os.makedirs(os.path.dirname(os.path.join(out, c[k])), exist_ok=True)
                shutil.copy(os.path.join(fdir, c[k]), os.path.join(out, c[k]))
        for k in ('change', 'since', 'from'): c.pop(k, None)
        c['fromFull'] = {'id': fa['scan']['id'], 'at': fa['scan']['at'], 'version': fa['scan'].get('version')}
        carried.append(c)
    if carried:
        keys, sids = set(), set()
        for c in carried:
            if c.get('sid'): sids.add(c['sid'])
            if c.get('sig') is not None: keys.update(str(k) for k in st.keys_of(c['sig']))
        screens[:] = [s for s in screens if not (s['status'] == 'uncaptured' and (str(s.get('key')) in keys or s.get('sid') in sids))
                      and not (s['status'] == 'notfound' and s.get('sid') in sids)] + carried
        if idinfo: idinfo['notFound'] = [i for i in idinfo['notFound'] if i not in sids]
    for s in screens:   # where each screen is reached from, with the carried links
        s['from'] = [{'from': o['id'], 'label': l['label'], 'how': l['how']} for o in screens for l in o.get('links', [])
                     if l.get('to') == s['id'] and o['id'] != s['id'] and not o.get('stateOf')]


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
    sc = atlas['scan']
    if sc.get('mode') == 'pictures':
        b = sc.get('buttons')
        say('Pictures only: buttons last checked ' + (b['at'] + ' (' + str(b.get('version') or '?') + ')' if b else 'never (no full scan yet)')
            + (f", {sum(1 for s in atlas['screens'] if s.get('buttonsStale'))} changed since then" if b else ''))
    if sc.get('reused'): say(f"Pages reused between states: {sc['reused']}")
    stt = atlas.get('states')
    if stt:
        say(f"States: {stt['screens']} screens have one" + (f", {len(stt['reasons'])} have a written reason" if stt['reasons'] else '')
            + ('; No state yet: ' + ', '.join(stt['missing']) if stt['missing'] else '; every Live screen has one'))
        if stt['unknown']: say('Not in the register: ' + ', '.join(stt['unknown']))
    if sc.get('suggested'): say(f"Suggested states: {sc['suggested']} (suggested_states.py)")
    ids = atlas.get('ids')
    if ids:
        if ids['noId']: say('No ID yet: ' + ', '.join(f"{x['title']} (suggested {x['suggested']})" for x in ids['noId']))
        if ids['notFound']: say('In the register, not found this scan: ' + ', '.join(ids['notFound']))
    if atlas['scan']['docProblems']: say('Not matched: ' + '; '.join(atlas['scan']['docProblems']))
