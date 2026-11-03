"""Tests for the Atlas kit: the scanner, the viewer and "check my notes", on two made-up apps.

    python3 tests/test_kit.py                 everything (about 2 minutes)
    python3 tests/test_kit.py names shared    only some parts: names, shared, site, state, compare, viewer, phone, notes

- tests/apps/site: a made-up website (pages with addresses).
- tests/apps/state: a made-up app of screens without addresses, with screen IDs, a flow, a hand-written door and
  captions; its "version 2" (made in a temporary copy) renames a code key, adds a screen with no ID, lists a screen
  the scan can't find and changes how Home looks.
- phone: the viewer at iPhone 15 Pro size with real touch events (pinch, double-tap, swipes, hold-to-move), plus the
  computer's extras (trackpad pinch, animated map buttons).
- With the Prototype kit beside this repo (../prototype-kit, or PROTOTYPE_KIT=path), a real Prototype kit page is
  also captured as a proposed screen. Without it, a stand-in page is used.

Needs Playwright and Pillow. Everything is made in a temporary folder; nothing is left behind.
"""
import functools
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

TESTS = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(TESTS)
sys.path.insert(0, KIT)
from atlas_kit import engine, notes as NOTES, VERSION  # noqa: E402

STATE = os.path.join(TESTS, 'apps', 'state')
SITE = os.path.join(TESTS, 'apps', 'site')
# SHARED.md as released in Prototype kit 1.1.0; both kits keep it identical
SHARED_SHA = 'd9ab7d28a4f57bc5f15671ffacd02a5a95f27845c128a248f9a6a635ea04b0d0'

PASSED, FAILS = 0, []


def ok(cond, msg):
    global PASSED
    if cond: PASSED += 1
    else: FAILS.append(msg)
    print(('  pass  ' if cond else '  FAIL  ') + msg, flush=True)


def quiet(*a): pass


def scan(settings, app, out, **kw):
    return engine.scan(settings, app, out, workers=3, say=quiet, **kw)


def by(atlas):
    return {s['id']: s for s in atlas['screens']}


def prototype_kit():
    p = os.environ.get('PROTOTYPE_KIT') or os.path.join(os.path.dirname(KIT), 'prototype-kit')
    return p if os.path.exists(os.path.join(p, 'kit.js')) else None


# ---------- the kit belongs to no app ----------
def t_names():
    print('No app’s names are in the kit')
    banned = ['Vocal Sessions', 'Vocal-Sessions', 'vocalTracker', 'RENDER_QUEUE', 'VS-0', 'Tesco', 'North Designerwear', 'ivanc',
              'Tidy list', 'Pebble', 'TL-0']
    files = ['atlas.py', 'viewer.html'] + ['atlas_kit/' + f for f in os.listdir(os.path.join(KIT, 'atlas_kit')) if f.endswith('.py')]
    hits = []
    for f in files:
        txt = open(os.path.join(KIT, f), encoding='utf-8').read()
        hits += [f + ': ' + b for b in banned if b in txt]
    ok(not hits, 'kit code and viewer name no app (' + (', '.join(hits) or f'{len(files)} files checked') + ')')
    for f in ('README.md', 'CHANGELOG.md', 'SHARED.md'):
        txt = open(os.path.join(KIT, f), encoding='utf-8').read()
        h = [b for b in banned[:9] if b in txt]
        ok(not h, f'{f} names no app' + (' (' + ', '.join(h) + ')' if h else ''))


def t_shared():
    print('SHARED.md is the same as the Prototype kit’s')
    mine = open(os.path.join(KIT, 'SHARED.md'), 'rb').read()
    ok(hashlib.sha256(mine).hexdigest() == SHARED_SHA, 'SHARED.md matches the one released in Prototype kit 1.1.0')
    pk = prototype_kit()
    if pk:
        ok(open(os.path.join(pk, 'SHARED.md'), 'rb').read() == mine, 'SHARED.md is identical to ' + pk + '/SHARED.md')
    else:
        print('  skip  the Prototype kit isn’t beside this repo, so only the released copy is compared')


# ---------- a website ----------
def t_site(tmp):
    print('A website (pages with addresses)')
    out = os.path.join(tmp, 'site1')
    a = scan(os.path.join(SITE, 'atlas_settings.py'), SITE, out)
    s = by(a)
    ok(all(k in s and s[k]['status'] == 'captured' for k in ('home', 'about', 'contact', 'menu', 'menu-bread', 'menu-cakes')),
       'every linked page is captured: ' + ', '.join(sorted(k for k in s if s[k]['status'] == 'captured')))
    ok(all(s[k]['kind'] == 'Page' for k in ('home', 'about')), 'pages are kind Page')
    ok(s['menu-bread']['area'] == 'Menu' and s['menu']['area'] == 'Menu' and s['about']['area'] == 'Home', 'areas come from the folders (Menu, Home)')
    ok(s['home']['title'] == 'Home' and s['about']['title'] == 'About', 'titles come from each page (Home, About)')
    L = {l['label']: l for l in s['home']['links']}
    ok(L['About']['how'] == 'seen' and L['About']['to'] == 'about', 'a link is seen working and points at its page')
    ok(L['Old offers']['how'] == 'broken' and '404' in L['Old offers']['why'], 'a link to a missing page is Broken (404)')
    ok(L['Find us on a map']['how'] == 'not-tested' and 'outside' in L['Find us on a map']['why'], 'a link to another site is Not tested (outside)')
    ok(L['Email us']['how'] == 'not-tested', 'an email link is Not tested')
    ok(L['Show opening hours']['how'] == 'stays', 'a button that changes the page is “Changes this screen”')
    ok(s.get('code-old-html', {}).get('status') == 'uncaptured', 'a page in the folder that nothing links to is “Not captured yet”')
    ok(os.path.exists(os.path.join(out, s['about']['shot'])) and os.path.exists(os.path.join(out, s['about']['full'])), 'each page has its top and full-length pictures')
    ok(any(e.get('tag') == 'h1' for e in s['about']['elements']), 'what’s on each page is mapped for tap-a-part notes')
    return out


