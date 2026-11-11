"""Atlas kit: every screen of an app or site as saved screenshots, how they link, what changed, and notes on them.

The kit belongs to no app. An app uses it through its own settings file (see README.md › Adding an app).
"""
VERSION = '1.2.0'


def coverage(settings, register=None, app_dir=None):
    """The no-browser check for an app's tests: Live register screens with no state and no written reason (1.2).
    See atlas_kit/states.py › coverage."""
    from .states import coverage as check
    return check(settings, register, app_dir)
