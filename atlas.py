"""Atlas kit · the command. Scans an app or site from its settings file, then shows every screen in the viewer.

    python3 atlas.py --settings path/to/atlas_settings.py             scan, then open the Atlas in your browser
    python3 atlas.py --settings … --view                             open the last scan again, without scanning
    python3 atlas.py --settings … --no-open                          scan only (what Claude runs before updating an Atlas page)
    python3 atlas.py --settings … --quick                            capture the starting screens without tapping their buttons
    python3 atlas.py --settings … --pictures                         every state's picture, quickly; buttons from the last full scan
    python3 atlas.py --settings … --workers 4                        how many browsers scan side by side (default: processors, up to 6)
    python3 atlas.py --settings … --proposed proposed.json           also capture prototypes listed against real screens

Needs Playwright (pip install playwright, then python3 -m playwright install chromium) and Pillow.
Scans go in <settings folder>/data/scans/<date-time>/ (atlas.json, shots/ and the viewer as index.html) unless
--data says otherwise. Every scan is kept, so the next one can be compared with it. Never commit data/: screenshots
and notes stay out of public repos.
"""
import argparse
import datetime as dt
import functools
import glob
import json
import os
import shutil
import sys
import threading
import webbrowser
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from atlas_kit import VERSION, settings as SET  # noqa: E402


def scans(folder):
    """Finished scans, oldest first."""
    return sorted(d for d in glob.glob(os.path.join(folder, '*')) if os.path.exists(os.path.join(d, 'atlas.json')))


def last_full(found):
    """The latest full scan (buttons tapped), for a pictures-only scan's links. Scans before 1.2 count when they have links."""
    for d in reversed(found):
        try: a = json.load(open(os.path.join(d, 'atlas.json'), encoding='utf-8'))
        except Exception: continue
        m = a['scan'].get('mode')
        if m == 'full' or (m is None and any(s.get('links') for s in a.get('screens', []))): return d
    return None


def put_viewer(folder):
    shutil.copy(os.path.join(HERE, 'viewer.html'), os.path.join(folder, 'index.html'))


def serve(folder, open_browser=True):
    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self, *a): pass
    srv = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=folder))
    url = f'http://localhost:{srv.server_address[1]}/'
    print(f'The Atlas is at {url}  (Ctrl+C to stop)')
    if open_browser: threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try: srv.serve_forever()
    except KeyboardInterrupt: print('\nStopped.')


def main(argv=None):
    ap = argparse.ArgumentParser(description=f'Atlas kit {VERSION}: scan an app or site and show every screen.')
    ap.add_argument('--settings', required=True, help='the app’s settings file (see README › Adding an app)')
    ap.add_argument('--app', help='the app or site folder (default: the settings’ APP_DIR, else the settings’ folder)')
    ap.add_argument('--data', help='where scans are kept (default: data/scans beside the settings file)')
    ap.add_argument('--view', action='store_true', help='open the last scan without scanning')
    ap.add_argument('--no-open', action='store_true', help='scan only; don’t start the viewer')
    ap.add_argument('--quick', action='store_true', help='don’t tap buttons (only the starting screens are captured)')
    ap.add_argument('--pictures', action='store_true', help='every state’s picture, no button tests; links from the latest full scan')
    ap.add_argument('--fresh-pages', action='store_true', help='a fresh page for every state (no page reuse)')
    ap.add_argument('--workers', type=int, default=min(6, os.cpu_count() or 2))
    ap.add_argument('--only', help='comma-separated starting screens (for checking a few)')
    ap.add_argument('--out', help='where to write this scan (default: a new folder under the data folder)')
    ap.add_argument('--proposed', help='a JSON list of prototypes to show beside the real screens they change')
    ap.add_argument('--baselines', type=int, default=12, help='how many earlier scans to tag NEW and CHANGED against')
    a = ap.parse_args(argv)

    st = SET.load(a.settings)
    app_dir = os.path.abspath(a.app or os.path.join(st.dir, getattr(st.mod, 'APP_DIR', '.')))
    data = os.path.abspath(a.data or os.path.join(st.dir, 'data', 'scans'))
    done = scans(data)
    if a.view:
        if not done: sys.exit('No scans yet. Run without --view first.')
        put_viewer(done[-1]); serve(done[-1]); return

    from atlas_kit import engine
    sid = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out = os.path.abspath(a.out) if a.out else os.path.join(data, sid)
    os.makedirs(out, exist_ok=True)
    prop = a.proposed or (os.path.join(st.dir, 'proposed.json') if os.path.exists(os.path.join(st.dir, 'proposed.json')) else None)
    proposed = json.load(open(prop, encoding='utf-8')) if prop else list(getattr(st.mod, 'PROPOSED', []))
    if prop:
        for p in proposed:
            if p.get('file') and not os.path.isabs(p['file']): p['file'] = os.path.join(os.path.dirname(os.path.abspath(prop)), p['file'])
    prev = [d for d in done if os.path.abspath(d) != out]
    print(f'Atlas kit {VERSION} · scanning {app_dir} into {out}')
    engine.scan(a.settings, app_dir, out, workers=a.workers, taps=not a.quick, only=set(a.only.split(',')) if a.only else None,
                prev=prev[-1] if prev else None, baselines=prev[-a.baselines:] if a.baselines else [], proposed=proposed, scan_id=sid,
                pictures=a.pictures, full=last_full(prev) if a.pictures else None, reuse=False if a.fresh_pages else None)
    put_viewer(out)
    if not a.no_open: serve(out)


if __name__ == '__main__':
    main()