# ---------- an app of screens without addresses, with IDs ----------
def t_state(tmp):
    print('An app of screens without addresses (with screen IDs, a flow, a door and captions)')
    out = os.path.join(tmp, 'state1')
    prop = proposed_list(tmp)
    a = scan(os.path.join(STATE, 'atlas_settings.py'), STATE, out, proposed=prop)
    s = by(a)
    want = ['TL-001', 'TL-002', 'TL-003', 'TL-004', 'TL-005', 'TL-006']
    ok(all(k in s and s[k]['status'] == 'captured' for k in want), 'every screen is captured under its ID: ' + ', '.join(k for k in s if s[k]['status'] == 'captured'))
    ok(s['TL-001']['idFrom'] == 'screen' and s['TL-005']['kind'] == 'Sheet', 'IDs are read from the screen itself; the sheet is kind Sheet')
    ok('TL-001~first-launch' in s and s['TL-001~first-launch']['sid'] == 'TL-001', 'a state shares its screen’s ID (TL-001~first-launch)')
    ok(a['ids']['register'] == 6 and not a['ids']['noId'] and not a['ids']['notFound'], 'the register is read from the page, every screen has an ID')
    ok(s['TL-001'].get('caption', '').startswith('Where the app opens') and not s['TL-002'].get('caption'), 'captions come from the settings; a screen without one has none')
    L = {l['label']: l for l in s['TL-003']['links']}
    ok(L['Clear the list']['how'] == 'not-tested' and 'deletes' in L['Clear the list']['why'], 'a button that clears data is never tapped')
    ok(L['Help (opens the web)']['how'] == 'not-tested', 'a link out of the app is Not tested')
    ok(L['About ›']['to'] == 'TL-004', 'links point at screens by ID')
    ok(any(l['kind'] == 'Tab bar' for l in s['TL-001']['links']), 'tab bar buttons are marked Tab bar')
    f = a['flows'][0] if a['flows'] else {}
    steps = f.get('steps', [])
    ok(f.get('status') == 'captured' and len(steps) >= 4, f'the flow F-01 is walked: {len(steps)} pictures (start plus 3 steps)')
    ok([x['screen'] for x in steps] == ['TL-001', 'TL-005', 'TL-005', 'TL-002'], 'each step lands on its screen; one screen at two moments (empty sheet, filled in)')
    ok(steps and steps[0].get('next') and steps[3]['label'] == 'Save', 'the tapped button is recorded between steps')
    d = a['doors'][0] if a['doors'] else {}
    ok(d.get('from') == 'TL-002' and d.get('to') == 'TL-006' and d.get('kind') == 'Hold', 'the hand-written door List → Item menu is matched to both screens')
    ok(s.get('code-stats', {}).get('status') == 'uncaptured', 'a screen the code has but no tap reaches is “Not captured yet”')
    P = a['proposed']
    ok(P and all(p['status'] == 'captured' and p['screen'] == 'TL-005' for p in P), f'the proposed prototype(s) are captured beside TL-005 ({len(P)})')
    ok(P and any(e.get('part') == 'save-button' for e in P[0].get('elements', [])), 'the prototype’s named parts are mapped')
    return out


def proposed_list(tmp):
    items = [{'screen': 'add', 'title': 'Save first (stand-in)', 'file': os.path.join(STATE, 'prototypes', 'add-item-save-first.html')}]
    pk = prototype_kit()
    if pk:
        src = os.path.join(tmp, 'proto')
        os.makedirs(src, exist_ok=True)
        shutil.copy(os.path.join(TESTS, 'fixtures', 'prototype_kit_page.html'), os.path.join(src, 'p.html'))
        for f in ('kit.js', 'kit.css'): shutil.copy(os.path.join(pk, f), src)
        subprocess.run([sys.executable, os.path.join(pk, 'tools', 'bundle.py'), os.path.join(src, 'p.html'), os.path.join(src, 'bundled.html')], check=True, capture_output=True)
        items.insert(0, {'screen': 'TL-005', 'title': 'Save first', 'version': '1', 'slug': 'test-prototype', 'file': os.path.join(src, 'bundled.html')})
    return items


# ---------- version 2: compare, tags since a version, IDs that survive renames ----------
def state_v2(tmp):
    app = os.path.join(tmp, 'state-v2')
    shutil.copytree(STATE, app, ignore=shutil.ignore_patterns('data', '__pycache__'))
    open(os.path.join(app, 'version.js'), 'w').write('window.APP_VERSION = 2;\n')
    with open(os.path.join(app, 'CHANGELOG.md'), 'a') as f:
        f.write('\n')
    txt = open(os.path.join(app, 'CHANGELOG.md')).read().replace('# Changelog\n', '# Changelog\n\n## 1.1 · 2 Nov 2026\n*Stats, and a brighter Home (T02)*\n')
    open(os.path.join(app, 'CHANGELOG.md'), 'w').write(txt)
    return app


def t_compare(tmp, s1, p1):
    print('Compared with earlier scans (version 2 of each app)')
    app = state_v2(tmp)
    out = os.path.join(tmp, 'state2')
    a = scan(os.path.join(app, 'atlas_settings.py'), app, out, prev=s1, baselines=[s1], proposed=proposed_list(tmp))
    s = by(a)
    ok(s['TL-003']['status'] == 'captured' and s['TL-003']['sig'] == 'prefs', 'the Settings tab is still TL-003 after its code key changed to “prefs”')
    ok('settings' in (s['TL-003'].get('aliasKeys') or []), 'its old code key is kept as an alias')
    st = next((x for x in a['screens'] if x.get('family') == 'stats'), {})
    ok(st.get('status') == 'captured' and not st.get('sid') and st.get('suggested') == 'TL-008', 'a new screen with no ID is flagged: suggested ' + str(st.get('suggested')))
    ok(a['ids']['noId'] and a['ids']['noId'][0]['suggested'] == 'TL-008', 'the scan lists it under “No ID yet”')
    ok(s.get('TL-007', {}).get('status') == 'notfound', 'a register entry the scan can’t find is “Not found this scan”, not deleted')
    ok((s['TL-001'].get('change') or {}).get('kind') == 'looks-different' and s['TL-001']['change'].get('prevShot'), 'Home looks different since the last scan, with its before picture')
    ok((st.get('change') or {}).get('kind') == 'new', 'Stats is new since the last scan')
    bid = a['scan']['baselines'][0]['id'] if a['scan'].get('baselines') else None
    ok(bid and (s['TL-001'].get('since') or {}).get(bid) == 'changed', 'tagged since version 1.0: Home is CHANGED')
    ok(bid and (st.get('since') or {}).get(bid) == 'new', 'tagged since version 1.0: Stats is NEW')
    ok(not (s['TL-002'].get('since') or {}).get(bid), 'an unchanged screen gets no tag (List)')
    cc = a['scan'].get('codeChanges') or {}
    ok('prefs' in cc.get('added', []) and 'settings' in cc.get('gone', []), 'the code’s list: “prefs” added, “settings” gone')
    ok([c['version'] for c in a['scan']['prev']['between']] == ['1.1'], 'the versions released in between are listed (1.1)')

    # the website, version 2: About changed and a news page added
    site2 = os.path.join(tmp, 'site-v2')
    shutil.copytree(SITE, site2)
    p = os.path.join(site2, 'about.html'); open(p, 'w').write(open(p).read().replace('<h1>About us</h1>', '<h1 style="background:#c33;color:#fff;padding:20px">About us</h1>'))
    open(os.path.join(site2, 'news.html'), 'w').write(open(os.path.join(site2, 'about.html')).read().replace('About us', 'News').replace('<title>About', '<title>News'))
    b = scan(os.path.join(site2, 'atlas_settings.py'), site2, os.path.join(tmp, 'site2'), prev=p1, baselines=[p1])
    t = by(b); bid = b['scan']['baselines'][0]['id']
    ok((t['about'].get('since') or {}).get(bid) == 'changed' and (t['news'].get('since') or {}).get(bid) == 'new', 'the website: About is CHANGED and the news page NEW')
    ok({l['label']: l for l in t['home']['links']}["What's new"]['how'] == 'seen', 'the link that was broken now works')
    return out


