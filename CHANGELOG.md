# Changelog

## 1.0.0 · 3 Nov 2026

*First release of the Atlas kit: one Atlas for any app or site, working with the Prototype kit*

**Scanning**
- Any app or site from a small settings file: websites (pages with addresses, found by following links) and apps whose screens have no addresses (opened through their real buttons from a few starting screens).
- Each screen in a throwaway browser with sample data only, the clock frozen and motion off; top and full-length pictures; what's on it mapped for tap-a-part notes.
- Every button tapped on a reset copy: Seen working · Changes this screen · Not tested (with the reason) · Broken. A sheet that didn't open is Failed, never captured as the screen underneath. Links out of the app, email links and anything that deletes, needs a file or pays are never tapped.
- Whatever a tap opens is captured next, through that same button, until nothing new turns up. Screens the code (or the site's folder) has but no tap reached are listed as Not captured yet.

**Viewer**
- Lightbox, details, map (with your own layout and labels), notes, export for Claude, and changes since the last scan with a before/now wipe. The app's name, areas and docs come from the scan.
- **Flows:** walk-throughs from the settings, stepped through like a slideshow, with the button to tap ringed and named between steps.
- **Captions:** one plain line per screen, from the settings, on cards and in details.
- **Tags since a chosen version:** NEW or CHANGED against any earlier scan, with a filter.
- **Map labels switch:** what's tapped on every line at once.
- **Doors the scan can't test:** written by hand in the settings, drawn as dotted lines and listed in details.

**Screen IDs**
- When the app keeps a register, IDs read from the screen itself are the keys for screens, notes, flows, captions, tags and the map layout, so they survive renames. Search finds IDs, flows and parts (`AB-041 › done-button`).
- A screen with no ID yet is flagged with a suggested number; a register entry the scan can't find is shown as Not found this scan, never deleted.

**Works with the Prototype kit**
- Notes in note format v1, kept in the page's own store on claude.ai, so "check my notes" in a Claude chat finds them. `atlas_kit/notes.py` reports Atlas and prototype notes together.
- Proposed screens: a prototype listed against a real screen is scanned and shown beside it, with the wipe. Prototypes can be listed from the page.
- `SHARED.md`, identical to Prototype kit 1.1.0's. Copied reports start with the shared header.

**Proof**
- Two made-up apps in `tests/apps`, scanned by the kit's tests, plus a check that no app's names are in the kit.
