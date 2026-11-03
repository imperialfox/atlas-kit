# Atlas kit · Handoff

Each kit version gets its own Render and Build here. No Q number: the kit belongs to no app.

## Kit 1.0

> **Render:** Approved by Ivan on 2 Nov 2026, 19:50 ("Render. This is how I want things to be. Building system in place to be more optimal.") for Piece 1 of `claude/atlas_kit_prototype_kit_tandem_blueprint.md`, with all its decision defaults taken: items 1–8 below.
> **Render (widened):** 3 Nov 2026, 00:39 ("Render all mentioned"): items 9–13 below folded into 1.0, as Ivan chose on 3 Nov ("2-6 i want these in the kit for sure", 00:29), since nothing is built yet. Source: what the "Vocal Sessions · Screen flow" design canvas does that the Atlas didn't.
> **Render (widened again):** 3 Nov 2026, 08:00 ("Render"): item 14 · Stable IDs below, Piece B of `claude/screen_ids_blueprint.md`.
> **Build:** 3 Nov 2026, 08:22 (Ivan: "Build Atlas kit 1.1"; there was no 1.1, so Claude asked, and Ivan picked Atlas kit 1.0). Kit 1.0.0.

**For:** Claude · **Job:** build · **Builder for this change:** Claude
**Home:** new public repo `imperialfox/atlas-kit`, MIT. Code only: screenshots and notes never go in it. It belongs to no app, so it has no Q number and isn't in any app's queue (like `imperialfox/prototype-kit`).
**This file is the live record** (copied in from Ivan's project notes at Build, with the Render stamps).
**Build order:** Prototype kit 1.1 (built 2 Nov 2026, 1.1.0, commit 40295d1 in `imperialfox/prototype-kit`), then this, then Vocal Sessions Q31 (re-scoped; Render recorded in that repo's `RENDER_QUEUE.md`, commit 327b0ab), then Vocal Sessions Q35 · Atlas: Starting States (fills in Vocal Sessions' flows, captions and doors, using the screen IDs from Q36 · Interface: Screen IDs).

**Goal:** one universal Atlas that works for any of Ivan's apps or sites: every screen as a saved screenshot, how screens link, what changed since the last scan, and notes on real screens that Claude can read.

**Start from:**
- Vocal Sessions `tools/atlas/` as shipped by Q30 (`e3de321`): `scan.py`, `inventory.py`, `viewer.html`, `atlas.py`, `test_atlas.py`. `screens.py` is Vocal Sessions' own settings and stays in that repo.
- The stage-2 prototype page (artifact `f5edbbc0-35fd-4573-bdf7-035b31b22705`, its `index.html`): map, note mode, notes drawer, export, changes view. Scanner: `claude/atlas_prototype_scan.py` (`ELEMENTS`, `compare()`).
- `SHARED.md` from Prototype kit 1.1.0 (copy it unchanged). Its note format v1 table already follows the Atlas prototype's note fields; Atlas notes add `v: 1`, `source: 'atlas'`, `part` and `from.scan`. The Atlas report's header uses `Atlas notes` and `Source: atlas · App · Scan · Kit` in the same places as the prototype's.
- Prototype pages keep their notes in their own store's `notes` collection (ids start `p-`) and their draft in `kit/draft`; `Kit.notes()` gives the same records on a page without a store. Proposed screens can use the prototype's `real` option to show the Atlas screenshot.
- For items 9–13: the "Vocal Sessions · Screen flow" design canvas (artifact `bcc7af97-a5f1-40f4-aaa5-95df7be347b1`) shows each one by hand; its capture script's flow steps are a worked example (see `claude/q35_atlas_starting_states_handoff.md`).

**Scope:**
1. **Scan engine:** open each screen in a throwaway browser, freeze the clock, capture top and full length, tap every button on a reset copy, follow what opens, map what's on each screen (for tap-a-part notes), and compare with the last scan. Rules kept from Q30: open screens through their real buttons; reset fully before every tap; a sheet that didn't open is "Failed"; honest "Not tested" reasons.
2. **Two kinds of app:**
   - *Screens without addresses* (like Vocal Sessions): the app's settings file gives the hooks (start with sample data, list screens, open one, reset, tell which screen is showing, buttons to skip).
   - *Pages with addresses* (ordinary websites): pages found by following links; settings are the start address, size and skip list.
3. **Viewer:** Lightbox, details, map, notes, export, changes since last scan (the full feature list is Q31's in Vocal Sessions' `RENDER_QUEUE.md`). The app's name, areas and docs come from the scan, not the page's code.
4. **Notes** in the page's own store, in note format v1 from `SHARED.md`, so Claude reads them.
5. **Proposed screens:** a prototype can be listed against the real screen it changes; the Atlas scans it and shows it beside that screen, with the before/now wipe. Parts named with `data-name` keep their names in notes.
6. **"Check my notes":** the page keeps the list of proposed prototypes in its store, so Claude can read the Atlas's notes and each listed prototype's notes together.
7. **Guide:** README "Adding an app" in plain steps, the settings explained, the `atlas.json` format; `CHANGELOG.md` starting at 1.0; `LICENSE.txt` (MIT); `SHARED.md`; this handoff.
8. **Proof and tests:** a tiny made-up test site (addresses) and a tiny made-up state-driven page, both scanned in the kit's tests; a check that no app's names are in the kit.
9. **Flows:** the app's settings can name walk-throughs, each a list of steps (start state, the button to tap, what to capture). The scanner captures every step; the viewer gets a Flows view you step through like a slideshow, with the tapped button shown between steps and each step linked to its screen in the Lightbox. One screen can appear at several moments (fresh, filled in, finished).
10. **Captions:** an optional one-line, plain-words caption per screen in the settings file, shown on cards and in details. A screen without one shows nothing (no made-up text).
11. **Tags since a chosen version:** pick a baseline scan; cards are tagged NEW (not in the baseline) or CHANGED (looks different from it), with a filter. Uses the same comparison as changes since the last scan, and never claims which release caused a change.
12. **Map labels switch:** show what's tapped on every line of the map at once, on or off (otherwise it shows on click).
13. **Doors the scan can't test:** the settings can list hand-written doors per screen (a swipe, a hold, a timed sheet, a file picker). They're drawn as dashed lines marked "Not tested by the scan" and listed in details.
14. **Stable IDs:** the app's settings can point the kit at its register and at `data-screen` / `data-name` on the page, so the scan reads each screen's ID from the screen itself. IDs are the keys for screens, notes, flows, captions, tags since a version and the saved map layout; apps without IDs keep code-based keys. IDs show on cards and in details, and search finds them (`VS-041`, `F-01`, `VS-041 › done-button`). A captured screen with no register entry is flagged "No ID yet · suggested VS-0xx" in the viewer and the report (a suggestion only: the app's register changes in an app build). A register entry the scan can't find shows as "Not found this scan", never deleted. Notes on a named part keep its name, so they still point at it after a redesign moves it.

**Agreed (defaults taken at Render):** own public repo, MIT; apps use a pinned copy (no submodule); prototype notes on a page not published on claude.ai stay on that device; "check my notes" covers both kits; each kit version gets its own Render and Build in its own `HANDOFF.md`, no Q number; scans use sample data only.

**Out of scope:** moving Vocal Sessions onto the kit (that's Q31); filling in Vocal Sessions' own flows, captions and doors (that's Q35); wiring up any real second app or site; compare views across screens and sizes; an overview page of areas (offered 3 Nov, not chosen); any app change.

**Done when:**
- No app's names, colours or screens are in the kit (its tests check).
- The kit scans both made-up test apps.
- A note made in a prototype and a note made in the Atlas come back together from "check my notes", in the same format.
- A prototype listed in the Atlas shows beside its real screen, with the wipe.
- `SHARED.md` is identical to the Prototype kit's.
- The made-up test apps include a flow of at least three steps and a hand-written door, both shown in the viewer.
- A baseline scan tags one added screen NEW and one altered screen CHANGED.
- A made-up test app with IDs keeps a note attached after its code key is renamed (with the old key as an alias), and a screen added without an ID is flagged with a suggested number.

**After the work:** a Debrief in the repo's `HANDOFF.md`, and up to five checks for Ivan's phone.

## Debrief · kit 1.0 (3 Nov 2026)

**What's in it:** everything in items 1–14. See `CHANGELOG.md` › 1.0.0 and the README.

- **Scan engine** (`atlas_kit/engine.py`, `browser.py`): Q30's scanner made general. An app gives a settings file (a Python file, like Q30's `screens.py`): `load(page, setup, ctx)`, `WHERE`, `SNAPSHOT`/`RESET`, `ROOTS`, and optional naming hooks (`family`, `keys_of`, `area_of`, `kind_of`, `describe`, `link_kind`, `key`, `inventory`, `docs`). Everything Q30's `screens.py` and `scan.py` did for Vocal Sessions fits these hooks, including the set-up with a file picker (inside `load`) and `{song}`-style placeholders (`prepare(ctx)` returns `vars`).
- **Pages with addresses:** pages found by following links (served from the site's folder, or from an `https://` address). Links out of the site, email links and new-tab links are Not tested; a missing page is Broken (404). Pages in the folder nothing links to are "Not captured yet".
- **Viewer** (`viewer.html`): the stage-2 prototype page made general (app name, areas, docs and queue file come from `atlas.json`), plus Flows, captions, tags since a version, the map labels switch, dotted doors, proposed screens with a wipe, IDs, "No ID yet" and "Not found this scan". Notes are note format v1 with ids starting `a-`.
- **"Check my notes":** `atlas_kit/notes.py` reports Atlas and prototype notes together, grouped by screen, oldest open first. Claude reads the Atlas page's `notes` and `proposed`, then each listed prototype's `notes`.
- **IDs** (`atlas_kit/ids.py`): read from `data-screen` on the screen (a sheet's on the sheet itself), or from the register by code key and aliases. Final ids are the screen IDs (`AB-001`, states `AB-001~first-launch`). `aliases` in `atlas.json` keep notes and layouts made under older names attached.

**Decided along the way (defaults, all changeable):**
- Settings files are Python, so apps can hook in code (Q30's `screens.py` already was).
- CHANGED in "tags since a version" means the picture differs (links alone don't count); the since-last-scan view still lists link changes.
- When tags are on, a card shows its tag and not also the since-last-scan badge, so it isn't said twice.
- The map's labels switch shows small pills at the middle of each line.
- Proposed screens: the scan opens a Prototype kit page with Inspect off and the kit's own controls hidden, and captures its screen. Listing from the page writes to the store's `proposed`; it shows after the next rescan.
- Pages' areas default to their folder ("Menu" for `/menu/…`, "Home" for top-level pages).

**Checked:** `python3 tests/test_kit.py`: 82 checks pass. Two made-up apps (a website and an app of screens with IDs), a version 2 of each, the viewer at computer and phone sizes with a stand-in for the page's store, a real Prototype kit 1.1.0 page as a proposed screen, and a real prototype note read back with an Atlas note. `SHARED.md` is byte-identical to Prototype kit 1.1.0's.

**Demo:** [Atlas kit demo](https://claude.ai/artifact/G6mPQt1qo3iUDaoDMkqFEu) (private), the made-up app at version 2 compared with version 1, with the page's store declared (everyone signed in who can open it reads; only Ivan writes) and downloads.

**Next:** Vocal Sessions Q31 (move its Atlas onto this kit), then Q35.

**For Ivan's phone:**
1. Open the demo, tap a card, then **Add note**: tap the Save button, write a word, Save. The Notes button counts 1.
2. Tap **Flows**: step through F-01 with Next. The ringed button is the one tapped next.
3. In **Map**, switch **Labels** on: each line shows what's tapped. The purple dotted line is the hand-written "Hold" door.
4. Pick **Tags since 1.0** (in the filter chips): Stats shows NEW, Home CHANGED.
5. Open **Add an item**: under "Proposed changes", drag the wipe between Now and Proposed.

## Kit 1.1 · Phone pass

> **Render:** 3 Nov 2026, 11:21, folded into Vocal Sessions Q31 · Atlas: Map and Notes (Ivan: "I'm happy with the current prototype time to fold it into the same q"), after trying the phone prototype (two rounds, the second for smoother zooming, 10:54).
> **Build:** with Q31's Build: one instruction builds this kit version first, then Q31 copies it. Awaiting Ivan's instruction.

**Goal:** the Atlas is easy to use on a phone, and the desktop stays as it is.
**Start from:** the phone prototype page ("Atlas kit 1.1 · phone prototype", artifact `89c96bf1-915c-4e7e-8bde-3ce5218071ed`): its `index.html` is the prototype viewer. Plan and checks: `claude/atlas_kit_1_1_phone_blueprint.md` in Ivan's project notes.

**Scope (on a phone; desktop unchanged):**
1. **Map:** pinch to zoom around your fingers; one finger moves the map; double-tap a screen to zoom to it, double-tap the background to zoom in (or fit when close); one tap opens a screen; hold a card, then drag, to move it. Opens at a readable size on the first area. Options (Show, Labels, Note label, Tidy layout) behind **Map options**; the legend behind **Key**.
2. **Zoom viewer** for full length, details, before/now, proposed and flow steps: pinch, double-tap, drag; wipes can be zoomed with their slider.
3. **Notes:** pinch to zoom the screen, tap a part, the form slides up as a bottom sheet; the zoom stays.
4. **Compact top:** one row (name, search icon, rescan, Notes with count); search opens over the row with Cancel. Banners fold to one line.
5. **Bottom bar** for Lightbox · Map · Flows.
6. **Swipes:** details left/right for the next screen, down to close; flows left/right for the next step, with the picture and step side by side and Back · Next · Lightbox always on screen.
7. **Lightbox grid:** pinch for 2, 3 or 4 columns, remembered on the device.
8. **Feel:** drawn once per screen refresh; past a zoom or edge limit it gives a little and eases back; a flick glides to rest; double-tap, fit, zoom-to-card and the + / − buttons animate (about 0.3 s) with the point under your finger kept still; the page itself can't zoom under a pinch on iOS; the map's place is saved after moving stops.
9. Tap targets at least 44 pt; safe areas respected. **Desktop:** unchanged, plus trackpad pinch in the zoom viewer and animated map buttons.

**Defaults:** bottom bar on phones; 3 columns to start; double-tap 2.5×; most zoom 6× on pictures, 5× in note mode, 250 % on the map.
**Out of scope:** anything in an app; the Prototype kit; compare views.
**Done when:** the kit's tests gain phone checks (iPhone size with touch: map, zoom viewer and note-mode pinch; swipes; bottom bar; 44 pt controls; give and ease-back at the limits; one draw per frame; no sideways scroll; no errors) and all pass, with the desktop checks unchanged; `CHANGELOG.md` 1.1.0; the demo page republished on 1.1.
**After the work:** a Debrief here, and up to five checks for Ivan's phone.