# ---------- the viewer ----------
FAKE_STORE = r"""(() => {
  if (window.__preset && !sessionStorage.getItem('__fakeDocs')) sessionStorage.setItem('__fakeDocs', window.__preset);
  const docs = JSON.parse(sessionStorage.getItem('__fakeDocs') || '{}'), subs = [];
  const persist = () => sessionStorage.setItem('__fakeDocs', JSON.stringify(docs));
  const fire = () => setTimeout(() => subs.forEach(f => f()), 0);
  const copy = v => JSON.parse(JSON.stringify(v));
  const snap = p => ({ id: p.split('/').pop(), exists: p in docs, data: () => copy(docs[p]) });
  const docRef = p => ({
    set: async v => { docs[p] = copy(v); persist(); fire(); },
    update: async v => { docs[p] = Object.assign({}, docs[p], copy(v)); persist(); fire(); },
    delete: async () => { delete docs[p]; persist(); fire(); },
    onSnapshot(cb) { const f = () => cb(snap(p)); subs.push(f); setTimeout(f, 0); return () => {}; } });
  const colRef = n => ({ doc: id => docRef(n + '/' + id),
    onSnapshot(cb) { const f = () => cb({ docs: Object.keys(docs).filter(k => k.startsWith(n + '/') && k.split('/').length === 2).map(snap), metadata: { fromCache: false } }); subs.push(f); setTimeout(f, 0); return () => {}; } });
  window.__store = { docs };
  window.claude = { use: async n => (n === 'db' ? { doc: docRef, collection: colRef } : null) };
})();"""


class Serve:
    def __init__(self, folder):
        shutil.copy(os.path.join(KIT, 'viewer.html'), os.path.join(folder, 'index.html'))
        class Q(SimpleHTTPRequestHandler):
            def log_message(self, *a): pass
        self.srv = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Q, directory=folder))
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = f'http://127.0.0.1:{self.srv.server_address[1]}/'

    def close(self):
        self.srv.shutdown(); self.srv.server_close()


def viewer_page(b, url, preset=None, w=1440, h=900):
    pg = b.new_page(viewport={'width': w, 'height': h})
    errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.on('console', lambda m: errs.append(m.text) if m.type == 'error' and 'Failed to load resource' not in m.text else None)
    if preset is not None: pg.add_init_script('window.__preset = ' + json.dumps(json.dumps(preset)) + ';')
    pg.add_init_script(FAKE_STORE)
    pg.goto(url)
    pg.wait_for_selector('.card')
    pg.wait_for_timeout(200)
    return pg, errs


