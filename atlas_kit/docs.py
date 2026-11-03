"""Reading an app's docs and changelog, with no browser. General: the file names and address come from the settings.

- doc_sections(): every ## and ### heading of the doc files, with the address GitHub gives each one, plus bold
  sub-heads directly under a heading (labelled 'Heading › Sub-head', linking to the heading they sit under).
- changelog(): each version's number, date, headline, change ID (like a queue ID) and address.
"""
import os
import re


def gh_slug(heading):
    """The anchor GitHub gives a Markdown heading: lower case, punctuation dropped (letters, digits, '-', '_' and
    spaces kept), spaces to '-'. Links and code marks count as their text."""
    h = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', heading)
    h = h.replace('`', '').strip().lower()
    h = re.sub(r'[^\w\- ]', '', h)
    return h.replace(' ', '-')


def doc_sections(app_dir, files, base_url=''):
    out = []
    for fname in files:
        p = os.path.join(app_dir, fname)
        if not os.path.exists(p): continue
        seen, parent, in_code = {}, None, False
        for i, line in enumerate(open(p, encoding='utf-8')):
            if line.startswith('```'): in_code = not in_code
            if in_code: continue
            m = re.match(r'^(#{1,6}) (.+?)\s*#*\s*$', line)
            if m:
                h = m.group(2).strip(); s = gh_slug(h)
                n = seen.get(s, 0); seen[s] = n + 1
                anchor = s if n == 0 else s + '-' + str(n)
                if len(m.group(1)) in (2, 3):
                    parent = {'file': fname, 'heading': h, 'label': h, 'anchor': anchor, 'line': i + 1,
                              'url': (base_url + fname + '#' + anchor) if base_url else fname + '#' + anchor}
                    out.append(parent)
                continue
            b = re.match(r'^\*\*([^*]+)\*\*\s*$', line) or re.match(r'^\*\*([^*]+)\*\*', line)
            if b and parent:
                out.append(dict(parent, heading=b.group(1).strip(), label=parent['heading'] + ' › ' + b.group(1).strip(),
                                line=i + 1, sub=True))
    return out


HEAD = re.compile(r'^##\s+\[?v?(\d+(?:\.\d+)+)\]?(?:\s*[·\-–—]\s*([^\n]*))?\n(?:\s*\n)?(?:\*([^*\n]+)\*)?', re.M)


def changelog(app_dir, fname='CHANGELOG.md', base_url='', id_pattern=r'\(([A-Z]+\d+)\)'):
    """Newest first, as changelogs are written."""
    p = os.path.join(app_dir, fname)
    if not fname or not os.path.exists(p): return []
    txt = open(p, encoding='utf-8').read()
    out = []
    for m in HEAD.finditer(txt):
        title = (m.group(3) or '').strip()
        q = re.search(id_pattern, title) if id_pattern else None
        head = m.group(1) + (' · ' + m.group(2).strip() if m.group(2) else '')
        out.append({'version': m.group(1), 'date': (m.group(2) or '').strip(), 'title': title, 'q': q.group(1) if q else None,
                    'url': (base_url + fname + '#' + gh_slug(head)) if base_url else fname + '#' + gh_slug(head)})
    return out


def vkey(v):
    return tuple(int(x) for x in re.findall(r'\d+', v or '0'))


def between(log, lo, hi):
    """The versions released after `lo`, up to and including `hi`."""
    a, b = vkey(lo), vkey(hi)
    return [c for c in log if a < vkey(c['version']) <= b]
