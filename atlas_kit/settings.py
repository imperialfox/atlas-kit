"""Reading an app's settings file, with the kit's defaults for everything it leaves out.

An app's settings file is a plain Python file (README.md › Adding an app explains every name). Only a few names are
needed; everything else has a default here. Nothing in this file knows about any particular app.
"""
import datetime as dt
import importlib.util
import os
import re
import sys

KINDS = ('screens', 'pages')

# What the scan taps, if the settings don't say: ordinary buttons and links.
DEFAULT_BUTTONS = 'button, a[href], [role=button], [data-a], summary'
# An open sheet or dialog, if the settings don't say.
DEFAULT_SHEET = 'dialog[open], [role=dialog]:not([hidden]), [aria-modal=true]:not([hidden])'
DEFAULT_SKIP = [
    (r'(?i)\b(delete|remove|clear|reset|erase|wipe|discard)\b', 'Not tested: deletes or clears something'),
    (r'(?i)\b(import|upload|choose file|attach)\b', 'Not tested: needs a file'),
    (r'(?i)\b(export|download|share|print)\b', 'Not tested: saves, shares or prints a file'),
    (r'(?i)\b(record|microphone|camera)\b', 'Not tested: needs the microphone or camera'),
    (r'(?i)\b(log ?out|sign ?out|pay|buy|checkout|subscribe)\b', 'Not tested: signs out, pays or subscribes'),
]


def load(path):
    """Load a settings file by its path and wrap it with the kit's defaults."""
    path = os.path.abspath(path)
    name = 'atlas_settings_' + re.sub(r'\W', '_', path)
    if name in sys.modules:
        return Settings(sys.modules[name], path)
    sys.path.insert(0, os.path.dirname(path))
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return Settings(mod, path)


class Settings:
    """The app's settings with defaults. Attribute names match the settings file's names in lower case."""

    def __init__(self, mod, path):
        self.mod, self.path, self.dir = mod, path, os.path.dirname(path)
        g = lambda n, d=None: getattr(mod, n, d)
        self.app = dict(g('APP', {}))
        if not self.app.get('name'):
            raise SystemExit(f'{path}: APP needs a name, e.g. APP = {{"name": "My app"}}')
        self.kind = g('KIND', 'screens')
        if self.kind not in KINDS:
            raise SystemExit(f'{path}: KIND must be one of {KINDS}, not {self.kind!r}')
        self.viewport = dict(g('VIEWPORT', {'w': 402, 'h': 874, 'name': 'iPhone'}))
        self.viewport.setdefault('name', f"{self.viewport['w']} × {self.viewport['h']}")
        t = g('FIXED_TIME', '2026-01-01T10:00:00+00:00')
        self.fixed_time = t if isinstance(t, dt.datetime) else dt.datetime.fromisoformat(t)
        self.timezone = g('TIMEZONE', 'UTC')
        self.locale = g('LOCALE', 'en-GB')
        self.data = g('DATA', 'sample data')
        self.scale = g('SCALE', 2)
        self.user_agent = g('USER_AGENT')
        self.init_script = g('INIT_SCRIPT')
        self.areas = list(g('AREAS', []))
        self.titles = dict(g('TITLES', {}))
        self.title_prefix = dict(g('TITLE_PREFIX', {}))
        self.captions = dict(g('CAPTIONS', {}))
        self.flows = list(g('FLOWS', []))
        self.doors = list(g('DOORS', []))
        self.ids = g('IDS')
        self.queue = g('QUEUE')
        self.skip = list(g('SKIP', DEFAULT_SKIP))
        self.safe_actions = set(g('SAFE_ACTIONS', set()))
        self.buttons = g('BUTTONS', DEFAULT_BUTTONS)
        self.sheet = g('SHEET', DEFAULT_SHEET)
        self.root = g('ROOT', 'body')
        self.title_js = g('TITLE_JS')
        self.reset_js = g('RESET')
        self.snapshot_js = g('SNAPSHOT')
        self.where_js = g('WHERE')
        self.tap_wait = g('TAP_WAIT', 160)
        self.max_buttons = g('MAX_BUTTONS', 40)
        self.max_passes = g('MAX_PASSES', 5)
        self.max_pages = g('MAX_PAGES', 200)
        self.doc_files = list(g('DOC_FILES', ['README.md']))
        self.docs_url = g('DOCS_URL', '')
        self.changelog_file = g('CHANGELOG', 'CHANGELOG.md')
        self.change_id = g('CHANGE_ID', r'\(([A-Z]+\d+)\)')
        self.words = dict(g('WORDS', {}))
        self.docs_table = dict(g('DOCS', {}))
        # pages: where the site starts, and its folder (served locally) or address
        self.start = g('START', 'index.html')
        self.site = g('SITE')
        self.roots = [dict(r) for r in g('ROOTS', [])]
        if self.kind == 'screens' and not self.roots:
            self.roots = [dict(id='start', title=None, steps=[], setup=[])]
        if self.kind == 'screens' and not hasattr(mod, 'load'):
            raise SystemExit(f'{path}: an app of screens without addresses needs a load(page, setup, ctx) function')

    # ---------- hooks, each with a default ----------
    def call(self, name, *a, default=None):
        f = getattr(self.mod, name, None)
        return f(*a) if callable(f) else default

    def has(self, name):
        return callable(getattr(self.mod, name, None))

    def prepare(self, app_dir):
        return self.call('prepare', app_dir, default={})

    def family(self, key):
        """Screens with the same layout and other content (other exercises, other posts) share a family."""
        return self.call('family', key, default=key)

    def keys_of(self, key):
        """The entries of the code's list a captured screen accounts for."""
        return self.call('keys_of', key, default=[self.family(key)])

    def area_of(self, key, under=None):
        a = self.call('area_of', key, under, default=None)
        if not a and self.kind == 'pages' and key is not None:
            k = key.split('?')[0]
            top = k.strip('/').split('/')
            a = top[0].replace('-', ' ').capitalize() if top[0] and (len(top) > 1 or k.endswith('/')) else 'Home'
        return a or under or (self.areas[0] if self.areas else 'Screens')

    def describe(self, key):
        return self.call('describe', key, default=key)

    def kind_of(self, family, sheet_open):
        k = self.call('kind_of', family, sheet_open, default=None)
        if k: return k
        if self.kind == 'pages': return 'Page'
        return 'Sheet' if sheet_open else 'Screen'

    def version(self, app_dir, log):
        v = self.call('version', app_dir, default=None)
        return v or (log[0]['version'] if log else '')

    def inventory(self, app_dir):
        return self.call('inventory', app_dir, default={})

    def docs(self, key, family, area):
        """(file, section label) pairs, most specific first."""
        if self.has('docs'):
            return self.call('docs', family, area) or []
        return list(self.docs_table.get(key) or self.docs_table.get(family) or self.docs_table.get(area) or [])

    def skip_reason(self, action, value, label):
        if action in self.safe_actions: return None
        for rx, why in self.skip:
            for s in (action, value, label):
                if s and re.search(rx, s): return why
        return None