def t_viewer(tmp, s1, s2):
    print('The viewer (with a stand-in for the page’s store)')
    from playwright.sync_api import sync_playwright
    a1 = json.load(open(os.path.join(s1, 'atlas.json')))
    v1, v2 = Serve(s1), Serve(s2)
    store = {}
    try:
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg, errs = viewer_page(b, v1.url)
            ok(pg.title() == 'Atlas · Tidy list' and 'Tidy list' in pg.inner_text('#appname'), 'the app’s name comes from the scan')
            ok(pg.locator('.card .sid', has_text='TL-005').count() == 1, 'IDs show on the cards')
            ok('Where the app opens' in pg.inner_text('.card[data-id="TL-001"]'), 'captions show on the cards')
            # a note on a named part, by tapping it
            pg.click('.card[data-id="TL-003"]'); pg.click('#addNote'); pg.wait_for_selector('#stage')
            e = next(x for x in by(a1)['TL-003']['elements'] if x.get('part') == 'about-row')
            box = pg.locator('#stage').bounding_box(); k = box['width'] / a1['scan']['viewport']['w']
            pg.mouse.click(box['x'] + (e['x'] + e['w'] / 2) * k, box['y'] + (e['y'] + e['h'] / 2) * k)
            pg.fill('#ntext', 'The About row needs a short description under it')
            pg.click('#nmSave'); pg.wait_for_timeout(400)
            store = pg.evaluate('JSON.parse(JSON.stringify(window.__store.docs))')
            nt = [v for k2, v in store.items() if k2.startswith('notes/')]
            n = nt[0] if nt else {}
            need = ['v', 'n', 'source', 'app', 'screen', 'screenTitle', 'part', 'name', 'box', 'px', 'element', 'text', 'kind', 'status', 'from', 'created', 'updated']
            ok(n and all(f in n for f in need) and n['v'] == 1 and n['source'] == 'atlas', 'a note is saved in note format v1 (every field of SHARED.md)')
            ok(n.get('screen') == 'TL-003' and n.get('part') == 'about-row' and n['from']['scan']['id'] == a1['scan']['id'], 'the note is keyed by screen ID, keeps the part’s name and its scan')
            # an Atlas note on the same screen as the prototype's note, through the page's own note maker
            pg.evaluate("""async()=>{const s=byId['TL-005'], e=s.elements.find(x=>x.part==='save-button');
              await saveNote(makeNote(s,{x:e.x,y:e.y,w:e.w,h:e.h},e,'Save is below the fold on small phones','Layout or spacing'))}""")
            pg.wait_for_timeout(300)
            store = pg.evaluate('JSON.parse(JSON.stringify(window.__store.docs))')
            # flows
            pg.click('[data-view="flows"]'); pg.wait_for_selector('.fshot')
            ok(pg.locator('.sth').count() == 4 and pg.locator('.ring').count() == 1, 'the flow shows its 4 steps, with the button to tap ringed')
            ok('Next: Add an item' in pg.inner_text('#flows'), 'the tapped button shows between steps')
            pg.keyboard.press('ArrowRight'); pg.keyboard.press('ArrowRight')
            ok('filled in' in pg.inner_text('.finfo').lower() and 'Add an item' in pg.inner_text('.finfo h2'), 'stepping through: one screen at another moment (Add an item, filled in)')
            pg.click('[data-lb]'); pg.wait_for_timeout(200)
            ok(pg.locator('#det.open').count() == 1 and 'Add an item' in pg.inner_text('.dtitle'), 'a step opens its screen in the Lightbox')
            ok(pg.locator('#det [data-wipe^="wp-"]').count() >= 1 and pg.locator('#det', has_text='Proposed changes').count() == 1, 'the proposed prototype shows beside its real screen, with the wipe')
            # door and map
            pg.click('.card[data-id="TL-002"]'); pg.wait_for_timeout(150)
            ok('Not tested by the scan' in pg.inner_text('#det') and 'Hold an item' in pg.inner_text('#det'), 'the hand-written door is listed in details')
            pg.click('[data-view="map"]'); pg.wait_for_timeout(300)
            ok(pg.locator('#map path.edge.door').count() == 1, 'the door is drawn as a dotted line on the map')
            ok(pg.locator('#map .elabel').count() == 0, 'map labels are off until switched on')
            pg.click('#mapLabels'); pg.wait_for_timeout(150)
            ok(pg.locator('#map .elabel').count() >= 4 and pg.locator('#map .elabel', has_text='About').count() >= 1, f'the labels switch shows what’s tapped on every line ({pg.locator("#map .elabel").count()})')
            pg.click('[data-view="lightbox"]')
            # search finds IDs and parts
            pg.fill('#q', 'TL-005 › save-button'); pg.wait_for_timeout(150)
            ok([c.get_attribute('data-id') for c in pg.locator('.card').all()] == ['TL-005'], 'search finds “TL-005 › save-button”')
            pg.fill('#q', 'F-01'); pg.wait_for_timeout(150)
            ok(pg.locator('.card').count() >= 3, 'search finds the screens in a flow (F-01)')
            pg.fill('#q', '')
            # report header
            rep = pg.evaluate("reportMd(NOTES)")
            ok(rep.startswith('Atlas notes · note format v1 · ') and 'Source: atlas · App: Tidy list · Scan: ' + a1['scan']['id'] + ' · Kit ' + VERSION in rep, 'the copied report starts with the shared header')
            ok(not [x for x in errs if 'ERR_' not in x], 'no errors on the page' + (': ' + '; '.join(errs[:3]) if errs else ''))
            pg.close()

            # version 2, with the same store: notes stay on their screens; IDs, tags and flags
            pg, errs = viewer_page(b, v2.url, preset=store)
            ok(pg.locator('.card[data-id="TL-003"] .npin').count() == 1, 'the note stays on Settings (TL-003) after its code key changed')
            pg.click('.card[data-id="TL-003"]'); pg.wait_for_timeout(150)
            ok('The About row needs' in pg.inner_text('#det'), 'and shows in its details')
            ok(pg.locator('.card', has_text='No ID yet · suggested TL-008').count() == 1, 'the new screen shows “No ID yet · suggested TL-008”')
            pg.select_option('#since', index=1); pg.wait_for_timeout(150)
            ok(pg.locator('.card .badge.tch').count() >= 1 and pg.locator('.card .badge.tnew').count() >= 1, 'tags since version 1.0: CHANGED and NEW on the cards')
            pg.click('nav.side [data-so="new"]'); pg.wait_for_timeout(150)
            ok(pg.locator('.card').count() == 1 and 'Stats' in pg.inner_text('.card'), 'the NEW filter shows only Stats')
            pg.click('nav.side [data-so="new"]'); pg.check('#showCode'); pg.wait_for_timeout(150)
            ok(pg.locator('.card[data-id="TL-007"]', has_text='Not found this scan').count() == 1, 'Archive (TL-007) shows as “Not found this scan”')
            ok(not [x for x in errs if 'ERR_' not in x], 'no errors on version 2’s page' + (': ' + '; '.join(errs[:3]) if errs else ''))
            pg.close()

            # on a phone
            pg, errs = viewer_page(b, v1.url, preset=store, w=402, h=874)
            ok(pg.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'on a phone nothing scrolls sideways')
            pg.click('[data-view="flows"]'); pg.wait_for_selector('.fshot')
            fb = pg.locator('.fshot').bounding_box()
            ok(fb['width'] <= 402 and fb['height'] < 874 * 0.75, 'on a phone a flow step leaves room for its buttons')
            ok(not [x for x in errs if 'ERR_' not in x], 'no errors on a phone')
            b.close()
    finally:
        v1.close(); v2.close()
    return store


# ---------- on a phone (1.1): real touch events at iPhone 15 Pro size ----------
class Touch:
    """Real touch events through the browser's own input (they arrive as touches and as pointers, like on a phone)."""
    def __init__(self, pg):
        self.pg, self.c = pg, pg.context.new_cdp_session(pg)

    def send(self, kind, pts):
        self.c.send('Input.dispatchTouchEvent', {'type': kind, 'touchPoints': [{'x': x, 'y': y, 'id': i} for i, (x, y) in enumerate(pts)]})

    def tap(self, x, y):
        self.send('touchStart', [(x, y)]); self.send('touchEnd', [])

    def dbl(self, x, y):
        self.tap(x, y); self.pg.wait_for_timeout(90); self.tap(x, y)

    def drag(self, a, b, steps=10, ms=200, hold=0, wait_end=True):
        self.send('touchStart', [a])
        if hold: self.pg.wait_for_timeout(hold)
        for i in range(1, steps + 1):
            t = i / steps
            self.send('touchMove', [(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)])
            if ms: self.pg.wait_for_timeout(ms / steps)
        self.send('touchEnd', [])

    def pinch(self, c, d0, d1, steps=12, ms=240, lift=True, upright=False):
        at = (lambda d: [(c[0], c[1] - d / 2), (c[0], c[1] + d / 2)]) if upright else (lambda d: [(c[0] - d / 2, c[1]), (c[0] + d / 2, c[1])])
        self.send('touchStart', at(d0))
        for i in range(1, steps + 1):
            self.send('touchMove', at(d0 + (d1 - d0) * i / steps))
            if ms: self.pg.wait_for_timeout(ms / steps)
        if lift: self.send('touchEnd', [])


