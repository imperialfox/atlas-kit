# Atlas kit

![version](https://img.shields.io/badge/version-1.0.0-007aff)

**Current version:** 1.0.0 · 3 Nov 2026 · [changelog](CHANGELOG.md)

*See the real app: every screen as a saved screenshot, how they link, what changed, and notes on real screens that Claude can read.*

One Atlas for any app or website. The kit scans the app in a throwaway browser with sample data, saves every screen it can reach, taps every button to see where it goes, and shows it all in one page: a Lightbox of screens, a Map of how they link, step-by-step Flows, and notes you leave on any part of a screen. It belongs to no app: each app uses it through a small settings file of its own.

**Works with the Prototype kit** (`imperialfox/prototype-kit`): the Atlas shows the real app; a prototype tries a change. Both write notes in the same format ([SHARED.md](SHARED.md), identical in both repos), and a prototype listed in the Atlas shows beside the real screen it changes.

## What's in it

- **Lightbox:** every screen as a card, grouped by area, with its ID, a one-line caption, and what changed. Filters for area, status, kind, and **tags since a chosen version** (NEW or CHANGED).
- **Details:** the screen, where each button goes (seen working, changes this screen, not tested with the reason, broken), where it comes from, which flows it's in, the docs that explain it, the last changelog headline that names it, and its named parts.
- **Map:** every screen placed by area, with lines for the links the scan saw working, dotted lines for **doors the scan can't test** (written by hand), and a **Labels** switch that shows what's tapped on every line at once. Drag cards to arrange them; the layout is kept.
- **Flows:** walk-throughs named in the settings, stepped through like a slideshow, with the button to tap ringed and named between steps. One screen can appear at several moments (fresh, filled in, finished).
- **Notes:** tap a part of a screen (or drag a box), write what's wrong, save. Notes keep the part's name, so they follow it after a redesign. In any Claude chat, say **"check my notes"**.
- **Changes since the last scan:** new, gone, looks different (with a before/now wipe), links changed, failed this time, and the versions released in between.
- **Screen IDs:** when the app keeps a register of its screens, IDs are the keys for everything (screens, notes, flows, captions, tags, the map layout), so they survive renames. A screen with no ID yet is flagged with a suggested number.
- **Proposed screens:** a prototype listed against a real screen shows beside it, with the same wipe.

The screenshots are saved, not live. The page says so wherever it matters.

Try it: [Atlas kit demo](https://claude.ai/artifact/G6mPQt1qo3iUDaoDMkqFEu), a scan of the made-up app in `tests/apps/state` at its version 2, compared with version 1, with a prototype listed against one screen. The kit itself has no app's screens, names or colours.

## Two kinds of app

| Kind | What it is | What the settings give |
|---|---|---|
| `pages` | An ordinary website: pages with addresses | The start page, screen size, and anything not to tap. Pages are found by following links. |
| `screens` | An app whose screens have no addresses (one page that draws different screens) | How to open it with sample data, how to tell which screen is showing, how to put it back after a tap, and the starting screens. Everything else is found by tapping. |

## Use

Needs Python 3.9 or later, Playwright and Pillow, once:

```
pip install playwright pillow
python3 -m playwright install chromium
```

Then, from this folder (or with the path to `atlas.py`):

```
python3 atlas.py --settings path/to/atlas_settings.py             scan, then open the Atlas in your browser
python3 atlas.py --settings … --view                             open the last scan again, without scanning
python3 atlas.py --settings … --no-open                          scan only
python3 atlas.py --settings … --quick                            the starting screens only, no tapping (fast)
python3 atlas.py --settings … --proposed proposed.json           also capture prototypes listed against real screens
```

Scans are kept in `data/scans/<date-time>/` beside the settings file (`atlas.json`, `shots/` and the viewer as `index.html`), so each scan can be compared with the ones before it. **Never commit `data/`:** screenshots and notes stay out of public repos.

From a Claude chat, say **"rescan the Atlas"**: Claude runs the scan in its own workspace and updates the private Atlas page on claude.ai.

## Adding an app

1. **Make a settings file** in the app's own repo (for example `tools/atlas/atlas_settings.py`). Start from one of the worked examples in `tests/apps/`: `site/atlas_settings.py` for a website, `state/atlas_settings.py` for an app of screens.
2. **Give it the basics:** `APP` (name, and the live address), `KIND`, `VIEWPORT`, and `APP_DIR` (the app's folder, from the settings file).
3. **For an app of screens,** write `load(page, setup, ctx)`: open `ctx['url'] + 'index.html'` and fill it with sample data, never real data. Then `WHERE` (how to tell which screen is showing) and, if you can, `SNAPSHOT` and `RESET` (put it back after a tap, quicker than starting again).
4. **List the starting screens** in `ROOTS`: the tabs, through their real buttons, plus any states worth seeing (first launch, dark).
5. **Run a scan** and look. Anything the scan couldn't reach shows as "Not captured yet"; add a starting screen for it, or a hand-written door if a tap can't reach it.
6. **Add the extras when you want them:** captions, flows, doors, screen IDs, docs links (below).
7. **Copy the kit into the app** (a pinned copy, with its version noted in the app's own README), and add `data/` to the app's `.gitignore`.
8. **Publish the Atlas page on claude.ai** with the page's store declared, so notes are kept where Claude can read them: everyone signed in who can open it reads, only you write (`rules: [{ path: '', read: 'interact', write: 'admin' }]`).

## Settings

Only `APP` is always needed (and `load` for an app of screens). Everything else has a default.

| Name | What it is | Default |
|---|---|---|
| `APP` | `{'name': …, 'url': …}`: the app's name and live address | (needed) |
| `KIND` | `'pages'` or `'screens'` | `'screens'` |
| `APP_DIR` | The app's folder, from the settings file | the settings file's folder |
| `VIEWPORT` | `{'w': 402, 'h': 874, 'name': 'iPhone'}` (SHARED.md's devices) | iPhone |
| `FIXED_TIME`, `TIMEZONE`, `LOCALE` | The frozen clock, so dates never show up as changes | 1 Jan 2026 10:00 UTC |
| `DATA` | A few words on the sample data, shown in the viewer | `'sample data'` |
| `AREAS` | The areas, in order | from the scan |
| `START`, `SITE` | Pages: the first page, and the site's folder (or an `https://` address) | `index.html`, `APP_DIR` |
| `MAX_PAGES` | Pages: the most pages to follow | 200 |
| `load(page, setup, ctx)` | Screens: open the app with sample data, then the set-up a starting screen asks for (`'empty'`, `'dark'` and your own) | (needed) |
| `prepare(ctx)` | Once per scan, before anything: work out values the steps need; return a dict merged into `ctx` (`ctx['vars']` fills `{name}` in selectors) | none |
| `WHERE` | Screens: JavaScript giving the screen showing (a string, or anything `key(raw)` turns into one) | the address |
| `SNAPSHOT`, `RESET` | Screens: JavaScript to keep the state after set-up, and to go back to it before every tap | start a fresh copy |
| `ROOTS` | Starting screens: `id`, `title`, `area`, `kind`, `key`, `steps`, `setup`, and for a state `state_of` and `state` | the app as it opens |
| `SHEET`, `ROOT`, `BAR` | Where an open sheet, the screen and the tab bar are | common dialog selectors, `body`, none |
| `BUTTONS` | What counts as a button | buttons, links, `[role=button]`, `[data-a]` |
| `SKIP` | `(pattern, reason)` pairs for buttons never tapped | delete, clear, file, share, record, pay, sign out |
| `family`, `keys_of`, `area_of`, `kind_of`, `describe`, `link_kind` | Functions that name and group what the scan finds | sensible defaults |
| `inventory(app_dir)` | Every screen the code can show, so anything the scan missed is listed (`atlas_kit/code.py` helps read JavaScript) | pages: every `.html` file |
| `TITLES`, `TITLE_PREFIX` | Names for screens, by key | the screen's own heading |
| `DOC_FILES`, `DOCS_URL`, `DOCS` or `docs(key, area)` | Which doc sections explain which screen | `README.md` |
| `CHANGELOG`, `CHANGE_ID`, `WORDS` | The changelog, the pattern of its change IDs, words to find a screen's latest headline | `CHANGELOG.md`, `(Q12)`-style |
| `QUEUE` | Where "Copy as queue ideas" sends notes: `{'file': …, 'section': …}` | the app's ideas list |
| `CAPTIONS` | One plain line per screen, by ID or key | none (nothing is made up) |
| `FLOWS` | Walk-throughs (below) | none |
| `DOORS` | Doors the scan can't test (below) | none |
| `IDS` | Screen IDs (below) | none: code-based keys |

**Steps** (in `ROOTS` and flows): `('tap', selector)` taps a real button; `('js', code)` runs a shortcut, for set-up only; `('wait', ms)`; pages also have `('goto', address)`.

### Flows

```python
FLOWS = [
    dict(id='F-01', title='Add an item', start='home', start_moment='fresh',
         steps=[dict(tap='[data-name="add-button"]', moment='empty sheet'),
                dict(fill={'[data-name="title-field"]': 'Tea bags'}, label='Type “Tea bags”', moment='filled in'),
                dict(tap='[data-name="save-button"]', moment='saved')]),
]
```

`start` is a starting screen's id (or a list of steps). Each step can `tap`, `fill` (sample text only), run `js` and `wait`, then the scan captures what's showing; `capture=False` skips the picture. `label` is what shows between steps (the tapped button's own name if left out), `moment` names the state, and `caption` adds a line.

### Doors the scan can't test

```python
DOORS = [dict(**{'from': 'AB-002', 'to': 'AB-006'}, how='Hold an item for about half a second', kind='Hold')]
```

A swipe, a hold, a timed sheet, a file picker: drawn as dotted lines marked "Not tested by the scan" and listed in details. `from` and `to` can be a screen's ID, id or code key.

### Screen IDs

```python
IDS = {'register': 'window.SCREENS', 'screen_attr': 'data-screen', 'part_attr': 'data-name', 'prefix': 'AB-', 'digits': 3}
```

- **The register** lists each screen once: `id`, `name`, `area`, `kind`, `key` (its place in the code), `aliases` (older keys), `docs`, `status` (`Live` or `Retired in …`) and `parts`. It's read from the running page (`register`), a JSON file (`register_file`) or the settings' `register(ctx)`.
- **On the page,** each screen's root and each sheet carry their ID (`data-screen="AB-012"`); parts carry their name (`data-name="save-button"`). A sheet's ID goes on the sheet itself or inside it.
- The scan reads the ID from the screen; failing that, it looks the code key up in the register (aliases included).
- **No ID yet:** a captured screen with no ID is flagged with a suggested next number. It's a suggestion only: the register changes in an app build, never from the Atlas.
- **Not found this scan:** a live register entry no screen showed. Kept, never deleted.
- States share their screen's ID: `AB-001~first-launch`.

### Proposed screens

A JSON list, or `PROPOSED` in the settings:

```json
[{"screen": "AB-005", "title": "Save button moved up", "file": "prototypes/save-first.html", "slug": "…", "version": "2"}]
```

The scan opens each prototype at the same size (a Prototype kit page with Inspect off and its controls hidden; any other page as it is), captures it and maps its named parts. In the Atlas it shows beside the real screen, with a wipe between the two. Prototypes can also be listed from the page itself ("+ List a prototype for this screen"); they show after the next rescan.

## Notes and "check my notes"

On claude.ai, with the page's store declared, the Atlas keeps:

| In the store | What |
|---|---|
| `notes` | One document per note, in note format v1 ([SHARED.md](SHARED.md)), ids starting `a-`, plus the Atlas's own fields (`sid`, `area`, `shot`, `how`, `docs`, `errors`, `scan`) |
| `layout/map` | Where cards sit on the map, and its note labels |
| `proposed` | Prototypes listed against real screens: `screen`, `title`, `url`, `slug`, `added` |

**"Check my notes"** in a Claude chat: Claude reads the Atlas page's `notes` and `proposed`, then each listed prototype's own `notes`, and reports them together, grouped by screen, oldest open first, each with its source. `python3 -m atlas_kit.notes atlas.json prototype.json …` does the same from saved copies. Claude or you can set a note's status (Open · Looking into it · Fixed · Dismissed).

Copying a report starts with the shared header:

```
Atlas notes · note format v1 · 3 Nov 2026
Source: atlas · App: … · Scan: … · Kit 1.0.0
```

**Never stored:** anything typed into a field, or real user data.

## atlas.json

| Field | What |
|---|---|
| `format`, `kit` | `4`, and the kit version that made it |
| `app`, `kind`, `areas` | From the settings |
| `scan` | `id`, `at`, `seconds`, `commit`, `version`, `viewport`, `data`, `clock`, `passes`, `codeStates`, `docProblems`; after an earlier scan, `prev` (with the versions `between`) and `codeChanges`; `baselines` (the earlier scans tags are counted against) |
| `ids` | With screen IDs: `register` (how many), `noId` (with suggestions), `notFound`, `retired` |
| `screens` | Each: `id`, `sid`, `title`, `caption`, `area`, `kind`, `key`, `family`, `state`, `stateOf`, `status` (captured · failed · uncaptured · notfound · gone), `why`, `errors`, `shot`, `full`, `elements` (for tap-a-part), `links` (label, action, how, why, `to`, `kind`, `forced`), `from`, `via`, `how`, `docs`, `mention`, `change` (since the last scan), `since` (NEW or CHANGED by baseline) |
| `flows` | Each: `id`, `title`, `status`, `why`, `steps` (`n`, `moment`, `label`, `shot`, `screen`, `next`: the box of the button tapped next) |
| `doors` | `from`, `to`, `how`, `kind` |
| `proposed` | `pid`, `screen`, `title`, `shot`, `elements`, `slug`, `url`, `version`, `status` |
| `aliases` | Other names each screen had (its first id, its code key), so notes and layouts made under them still find it |
| `changelog`, `inventory` | The latest changelog entries, and the code's list |

## Files

| File | What it is |
|---|---|
| `atlas.py` | The command |
| `atlas_kit/engine.py` | The scan: capture, tap, follow, flows, proposed screens |
| `atlas_kit/browser.py` | Fresh pages with the clock frozen, and the scripts run in the page |
| `atlas_kit/ids.py` | Screen IDs, and finding screens by any of their names |
| `atlas_kit/compare.py` | Changes since the last scan, and tags since a chosen version |
| `atlas_kit/docs.py` | Doc sections and the changelog |
| `atlas_kit/code.py` | Helpers for settings that read the app's JavaScript |
| `atlas_kit/notes.py` | "Check my notes" |
| `atlas_kit/settings.py` | Reading a settings file, with the defaults |
| `viewer.html` | The Atlas page (one file, for any app) |
| `tests/` | Two made-up apps and the kit's tests |
| `SHARED.md` | Devices, looks, text styles and note format v1, identical in the Prototype kit |
| `HANDOFF.md` | Approvals and builds of each kit version |

## Tests

```
python3 tests/test_kit.py
```

Scans a made-up website and a made-up app of screens (with IDs, a flow, a door, captions and a "version 2" that renames a code key, adds a screen with no ID and changes how one looks), then checks the viewer, notes and "check my notes" with a stand-in for the page's store. It also checks that no app's names are in the kit, and that `SHARED.md` matches the Prototype kit's. With the Prototype kit beside this repo (or `PROTOTYPE_KIT=path`), a real Prototype kit page is captured as a proposed screen too. About 2 minutes.

## Licence

MIT. See [LICENSE.txt](LICENSE.txt).
