# Shared basics · Prototype kit and Atlas kit

This file is kept **identical** in `imperialfox/prototype-kit` and `imperialfox/atlas-kit`. Changing it means changing both, in the same sitting, and noting it in both changelogs.

- **Prototype kit:** *try* a change. A clickable screen in a device frame you can nudge, resize and note.
- **Atlas kit:** *see* the real app. Every screen as a saved screenshot, how they link, what changed, and notes on real screens.

## Devices

| Device | Width × height (points) |
|---|---|
| iPhone | 402 × 874 |
| iPad | 820 × 1180 |
| Mac | 1440 × 900 |

## Looks

Light and Dark. Motion: Normal, or Reduce Motion.

## Text styles by size

| Size (pt) | 34 | 28 | 22 | 20 | 17 | 16 | 15 | 13 | 12 | 11 |
|---|---|---|---|---|---|---|---|---|---|---|
| Style | Large title | Title 1 | Title 2 | Title 3 | Body | Callout | Subhead | Footnote | Caption 1 | Caption 2 |

## Note format v1

Each note is one document in the page's own store, in a collection called `notes`, so Claude can list them from a chat ("check my notes"). Fields readers don't know are ignored, so a kit may add its own.

| Field | What it holds |
|---|---|
| `v` | `1` |
| `n` | The note's number on that page, starting at 1 |
| `source` | `atlas` or `prototype` |
| `app` | The app's name |
| `screen`, `screenTitle` | The real screen's id (the Atlas's) and its readable name |
| `part` | The part's `data-name`, when it has one; otherwise `null` |
| `name` | A readable name for the part ("Button: Refresh", "Box in Header") |
| `box` | The marked area as fractions of the screen: `x`, `y`, `w`, `h` from 0 to 1 |
| `px` | The same area in points |
| `element` | `tag`, `cls` (classes), `text` (up to 80 characters), `path` (a short CSS path), `style` (`font`, `lh`, `color`, `bg`, `pad`, `radius`) |
| `text` | The note itself (may be empty for a change with no note) |
| `kind` | Optional: Looks different · Layout or spacing · Text · Goes to the wrong place · Doesn't work · Accessibility · Other |
| `status` | `open` · `looking` (Looking into it) · `fixed` · `dismissed` |
| `from` | Atlas: `scan` (id, version, commit). Prototype: `prototype` (its id), `version`, `kit` |
| `edits` | Prototype only: `move` (`dx`, `dy`), `width`, `height`, `corners` (each `[before, after]`), `copyOf` |
| `created`, `updated` | ISO dates |

**Statuses** are set by Ivan or by Claude. A kit keeps a status it finds, except that a note marked `fixed` or `dismissed` goes back to `open` when the note or change itself is edited.

**Never stored:** anything typed into a field, and real user data. Element text is left empty for text boxes and editable areas.

## The shared header

Copy changes (prototype) and a copied report (Atlas) start with the same two lines:

```
Prototype changes · note format v1 · 2 Nov 2026
Source: prototype · App: … · Screen: … · Prototype: … · Version: … · Kit 1.1.0
```

The Atlas uses `Atlas notes` and `Source: atlas · App: … · Scan: … · Kit …` in the same places.
