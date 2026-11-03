"""Atlas settings for a made-up app (the kit's tests): screens without addresses, with screen IDs.

A worked example of every setting an app of screens can give. See README.md › Adding an app.
"""
import json
import re

APP = {'name': 'Tidy list', 'url': 'https://example.com/tidy-list/'}
KIND = 'screens'
VIEWPORT = {'w': 402, 'h': 874, 'name': 'iPhone'}
FIXED_TIME = '2026-11-02T10:00:00+00:00'
TIMEZONE = 'Europe/London'
DATA = 'sample data: three list items'
AREAS = ['Home', 'List', 'Settings']
DOC_FILES = ['README.md']
CHANGELOG = 'CHANGELOG.md'
QUEUE = {'file': 'IDEAS.md', 'section': 'Not scheduled'}

SAMPLE = ['Oat milk', 'Batteries', 'Birthday card']


def load(page, setup, ctx):
    """Open the app with sample data (never real data), then any set-up the starting screen asks for."""
    page.goto(ctx['url'] + 'index.html')
    page.evaluate('items=>localStorage.setItem("tidyItems", JSON.stringify(items))', [] if 'empty' in setup else SAMPLE)
    page.reload()
    page.wait_for_function('()=>document.getElementById("app").children.length>0')


# Where the app is: its tab or screen, and its sheet. Keys look like 'home', 'about', 'list|menu'.
WHERE = '(U.view||U.tab)+(U.sheet?"|"+U.sheet:"")'
SNAPSHOT = '()=>__snap()'
RESET = '()=>__reset()'
SHEET = '.scrim .sheet'
ROOT = '#app'
BAR = '.tabbar'


def keys_of(key):
    return key.split('|')


def area_of(key, under=None):
    return {'home': 'Home', 'stats': 'Home', 'list': 'List', 'settings': 'Settings', 'prefs': 'Settings', 'about': 'Settings',
            'add': 'Home', 'menu': 'List'}.get(key.split('|')[-1], under)


def kind_of(family, sheet_open):
    if sheet_open: return 'Sheet'
    return {'about': 'Sub-page', 'stats': 'Screen'}.get(family, 'Tab')


ROOTS = [
    dict(id='home', title='Home', area='Home', kind='Tab', key='home', steps=[], setup=[]),
    dict(id='home-empty', title='Home · first launch', state='first launch', area='Home', kind='Tab', key='home', steps=[], setup=['empty'], state_of='home'),
    dict(id='home-dark', title='Home · dark', state='dark', area='Home', kind='Tab', key='home', steps=[], setup=['dark'], state_of='home'),
    dict(id='list', title='List', area='List', kind='Tab', key='list', steps=[('tap', '[data-name="tab-list"]')], setup=[]),
    dict(id='settings', title='Settings', area='Settings', kind='Tab', steps=[('tap', '[data-name="tab-settings"]')], setup=[]),
    # the item menu opens with a hold, which the scan can't do: a set-up shortcut to the app's own openMenu()
    dict(id='item-menu', title='Item menu', area='List', kind='Sheet', key='list|menu',
         steps=[('tap', '[data-name="tab-list"]'), ('js', '()=>openMenu(0)')], setup=[]),
]


def inventory(app_dir):
    """Every screen and sheet the code can set, read from the code with no browser."""
    src = open(app_dir + '/index.html', encoding='utf-8').read()
    v2 = 'APP_VERSION = 2' in open(app_dir + '/version.js', encoding='utf-8').read()
    out = {t: {'kind': 'Tab', 'name': t, 'where': 'index.html › tab bar'} for t in ('home', 'list', 'prefs' if v2 else 'settings')}
    for kind, rx in [('Screen', r"U\.view\s*=\s*'(\w+)'"), ('Sheet', r"U\.sheet\s*=\s*'(\w+)'")]:
        for m in re.findall(rx, src): out.setdefault(m, {'kind': kind, 'name': m, 'where': 'index.html'})
    return out


def family(key):
    return key.split('|')[-1] if '|' in key else key


TITLES = {'add': 'Add an item', 'about': 'About'}
DOCS = {'Home': [('README.md', 'Home')], 'List': [('README.md', 'List')], 'Settings': [('README.md', 'Settings')]}

# Captions: one line in plain words per screen (by screen ID). A screen without one shows nothing.
CAPTIONS = {
    'TL-001': 'Where the app opens: how many things are on the list, and a button to add one.',
    'TL-005': 'Type what it is, then Save. It lands on the List.',
}

# Walk-throughs, step by step. Each step: what to do (tap, fill, a set-up shortcut, wait), then what's captured.
FLOWS = [
    dict(id='F-01', title='Add an item', start='home', start_moment='fresh',
         steps=[dict(tap='[data-name="add-button"]', moment='empty sheet'),
                dict(fill={'[data-name="title-field"]': 'Tea bags'}, label='Type “Tea bags”', moment='filled in'),
                dict(tap='[data-name="save-button"]', moment='saved')]),
]

# Doors the scan can't test (a swipe, a hold, a timed sheet, a file picker), written by hand.
DOORS = [
    dict(**{'from': 'TL-002', 'to': 'TL-006'}, how='Hold an item for about half a second', kind='Hold'),
]

# Screen IDs: where the register is, and how screens and parts are marked on the page.
IDS = {'register': 'window.SCREENS', 'screen_attr': 'data-screen', 'part_attr': 'data-name', 'prefix': 'TL-', 'digits': 3}