def centre(pg, sel):
    pg.locator(sel).first.scroll_into_view_if_needed()
    b = pg.locator(sel).first.bounding_box()
    return (b['x'] + b['width'] / 2, b['y'] + b['height'] / 2)


SCALE_JS = """sel => { const m = (document.querySelector(sel).style.transform||'').match(/translate3d\\(([-\\d.e]+)px,\\s*([-\\d.e]+)px[^)]*\\)\\s*scale\\(([-\\d.e]+)\\)/);
  return m ? {x:+m[1], y:+m[2], z:+m[3]} : {x:0, y:0, z:1}; }"""
# 40 two-finger moves arriving faster than the screen refreshes (as a phone sends them), then how often the picture
# was redrawn: once per refresh means at most one or two draws
BURST_JS = """async ([sel, area, x, y]) => { const el = document.querySelector(sel), ar = document.querySelector(area); let w = 0;
  const mo = new MutationObserver(r => { w += r.length; }); mo.observe(el, {attributes:true, attributeFilter:['style']});
  const ev = (t, id, cx) => ar.dispatchEvent(new PointerEvent(t, {pointerId:id, pointerType:'touch', isPrimary:id===11, clientX:cx, clientY:y, bubbles:true, cancelable:true}));
  ev('pointerdown', 11, x-40); ev('pointerdown', 12, x+40);
  for (let i = 1; i <= 40; i++) { ev('pointermove', 11, x-40-i); ev('pointermove', 12, x+40+i); }
  await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
  const n = w; ev('pointerup', 11, x-80); ev('pointerup', 12, x+80); mo.disconnect(); return n; }"""


def phone_page(b, url, preset=None):
    ctx = b.new_context(**PHONE)
    pg = ctx.new_page()
    errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.on('console', lambda m: errs.append(m.text) if m.type == 'error' and 'Failed to load resource' not in m.text else None)
    if preset is not None: pg.add_init_script('window.__preset = ' + json.dumps(json.dumps(preset)) + ';')
    pg.add_init_script(FAKE_STORE)
    pg.goto(url)
    pg.wait_for_selector('.card')
    pg.wait_for_timeout(250)
    return pg, errs, Touch(pg)


PHONE = {}   # filled from Playwright's iPhone 15 Pro (393 × 659, touch, a phone's browser) when the phone checks start


