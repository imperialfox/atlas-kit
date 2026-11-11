"""Atlas settings for the made-up app, with a state for every screen (kit 1.2).

The same app and settings as atlas_settings.py, but every starting screen is a state: the screen ID it must open
(screen=...), its set-up, and the real taps that reach it, by part name. A screen that can't be held on screen gets a
written reason instead (NO_STATE). See README.md › States.
"""
from atlas_settings import *          # noqa: F401,F403  the app's own settings: load, WHERE, RESET, IDS and the rest
from atlas_settings import load, inventory, keys_of, area_of, kind_of, family  # noqa: F401  (hooks, named for clarity)

ROOTS = [
    dict(screen='TL-001', steps=[], setup=[]),
    dict(screen='TL-001', state='first launch', steps=[], setup=['empty']),
    dict(screen='TL-001', state='dark', steps=[], setup=['dark']),
    dict(screen='TL-002', steps=[('tap', '› tab-list')], setup=[]),
    dict(screen='TL-003', steps=[('tap', '› tab-settings')], setup=[]),
    dict(screen='TL-004', steps=[('tap', '› tab-settings'), ('tap', 'TL-003 › about-row')], setup=[]),
    dict(screen='TL-005', steps=[('tap', 'TL-001 › add-button')], setup=[]),
    # the item menu opens with a hold, which the scan can't do: a set-up shortcut to the app's own openMenu()
    dict(screen='TL-006', steps=[('tap', '› tab-list'), ('js', '()=>openMenu(0)')], setup=[]),
]

# Screens that can't be held on screen with sample data: one plain line each, shown as "No state · <reason>".
NO_STATE = {
    'TL-007': 'Not built yet: the register lists it ahead of the screen',
}

# The flow starts from the plain state of TL-001, and taps by part name.
FLOWS = [
    dict(id='F-01', title='Add an item', start='TL-001', start_moment='fresh',
         steps=[dict(tap='TL-001 › add-button', moment='empty sheet'),
                dict(fill={'TL-005 › title-field': 'Tea bags'}, label='Type “Tea bags”', moment='filled in'),
                dict(tap='TL-005 › save-button', moment='saved')]),
]
