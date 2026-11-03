"""Helpers for reading an app's JavaScript with no browser, for settings files that list the screens their code can
show (`inventory()`). General: they know about strings, comments and braces, not about any app.
"""
import os
import re


def _skip(src, i):
    """If src[i] starts a string or comment, the index just after it; else None."""
    c = src[i]
    if c in '\'"`':
        j = i + 1
        while j < len(src):
            if src[j] == '\\': j += 2; continue
            if src[j] == c: return j + 1
            if c == '`' and src.startswith('${', j):  # a template's ${…}: skip the code inside it
                j = block_end(src, j + 1) + 1; continue
            j += 1
        return j
    if src.startswith('//', i):
        j = src.find('\n', i); return len(src) if j < 0 else j
    if src.startswith('/*', i):
        j = src.find('*/', i + 2); return len(src) if j < 0 else j + 2
    return None


def block_end(src, i):
    """src[i] is '{': the index of the '}' that closes it (strings, comments and templates skipped)."""
    depth = 0
    while i < len(src):
        k = _skip(src, i)
        if k is not None: i = k; continue
        if src[i] == '{': depth += 1
        elif src[i] == '}':
            depth -= 1
            if depth == 0: return i
        i += 1
    return len(src) - 1


def function_body(src, name):
    """The body of `function name(...) {...}` (top level or nested), or '' if there's none."""
    m = re.search(r'function\s+' + re.escape(name) + r'\s*\([^)]*\)\s*\{', src)
    if not m: return ''
    start = m.end() - 1
    return src[start:block_end(src, start) + 1]


def sources(folder, ext='.js'):
    """{file name: text} for every file with that ending in a folder (not below it)."""
    out = {}
    if not os.path.isdir(folder): return out
    for f in sorted(os.listdir(folder)):
        if f.endswith(ext): out[f] = open(os.path.join(folder, f), encoding='utf-8').read()
    return out