def t_phone(tmp, s1, s2, store):
    print('On a phone (iPhone 15 Pro size, real touch events)')
    from playwright.sync_api import sync_playwright
    v1, v2 = Serve(s1), Serve(s2)
    a1 = json.load(open(os.path.join(s1, 'atlas.json')))
    try:
        with sync_playwright() as p:
            d = p.devices['iPhone 15 Pro']
            PHONE.update({k: d[k] for k in ('viewport', 'device_scale_factor', 'is_mobile', 'has_touch', 'user_agent')})
            VW, VH = d['viewport']['width'], d['viewport']['height']
            b = p.chromium.launch()

            # --- the top, the bottom bar, tap targets, banners and search (version 2 has changes to fold away)
            pg, errs, T = phone_page(b, v2.url, preset=store)
            hb = pg.locator('header').bounding_box()
            ok(hb['height'] <= 64, f'the top is one row ({hb["height"]:.0f} pt)')
            bar = pg.locator('.seg.views').bounding_box()
            ok(abs(bar['y'] + bar['height'] - VH) < 1 and pg.locator('.seg.views button').count() == 3, 'Lightbox · Map · Flows sit in a bar along the bottom')
            small = pg.evaluate("""() => [...document.querySelectorAll('header button, header input, header select, .mchips button, .mchips select, .seg.views button, .bfold')]
              .filter(e => e.offsetParent && getComputedStyle(e).visibility !== 'hidden').map(e => [e.id || e.textContent.trim().slice(0, 18), e.getBoundingClientRect()])
              .filter(([n, r]) => r.height < 43.5 || r.width < 43.5).map(([n, r]) => n + ' ' + Math.round(r.width) + '×' + Math.round(r.height))""")
            ok(not small, 'every control at the top, in the filters and in the bottom bar is at least 44 pt' + (' (' + ', '.join(small[:4]) + ')' if small else ''))
            ok(pg.locator('#bfold', has_text='changed since the last scan').count() == 1 and pg.locator('#main .banner').count() == 0, 'the changes banner is folded to one line')
            T.tap(*centre(pg, '#bfold')); pg.wait_for_timeout(150)
            ok(pg.locator('#main .banner').count() >= 1 and 'Fold these away' in pg.inner_text('#bfold'), 'tapping it opens the banners, with “Fold these away”')
            ok(pg.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'nothing scrolls sideways')
            T.tap(*centre(pg, '#searchBtn')); pg.wait_for_timeout(150)
            ok(pg.evaluate("document.querySelector('header').classList.contains('searching') && document.activeElement.id === 'q'"), 'the search icon opens search over the top row')
            pg.keyboard.type('TL-005'); pg.wait_for_timeout(150)
            ok([c.get_attribute('data-id') for c in pg.locator('.card').all()] == ['TL-005'], 'search finds a screen by its ID')
            T.tap(*centre(pg, '#searchX')); pg.wait_for_timeout(150)
            ok(pg.evaluate("!document.querySelector('header').classList.contains('searching') && !document.getElementById('q').value") and pg.locator('.card').count() > 3, 'Cancel closes search and clears it')
            pg.context.close()

            # --- the Lightbox grid, details swipes and the zoom viewer
            pg, errs, T = phone_page(b, v1.url, preset=store)
            cols = lambda: pg.evaluate("getComputedStyle(document.querySelector('.grid')).gridTemplateColumns.split(' ').length")
            ok(cols() == 3, 'the grid starts at 3 columns')
            c = (VW / 2, VH * 0.45)
            T.pinch(c, 90, 150); pg.wait_for_timeout(150)
            n2 = cols()
            T.pinch(c, 150, 100); pg.wait_for_timeout(100); T.pinch(c, 150, 100); pg.wait_for_timeout(150)
            n4 = cols()
            ok((n2, n4) == (2, 4), f'pinching the grid gives 2, then 4 columns ({n2}, {n4})')
            pg.reload(); pg.wait_for_selector('.card'); pg.wait_for_timeout(200)
            ok(cols() == 4, 'the number of columns is remembered on the device')
            T.pinch(c, 100, 150); pg.wait_for_timeout(150)
            vis = pg.evaluate('visible().map(s => s.id)')
            T.tap(*centre(pg, '.card[data-id="%s"]' % vis[1])); pg.wait_for_timeout(200)
            ok(pg.locator('#det.open').count() == 1, 'one tap on a card opens its details')
            mid = (VW / 2, VH * 0.4)
            T.drag((VW * 0.8, mid[1]), (VW * 0.2, mid[1]), ms=120); pg.wait_for_timeout(200)
            after_l = pg.evaluate('S.open')
            T.drag((VW * 0.2, mid[1]), (VW * 0.8, mid[1]), ms=120); pg.wait_for_timeout(200)
            after_r = pg.evaluate('S.open')
            ok((after_l, after_r) == (vis[2], vis[1]), f'in details, swipe left for the next screen and right for the one before ({after_l}, {after_r})')
            T.drag((VW / 2, VH * 0.25), (VW / 2, VH * 0.75), ms=150); pg.wait_for_timeout(200)
            ok(pg.locator('#det.open').count() == 0, 'swipe down closes the details')
            # the zoom viewer, from Full length
            T.tap(*centre(pg, '.card[data-id="TL-001"]')); pg.wait_for_timeout(200)
            T.tap(*centre(pg, '#dfull')); pg.wait_for_selector('#zoomv.open'); pg.wait_for_timeout(250)
            z = lambda: pg.evaluate(SCALE_JS, '#zin')['z']
            za = pg.locator('#zarea').bounding_box(); zc = (za['x'] + za['width'] / 2, za['y'] + za['height'] * 0.35)
            ok(abs(z() - 1) < 0.01, 'Full length opens in the zoom viewer, at full width')
            T.pinch(zc, 80, 200); pg.wait_for_timeout(450)
            ok(2.2 < z() < 2.8, f'pinching zooms the picture ({z():.2f}×)')
            T.dbl(*zc); pg.wait_for_timeout(500)
            n = pg.evaluate(BURST_JS, ['#zin', '#zarea', zc[0], zc[1]]); pg.wait_for_timeout(450)
            ok(1 <= n <= 2, f'drawn once per screen refresh: {n} draw(s) for 40 finger moves in one moment')
            T.pinch(zc, 30, 300, lift=False); pg.wait_for_timeout(60)
            past = z(); T.send('touchEnd', []); pg.wait_for_timeout(550)
            ok(past > 6.05 and abs(z() - 6) < 0.02, f'pinching past the 6× limit gives a little ({past:.2f}×) and eases back to 6× when you let go')
            T.dbl(*zc); pg.wait_for_timeout(600)
            ok(abs(z() - 1) < 0.02, 'double-tap when zoomed in goes back to full width')
            T.dbl(*zc); pg.wait_for_timeout(110)
            midz = z(); pg.wait_for_timeout(500)
            ok(1.05 < midz < 2.45 and abs(z() - 2.5) < 0.02, f'double-tap zooms to 2.5×, animated (half-way {midz:.2f}×)')
            T.tap(*centre(pg, '#zclose')); pg.wait_for_timeout(150)
            ok(pg.locator('#zoomv.open').count() == 0, '✕ closes the zoom viewer')
            # note mode: pinch to zoom, then tap a small part
            T.tap(*centre(pg, '#dclose')); pg.wait_for_timeout(150)
            T.tap(*centre(pg, '.card[data-id="TL-003"]')); pg.wait_for_timeout(200)
            T.tap(*centre(pg, '#addNote')); pg.wait_for_selector('#stwrap'); pg.wait_for_timeout(200)
            sw = pg.locator('#stwrap').bounding_box()
            ok(pg.locator('#nform.peek').count() == 1 and 'Pinch to zoom, then tap a part' in pg.inner_text('#nform'), 'note mode: the form waits as a small sheet (“Pinch to zoom, then tap a part”)')
            ok(sw['width'] >= VW - 20 or sw['height'] >= VH - 200, f'the screen is shown as large as fits ({sw["width"]:.0f} × {sw["height"]:.0f})')
            k = pg.evaluate('NM.k')
            e = min((x for x in by(a1)['TL-003']['elements'] if x['w'] * x['h'] > 0), key=lambda x: x['w'] * x['h'])   # the smallest part
            sc = (sw['x'] + (e['x'] + e['w'] / 2) * k, sw['y'] + (e['y'] + e['h'] / 2) * k)
            T.pinch(sc, 40, 120, upright=True); pg.wait_for_timeout(400)   # fingers above and below it, so both land on the screen
            zn = pg.evaluate(SCALE_JS, '#stage')
            ok(2.5 < zn['z'] <= 5, f'pinch zooms the screen while marking ({zn["z"]:.2f}×)')
            def place(e): return (sw['x'] + zn['x'] + (e['x'] + e['w'] / 2) * k * zn['z'], sw['y'] + zn['y'] + (e['y'] + e['h'] / 2) * k * zn['z'])
            T.tap(*place(e)); pg.wait_for_timeout(250)
            got = pg.evaluate('NM.el && NM.el.path')
            ok(got == e['path'] and pg.locator('#nform.peek').count() == 0, f'a small part ({e["w"]:.0f} × {e["h"]:.0f} pt) is picked by tapping it zoomed in, and the form opens')
            ok(abs(pg.evaluate(SCALE_JS, '#stage')['z'] - zn['z']) < 0.02, 'the zoom stays after picking')
            T.tap(*centre(pg, '#nmCancel')); pg.wait_for_timeout(150)
            ok(not [x for x in errs if 'ERR_' not in x], 'no errors in the Lightbox, details or zoom viewer' + (': ' + '; '.join(errs[:3]) if errs else ''))
            pg.context.close()

            # --- the map
            pg, errs, T = phone_page(b, v1.url, preset=store)
            T.tap(*centre(pg, '[data-view="map"]')); pg.wait_for_selector('#mapin'); pg.wait_for_timeout(500)
            k0 = pg.evaluate('MV.k')
            ok(0.45 <= k0 <= 0.9, f'the map opens at a readable size ({k0 * 100:.0f}%)')
            ok(not pg.locator('.mbar').is_visible() and not pg.locator('.mlegend').is_visible(), 'the map’s options and key are folded away')
            T.tap(*centre(pg, '#mopts')); pg.wait_for_timeout(150)
            ok(pg.locator('.mbar').is_visible() and pg.locator('#mapLabels').is_visible(), 'Map options shows Show, Labels, Note label and Tidy layout')
            T.tap(*centre(pg, '#mapLabels')); pg.wait_for_timeout(150)
            ok(pg.locator('#map .elabel').count() >= 4, 'Labels shows what’s tapped on every line')
            T.tap(*centre(pg, '#mapLabels')); T.tap(*centre(pg, '#mopts')); pg.wait_for_timeout(150)
            T.tap(*centre(pg, '#mkey')); pg.wait_for_timeout(150)
            ok(pg.locator('.mlegend').is_visible(), 'Key shows the legend')
            T.tap(*centre(pg, '#mkey')); pg.wait_for_timeout(150)
            mb = pg.locator('#map').bounding_box()
            # pinch around a point on empty map: the point under your fingers stays put
            pc = (mb['x'] + mb['width'] * 0.5, mb['y'] + mb['height'] * 0.82)
            w0 = pg.evaluate('([x, y]) => { const r = $("map").getBoundingClientRect(); return [(x - r.left - MV.x) / MV.k, (y - r.top - MV.y) / MV.k]; }', list(pc))
            T.pinch(pc, 80, 160); pg.wait_for_timeout(400)
            k1 = pg.evaluate('MV.k')
            w1 = pg.evaluate('([x, y]) => { const r = $("map").getBoundingClientRect(); return [(x - r.left - MV.x) / MV.k, (y - r.top - MV.y) / MV.k]; }', list(pc))
            ok(abs(k1 / k0 - 2) < 0.1 and abs(w1[0] - w0[0]) < 3 and abs(w1[1] - w0[1]) < 3, f'pinch zooms the map around your fingers ({k0 * 100:.0f}% → {k1 * 100:.0f}%, the point under them stays)')
            n = pg.evaluate(BURST_JS, ['#mapin', '#map', pc[0], pc[1]]); pg.wait_for_timeout(450)
            ok(1 <= n <= 2, f'the map is drawn once per screen refresh: {n} draw(s) for 40 finger moves in one moment')
            T.pinch(pc, 30, 330, lift=False); pg.wait_for_timeout(60)
            past = pg.evaluate('MV.k'); T.send('touchEnd', []); pg.wait_for_timeout(500)
            ok(past > 2.52 and abs(pg.evaluate('(RV||MV).k') - 2.5) < 0.01, f'pinching past 250% gives a little ({past * 100:.0f}%) and eases back to 250%')
            # fit, then one finger moves the map and a flick glides on
            pg.evaluate('fitFirst()'); pg.wait_for_timeout(450)
            x0 = pg.evaluate('MV.x')
            a = (mb['x'] + mb['width'] * 0.3, mb['y'] + mb['height'] * 0.85)
            T.drag(a, (a[0] + 120, a[1]), steps=6, ms=60); x1 = pg.evaluate('(RV||MV).x'); pg.wait_for_timeout(650)
            x2 = pg.evaluate('(RV||MV).x')
            ok(x1 - x0 > 90 and x2 - x1 > 20, f'one finger moves the map, and a flick keeps it gliding ({x1 - x0:.0f} pt, then {x2 - x1:.0f} more)')
            pg.evaluate('fitFirst()'); pg.wait_for_timeout(450)
            sid = pg.evaluate("[...document.querySelectorAll('.mcard')].map(c => [c.dataset.mid, c.getBoundingClientRect()]).find(([i, r]) => r.top > 110 && r.bottom < innerHeight - 120 && r.left > 0 && r.right < innerWidth)[0]")
            T.tap(*centre(pg, f'.mcard[data-mid="{sid}"]')); pg.wait_for_timeout(450)
            ok(pg.locator('#det.open').count() == 1 and pg.evaluate('S.open') == sid, f'one tap on a screen opens it ({sid})')
            T.drag((VW / 2, VH * 0.25), (VW / 2, VH * 0.75), ms=150); pg.wait_for_timeout(250)
            if pg.locator('#det.open').count(): T.tap(*centre(pg, '#dclose')); pg.wait_for_timeout(200)
            T.dbl(*centre(pg, f'.mcard[data-mid="{sid}"]')); pg.wait_for_timeout(120)
            mk = pg.evaluate('(RV||MV).k'); pg.wait_for_timeout(450)
            cb = pg.locator(f'.mcard[data-mid="{sid}"]').bounding_box()
            ok(abs(pg.evaluate('(RV||MV).k') - 1.1) < 0.01 and abs(cb['x'] + cb['width'] / 2 - (mb['x'] + mb['width'] / 2)) < 30 and pg.locator('#det.open').count() == 0,
               f'double-tap a screen zooms to it, animated (half-way {mk * 100:.0f}%)')
            pg.evaluate('fitFirst()'); pg.wait_for_timeout(450)
            before = dict(pg.evaluate(f'LAYOUT.pos["{sid}"] || autoLayout().pos["{sid}"]'))
            cc = centre(pg, f'.mcard[data-mid="{sid}"]')
            T.drag(cc, (cc[0] + 50, cc[1] + 40), steps=6, ms=60); pg.wait_for_timeout(700)
            ok(not pg.evaluate(f'!!LAYOUT.pos["{sid}"] && LAYOUT.pos["{sid}"].x !== {before["x"]}'), 'dragging a screen straight away moves the map, not the screen')
            pg.evaluate('fitFirst()'); pg.wait_for_timeout(450)
            cc = centre(pg, f'.mcard[data-mid="{sid}"]')
            T.drag(cc, (cc[0] + 50, cc[1] + 40), steps=6, ms=90, hold=480); pg.wait_for_timeout(300)
            moved = pg.evaluate(f'LAYOUT.pos["{sid}"]') or {}
            kk = pg.evaluate('MV.k')
            ok(moved and abs(moved['x'] - before['x'] - 50 / kk) < 4 and abs(moved['y'] - before['y'] - 40 / kk) < 4, 'hold a screen, then drag, to move it on the map')
            ok(not [x for x in errs if 'ERR_' not in x], 'no errors on the map' + (': ' + '; '.join(errs[:3]) if errs else ''))
            pg.context.close()

            # --- flows
            pg, errs, T = phone_page(b, v1.url, preset=store)
            T.tap(*centre(pg, '[data-view="flows"]')); pg.wait_for_selector('.fshot'); pg.wait_for_timeout(250)
            fs, fi = pg.locator('.fshot').bounding_box(), pg.locator('.finfo').bounding_box()
            ok(fs['x'] + fs['width'] <= fi['x'] + 1 and fi['y'] < fs['y'] + fs['height'], 'the step’s picture and its info sit side by side')
            nav = [pg.locator('.fnav button').nth(i).bounding_box() for i in range(pg.locator('.fnav button').count())]
            bar = pg.locator('.seg.views').bounding_box()
            ok(len(nav) == 3 and all(n['y'] >= 0 and n['y'] + n['height'] <= bar['y'] + 0.5 and n['height'] >= 43.5 for n in nav), 'Back · Next · Lightbox are on screen above the bottom bar, each at least 44 pt')
            ok(not pg.locator('#mchips').is_visible(), 'the filter row is hidden in Flows')
            T.drag((VW * 0.8, fs['y'] + fs['height'] / 2), (VW * 0.2, fs['y'] + fs['height'] / 2), ms=120); pg.wait_for_timeout(200)
            s1n = pg.evaluate('S.step')
            T.drag((VW * 0.2, fs['y'] + fs['height'] / 2), (VW * 0.8, fs['y'] + fs['height'] / 2), ms=120); pg.wait_for_timeout(200)
            ok((s1n, pg.evaluate('S.step')) == (1, 0), 'swipe left for the next step, right for the one before')
            ok(pg.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'nothing scrolls sideways in Flows')
            ok(not [x for x in errs if 'ERR_' not in x], 'no errors in Flows' + (': ' + '; '.join(errs[:3]) if errs else ''))
            pg.context.close()

            # --- the computer stays as it was, plus trackpad pinch in the zoom viewer and animated map buttons
            pg, errs = viewer_page(b, v1.url, preset=store)
            ok(pg.locator('#searchBtn').is_visible() is False and pg.locator('#q').is_visible() and pg.locator('header .seg.views').bounding_box()['y'] < 60, 'on a computer: the search field and the view switch stay at the top')
            pg.click('.card[data-id="TL-001"]'); pg.click('#dfull'); pg.wait_for_selector('#zoomv.open'); pg.wait_for_timeout(200)
            za = pg.locator('#zarea').bounding_box()
            pg.mouse.move(za['x'] + za['width'] / 2, za['y'] + 200)
            for _ in range(5): pg.evaluate("""() => document.getElementById('zarea').dispatchEvent(new WheelEvent('wheel', {deltaY:-20, ctrlKey:true, clientX:innerWidth/2, clientY:300, bubbles:true, cancelable:true}))""")
            pg.wait_for_timeout(100)
            ok(pg.evaluate(SCALE_JS, '#zin')['z'] > 1.5, 'a trackpad pinch zooms in the zoom viewer')
            pg.keyboard.press('Escape'); pg.keyboard.press('Escape')
            pg.click('[data-view="map"]'); pg.wait_for_timeout(400)
            k0 = pg.evaluate('(RV||MV).k'); pg.click('#zin'); pg.wait_for_timeout(110); km = pg.evaluate('(RV||MV).k'); pg.wait_for_timeout(400)
            ok(k0 < km < k0 * 1.25 - 0.005 and abs(pg.evaluate('(RV||MV).k') - min(2.5, k0 * 1.25)) < 0.01, 'the map’s + button zooms, animated')
            ok(not [x for x in errs if 'ERR_' not in x], 'no errors on a computer' + (': ' + '; '.join(errs[:3]) if errs else ''))
            pg.close()
            b.close()
    finally:
        v1.close(); v2.close()


