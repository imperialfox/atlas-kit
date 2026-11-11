"""States by screen ID (kit 1.2): taps by part name, the no-browser coverage check and suggested states.

- A state is a starting screen that names its screen ID (`screen='AB-041'`): its set-up, and the real taps that reach
  the screen. After its steps the scan reads the screen's ID off the page; a state that lands somewhere else is Failed,
  "opened AB-0xx instead".
- A tap can name a part instead of a selector: `('tap', 'AB-001 › add-button')` looks for the part named add-button
  while AB-001 is showing (inside it when it's a sheet; anywhere on the page outside an open sheet when it's a screen, so
  bars and docks count). `('tap', '› tab-list')` is a shared part, wherever it shows (an open sheet first). Anything
  after the name narrows it, as CSS: `'AB-009 › song-row[data-k="{song}"]'`, plus `:has-text("River")` for what it says.
  When no element carries the name, the register's selector for that part is tried; an older name (a part's `was` in
  the register) still finds it.
- A screen that can't be held on screen with sample data gets a written reason instead (NO_STATE), shown as
  "No state · <reason>", never as missing.
"""
import json
import os
import re

from . import ids as IDS

ARROW = '›'
REF = re.compile(r'^\s*([^\s›\[\]"\'=:>]+)?\s*›\s*([a-z0-9][a-z0-9-]*)(.*)$', re.S)
HAS_TEXT = re.compile(r''':has-text\((["'])(.*?)\1\)''')


def is_ref(sel):
    return isinstance(sel, str) and ARROW in sel and bool(REF.match(sel))


def parse(sel):
    """'AB-009 › song-row[data-k="x"]:has-text("River")' → ('AB-009', 'song-row', '[data-k="x"]', 'River')."""
    m = REF.match(sel)
    if not m: return None
    screen, name, rest = m.group(1), m.group(2), m.group(3).strip()
    text = None
    t = HAS_TEXT.search(rest)
    if t:
        text = t.group(2); rest = (rest[:t.start()] + rest[t.end():]).strip()
    return (screen or None), name, rest, text


def described(sel):
    p = parse(sel)
    return ((p[0] + ' ' if p[0] else '') + ARROW + ' ' + p[1]) if p else sel


# ---------- the no-browser check, for an app's own tests ----------
def coverage(settings, register=None, app_dir=None):
    """Which Live register screens have no state and no written reason, without a browser.

    `settings` is a settings file's path (or an already loaded one). The register comes from `register` (a list of
    entries, or of IDs), else the settings' register(ctx) hook, else IDS['register_file']. Only starting screens that
    name their screen (screen='AB-041') count here: a starting screen without one is counted by a scan, which reads the
    screen's ID off the page.

    Returns {'missing': [IDs], 'reasons': {ID: reason}, 'states': {ID: [starting screen ids]},
             'unknown': [IDs named by a state or a reason that aren't in the register], 'register': n}.
    """
    from . import settings as SET
    st = settings if hasattr(settings, 'roots') else SET.load(settings)
    reg = _register(st, register, app_dir)
    live = [r['id'] for r in reg if IDS.live(r)]
    known = {r['id'] for r in reg}
    states = st.state_screens()
    reasons = {k: v for k, v in st.no_state.items() if k in known}
    return {'missing': [i for i in live if i not in states and i not in reasons],
            'reasons': reasons, 'states': states,
            'unknown': sorted({i for i in list(states) + list(st.no_state) if i not in known}),
            'register': len(reg)}


def _register(st, register, app_dir):
    if register is not None:
        return IDS.normalize([r if isinstance(r, dict) else {'id': r} for r in register])
    ctx = {'app': os.path.abspath(app_dir or os.path.join(st.dir, getattr(st.mod, 'APP_DIR', '.')))}
    cfg = st.ids or {}
    if st.has('register') or cfg.get('register_file'):
        reg = IDS.read_register(st, None, ctx)
        if reg: return reg
    raise ValueError('coverage(): the register can’t be read without a browser here. Pass it in (register=[...]), '
                     'or give the settings a register(ctx) hook or IDS["register_file"].')


# ---------- suggested states, written by a full scan ----------
def suggestion_steps(parent_steps, parent_ids, link, ctx_vars):
    """The steps to a screen found by tapping: its parent's steps, then the button, by its part name where it has one."""
    sel = link['selector']
    showing = None
    if parent_ids:
        showing = parent_ids.get('sheet') if parent_ids.get('sheetOpen') else parent_ids.get('screen')
    if link.get('part') and showing:
        extra = ''.join(re.findall(r'\[data-[kv]="[^"]*"\]', sel))
        step = ('tap', showing + ' ' + ARROW + ' ' + link['part'] + extra)
    else:
        step = ('force' if link.get('forced') else 'tap', sel)
    out = list(parent_steps) + [step]
    return [unfill(s, ctx_vars) for s in out]


def unfill(step, ctx_vars):
    """Values the settings' prepare() made (an id that changes each run) go back to their {name}."""
    if not ctx_vars or not isinstance(step[1], str): return tuple(step)
    v = step[1]
    for k, x in ctx_vars.items():
        x = str(x)
        if len(x) >= 4: v = v.replace(x, '{' + k + '}')
    return (step[0], v) + tuple(step[2:])


def write_suggestions(path, atlas, items):
    """suggested_states.py: one dict per screen found by tapping that has no state yet, ready to copy into ROOTS."""
    sc = atlas['scan']
    lines = ['"""Suggested states from the Atlas kit’s full scan of ' + sc['at'] + ' (' + str(sc.get('version') or '?') +
             ', scan ' + sc['id'] + ').', '',
             'Screens the scan found by tapping that have no state yet, each with the taps that reached it: by part name',
             'where the part has one, by selector where not. A draft: copy what you want into the settings’ starting screens',
             '(ROOTS), give each a better title if needed, and check it opens its screen. Values that change each run go back',
             'to their {name} where the settings’ prepare() named them.', '"""', '', 'SUGGESTED_STATES = [']
    for it in items:
        bits = []
        if it.get('screen'): bits.append('screen=' + repr(it['screen']))
        bits.append('id=' + repr(it['id']))
        if it.get('title'): bits.append('title=' + repr(it['title']))
        if it.get('key') and not it.get('screen'): bits.append('key=' + repr(it['key']))
        bits.append('setup=' + repr(list(it.get('setup') or [])))
        steps = '[' + ', '.join('(' + ', '.join(repr(x) for x in s) + ')' for s in it['steps']) + ']'
        lines.append('    dict(' + ', '.join(bits) + ',')
        lines.append('         steps=' + steps + '),')
    lines.append(']')
    open(path, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    return path


def js_args(st, register_parts, sel, fill):
    """What the page needs to find a part: its name, the screen, what narrows it, and the register's selector."""
    screen, name, css, text = parse(sel)
    screen = fill(screen) if screen else None
    info = (register_parts or {}).get(screen or '', {})
    was = info.get('was') or {}
    renamed = None
    if name in was: renamed, name = name, was[name]
    rsel = (info.get('sel') or {}).get(name)
    ids = st.ids or {}
    return renamed, {'attr': ids.get('screen_attr', 'data-screen'), 'part': ids.get('part_attr', 'data-name'),
                     'sheet': st.sheet, 'screen': screen, 'name': name, 'css': fill(css) if css else '',
                     'text': fill(text) if text else None, 'sel': rsel}


def dumps(x):
    return json.dumps(x, ensure_ascii=False)
