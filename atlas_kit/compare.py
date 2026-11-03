"""Comparing a scan with earlier ones.

- Since the last scan: new and gone screens, pictures that differ (and where), links that differ, captures that failed
  this time, and the changelog versions released in between (the likely cause, never certain: the scan can't tell
  which release changed a screen).
- Tags since a chosen version: against each kept earlier scan (a baseline), every screen is NEW (not in that scan) or
  CHANGED (looks different from it), using the same picture comparison.
"""
import json
import os
import re
import shutil

from . import docs as DOCS

THRESHOLD = 28      # how different a pixel must be to count (0–255, in grey)
MIN_PCT = 0.05      # how much of the screen must differ to count as "looks different"


def load(d):
    p = os.path.join(d, 'atlas.json')
    return json.load(open(p, encoding='utf-8')) if os.path.exists(p) else None


def matcher(pa):
    """Find a screen of an earlier scan by the current screen's id or any of its other names."""
    pv = {s['id']: s for s in pa['screens']}
    al = pa.get('aliases') or {}

    def find(s):
        for n in (s['id'], s.get('sid'), s.get('slug')):
            if n and n in pv: return pv[n]
            if n and n in al and al[n] in pv: return pv[al[n]]
        return None
    return pv, find


def picture_diff(a_path, b_path):
    from PIL import Image, ImageChops
    a = Image.open(a_path).convert('L'); b = Image.open(b_path).convert('L')
    if a.size != b.size: return {'kind': 'looks-different', 'pct': None}
    d = ImageChops.difference(a, b).point(lambda v: 255 if v > THRESHOLD else 0)
    pct = sum(d.histogram()[255:]) / (d.size[0] * d.size[1]) * 100
    box = d.getbbox()
    if pct > MIN_PCT and box:
        return {'kind': 'looks-different', 'pct': round(pct, 2),
                'box': [round(box[0] / a.size[0], 4), round(box[1] / a.size[1], 4),
                        round((box[2] - box[0]) / a.size[0], 4), round((box[3] - box[1]) / a.size[1], 4)]}
    return None


def link_set(s, names):
    return {(l['label'], names(l.get('to')) or l.get('toLabel') or '', l['how']) for l in s.get('links', [])}


def compare_all(atlas, out, prev, baselines, say=print):
    prev = prev if prev and load(prev) else None
    if prev: since_last(atlas, out, prev)
    tags(atlas, out, [b for b in baselines or [] if load(b)], say)


def since_last(atlas, out, prev_dir):
    pa = load(prev_dir)
    pv, find = matcher(pa)
    os.makedirs(os.path.join(out, 'shots', 'prev'), exist_ok=True)
    log = atlas.get('changelog') or []
    between = DOCS.between(log, pa['scan'].get('version'), atlas['scan'].get('version'))
    atlas['scan']['prev'] = {'id': pa['scan']['id'], 'at': pa['scan']['at'], 'version': pa['scan'].get('version'),
                             'commit': pa['scan'].get('commit'), 'between': between}
    # the code's list, compared: what's new and what's gone
    pinv = set(pa.get('inventory', [])); inv = set(atlas.get('inventory', []))
    atlas['scan']['codeChanges'] = {'since': pa['scan']['id'], 'sinceVersion': pa['scan'].get('version'),
                                    'added': sorted(inv - pinv), 'gone': sorted(pinv - inv)}
    cur_names = lambda i: i
    matched = set()
    for s in atlas['screens']:
        o = find(s); ch = {}
        if o: matched.add(o['id'])
        if s['status'] in ('uncaptured', 'notfound'):
            if o and o['status'] == 'captured': ch['kind'] = 'not-recaptured'
            s['change'] = ch or None; continue
        if not o or o['status'] in ('uncaptured', 'notfound'):
            if s['status'] == 'captured': ch['kind'] = 'new'
        elif s['status'] == 'captured' and o['status'] == 'captured':
            d = picture_diff(os.path.join(prev_dir, o['shot']), os.path.join(out, s['shot']))
            if d: ch.update(d)
            # links, by where they go (earlier ids read through the earlier scan's names)
            old = {(l['label'], _cur_id(atlas, l['to'], pa) if l.get('to') else (l.get('toLabel') or ''), l['how']) for l in o.get('links', [])}
            new = link_set(s, cur_names)
            add, rem = sorted(new - old), sorted(old - new)
            if add or rem:
                ch['links'] = {'added': [list(x) for x in add][:20], 'removed': [list(x) for x in rem][:20]}
                ch.setdefault('kind', 'links-changed')
        elif s['status'] == 'failed' and o['status'] == 'captured':
            ch['kind'] = 'failed-now'
        if ch:
            if o and o.get('shot') and os.path.exists(os.path.join(prev_dir, o['shot'])):
                shutil.copy(os.path.join(prev_dir, o['shot']), os.path.join(out, 'shots', 'prev', s['id'] + '.jpg'))
                ch['prevShot'] = 'shots/prev/' + s['id'] + '.jpg'
            ch['between'] = [c['version'] + (' (' + c['q'] + ')' if c.get('q') else '') for c in between]
        s['change'] = ch or None
    for oid, o in pv.items():  # gone from this scan
        if oid in matched or o['status'] != 'captured': continue
        if not os.path.exists(os.path.join(prev_dir, o['shot'])): continue
        shutil.copy(os.path.join(prev_dir, o['shot']), os.path.join(out, 'shots', 'prev', oid + '.jpg'))
        g = dict(o); g.update(status='gone', shot='shots/prev/' + oid + '.jpg', full=None, links=[], elements=[], **{'from': []})
        g['area'] = 'Gone since the last scan'
        g['why'] = 'In the last scan (' + str(pa['scan'].get('version')) + '), not in this one'
        g['change'] = {'kind': 'gone', 'prevShot': g['shot'], 'between': [c['version'] for c in between]}
        atlas['screens'].append(g)


def _cur_id(atlas, prev_to, pa):
    """An earlier scan's link target, as this scan's id (same id, or one of this scan's aliases)."""
    al = atlas.get('aliases') or {}
    ids = {s['id'] for s in atlas['screens']}
    if prev_to in ids: return prev_to
    return al.get(prev_to) or prev_to


def tags(atlas, out, baselines, say=print):
    """NEW or CHANGED against each earlier scan, so the viewer can tag cards since a chosen version."""
    atlas['scan']['baselines'] = []
    for bdir in baselines:
        pa = load(bdir)
        if pa['scan'].get('id') == atlas['scan'].get('id'): continue
        pv, find = matcher(pa)
        bid = pa['scan']['id']
        atlas['scan']['baselines'].append({'id': bid, 'at': pa['scan']['at'], 'version': pa['scan'].get('version'),
                                           'commit': pa['scan'].get('commit')})
        for s in atlas['screens']:
            if s['status'] != 'captured': continue
            o = find(s)
            tag = None
            if not o or o['status'] != 'captured': tag = 'new'
            elif os.path.exists(os.path.join(bdir, o['shot'])) and picture_diff(os.path.join(bdir, o['shot']), os.path.join(out, s['shot'])):
                tag = 'changed'
            if tag: s.setdefault('since', {})[bid] = tag
    atlas['scan']['baselines'].sort(key=lambda b: b['at'], reverse=True)