# ---------- check my notes ----------
def t_notes(tmp, store):
    print('“Check my notes”: the Atlas’s notes and a prototype’s, together')
    atlas = [dict(v, id=k.split('/')[1]) for k, v in store.items() if k.startswith('notes/')]
    proto = json.load(open(os.path.join(TESTS, 'fixtures', 'prototype_notes.json'), encoding='utf-8'))
    pa, pp = os.path.join(tmp, 'atlas_notes.json'), os.path.join(tmp, 'proto_notes.json')
    json.dump(atlas, open(pa, 'w')); json.dump(proto, open(pp, 'w'))
    # also in the shape a store listing gives: one JSON object per line, with the note under "data"
    open(pp + '.lines', 'w').write('\n'.join(json.dumps({'id': n['id'], 'data': {k: v for k, v in n.items() if k != 'id'}}) for n in proto))
    rep = subprocess.run([sys.executable, '-m', 'atlas_kit.notes', pa, pp + '.lines'], cwd=KIT, capture_output=True, text=True).stdout
    sect = rep.split('## ')
    tl5 = next((x for x in sect if x.startswith('TL-005')), '')
    ok('· atlas (' in tl5 and '· prototype (' in tl5, 'the note made in the Atlas and the note made in a prototype come back together under TL-005')
    ok(rep.startswith('Notes · note format v1 · ') and 'Sources: atlas and prototype' in rep, 'in one report, with the shared header')
    la = [l for l in tl5.splitlines() if l.startswith('- ')]
    ok(len(la) == 2 and all('part save-button' in l for l in la), 'both name the same part, in the same line format')
    ok('move +0, -6' in tl5, 'the prototype’s change comes with it')
    heads = [x.split('\n')[0].split(' · ')[0] for x in sect[1:]]
    first = {}
    for n in atlas + proto: first[n['screen']] = min(first.get(n['screen'], n['created']), n['created'])
    ok(heads == sorted(first, key=first.get) and len(heads) == 2, 'grouped by screen, oldest open first (' + ', '.join(heads) + ')')
    keys = set(atlas[0]) & set(proto[0])
    need = {'v', 'n', 'source', 'app', 'screen', 'screenTitle', 'part', 'name', 'box', 'px', 'element', 'text', 'kind', 'status', 'from', 'created', 'updated'}
    ok(need <= keys, 'both records share every field of note format v1')


def main(argv):
    parts = argv or ['names', 'shared', 'site', 'state', 'compare', 'viewer', 'phone', 'notes']
    tmp = tempfile.mkdtemp(prefix='atlas-kit-test-')
    try:
        if 'names' in parts: t_names()
        if 'shared' in parts: t_shared()
        need_scans = {'site', 'state', 'compare', 'viewer', 'phone', 'notes'} & set(parts)
        if need_scans:
            p1 = t_site(tmp)
            s1 = t_state(tmp)
            s2 = t_compare(tmp, s1, p1) if {'compare', 'viewer', 'phone', 'notes'} & set(parts) else None
            if {'viewer', 'phone', 'notes'} & set(parts):
                store = t_viewer(tmp, s1, s2)
                if 'phone' in parts: t_phone(tmp, s1, s2, store)
                if 'notes' in parts: t_notes(tmp, store)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f'\n{PASSED} passed, {len(FAILS)} failed')
    for f in FAILS: print('  ✕ ' + f)
    sys.exit(1 if FAILS else 0)


if __name__ == '__main__':
    main(sys.argv[1:])
