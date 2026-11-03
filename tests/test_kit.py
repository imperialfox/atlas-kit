"""Tests for the Atlas kit: the scanner, the viewer and "check my notes", on two made-up apps.

    python3 tests/test_kit.py                 everything (about 2 minutes)
    python3 tests/test_kit.py names shared    only some parts: names, shared, site, state, compare, viewer, notes

- tests/apps/site: a made-up website (pages with addresses).
- tests/apps/state: a made-up app of screens without addresses, with screen IDs, a flow, a hand-written door and
  captions; its "version 2" (made in a temporary copy) renames a code key, adds a screen with no ID, lists a screen
  the scan can't find and changes how Home looks.
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
    parts = argv or ['names', 'shared', 'site', 'state', 'compare', 'viewer', 'notes']
    tmp = tempfile.mkdtemp(prefix='atlas-kit-test-')
    try:
        if 'names' in parts: t_names()
        if 'shared' in parts: t_shared()
        need_scans = {'site', 'state', 'compare', 'viewer', 'notes'} & set(parts)
        if need_scans:
            p1 = t_site(tmp)
            s1 = t_state(tmp)
            s2 = t_compare(tmp, s1, p1) if {'compare', 'viewer', 'notes'} & set(parts) else None
            if {'viewer', 'notes'} & set(parts):
                store = t_viewer(tmp, s1, s2)
                if 'notes' in parts: t_notes(tmp, store)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f'\n{PASSED} passed, {len(FAILS)} failed')
    for f in FAILS: print('  ✕ ' + f)
    sys.exit(1 if FAILS else 0)


if __name__ == '__main__':
    main(sys.argv[1:])
