"""The browser side of a scan: a local server for the app's folder, fresh pages with the clock frozen and motion off,
and the scripts run inside the page (where am I, what's on screen, which buttons are there). General for any app.
"""
import functools
import os
import threading
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler


class Server:
    """Serves a folder on 127.0.0.1 for the length of a scan, so pages load as they would from a host."""

    def __init__(self, folder):
        class Quiet(SimpleHTTPRequestHandler):
            def log_message(self, *a): pass
            def end_headers(self):
                self.send_header('Cache-Control', 'no-store')
                super().end_headers()
        self.srv = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=folder))
        self.url = f'http://127.0.0.1:{self.srv.server_address[1]}/'
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self):
        self.srv.shutdown(); self.srv.server_close()


def new_page(b, st, dark=False, errors=None, statuses=None):
    """A fresh, throwaway page: the settings' screen size, light or dark, Reduce Motion, the clock frozen."""
    opts = dict(viewport={'width': st.viewport['w'], 'height': st.viewport['h']}, device_scale_factor=st.scale,
                color_scheme='dark' if dark else 'light', reduced_motion='reduce', accept_downloads=False,
                timezone_id=st.timezone, locale=st.locale)
    if st.user_agent: opts['user_agent'] = st.user_agent
    ctx = b.new_context(**opts)
    ctx.clock.install(time=st.fixed_time.timestamp())
    if st.init_script: ctx.add_init_script(st.init_script)
    pg = ctx.new_page()
    if errors is not None:
        pg.on('pageerror', lambda e: errors.append(str(e).splitlines()[0][:240] if str(e) else 'error'))
        pg.on('console', lambda m: errors.append('console: ' + m.text[:240]) if m.type == 'error' and 'Failed to load resource' not in m.text else None)
    if statuses is not None:
        def resp(r):
            try:
                if r.request.is_navigation_request() and r.frame == pg.main_frame: statuses.append(r.status)
            except Exception: pass
        pg.on('response', resp)
    return pg


# ---------- scripts run in the page ----------

# Which screen IDs are showing: an open sheet's and the screen's own (data-screen, or whatever the settings name).
IDS_JS = """o=>{const ok=v=>v&&!/\\?\\?\\?/.test(v)?v:null;
 const sh=o.sheet?[...document.querySelectorAll(o.sheet)].find(e=>{const r=e.getBoundingClientRect();return r.width&&r.height}):null;
 let sheet=null,screen=null;
 if(sh){const e=sh.hasAttribute(o.attr)?sh:sh.querySelector('['+o.attr+']');sheet=e?e.getAttribute(o.attr):null}
 for(const e of document.querySelectorAll('['+o.attr+']')){if(sh&&sh.contains(e))continue;
  const r=e.getBoundingClientRect();if(!r.width&&!r.height)continue;screen=e.getAttribute(o.attr);break}
 return {screen:ok(screen),sheet:ok(sheet),rawScreen:screen,rawSheet:sheet,sheetOpen:!!sh}}"""

SHEET_OPEN_JS = """s=>!!(s&&[...document.querySelectorAll(s)].find(e=>{const r=e.getBoundingClientRect();return r.width&&r.height}))"""

# What's on the screen, for "tap a part" notes: boxes in points, short text, a simplified path, key styles and the part's
# name (data-name, or what the settings name). Never records what's typed in a field: only the field's kind.
ELEMENTS_JS = """o=>{const vis=e=>{const r=e.getBoundingClientRect();return r.width&&r.height};
 const sh=o.sheet?[...document.querySelectorAll(o.sheet)].find(vis):null;
 const root=sh||document.querySelector(o.root)||document.body;
 const sel='['+o.part+'],[data-a],h1,h2,h3,button,a,input,select,textarea,label,p,li,img,svg,canvas,video,[role=button],[role=tab],[class*=card],[class*=row],[class*=tile],nav,header,footer';
 const W=innerWidth,H=innerHeight,out=[];
 const nm=e=>e.tagName.toLowerCase()+([...e.classList].slice(0,2).map(c=>'.'+c).join(''));
 const els=[...root.querySelectorAll(sel)];
 root.querySelectorAll('span,div,b,small,strong,em,i').forEach(e=>{if(!e.childElementCount&&(e.textContent||'').trim())els.push(e)});
 if(o.bar){const bar=document.querySelector(o.bar);if(bar&&!root.contains(bar))els.push(bar,...bar.querySelectorAll('['+o.part+'],[data-a],button,a'))}
 const seen=new Set();
 for(const e of els){if(out.length>=360)break;if(seen.has(e))continue;seen.add(e);
  const r=e.getBoundingClientRect();if(r.width<4||r.height<4||r.bottom<0||r.top>H||r.right<0||r.left>W)continue;
  if(e.closest('svg')&&e.tagName.toLowerCase()!=='svg')continue;
  const cs=getComputedStyle(e);if(cs.visibility==='hidden'||+cs.opacity===0)continue;
  const path=[];let a=e;for(let i=0;i<4&&a&&a!==document.body;i++){path.unshift(nm(a));a=a.parentElement}
  const field=/^(INPUT|TEXTAREA|SELECT)$/.test(e.tagName)||e.isContentEditable;
  const own=e.getAttribute(o.part),inn=e.parentElement&&e.parentElement.closest('['+o.part+']');
  out.push({x:Math.round(r.left),y:Math.round(r.top),w:Math.round(r.width),h:Math.round(r.height),tag:e.tagName.toLowerCase(),
   cls:[...e.classList].slice(0,3).join(' '),a:e.dataset.a||'',v:e.dataset.v||'',part:own||null,in:inn?inn.getAttribute(o.part):null,
   text:field?'('+(e.type||e.tagName.toLowerCase())+' field)':((e.getAttribute('aria-label')||e.innerText||e.getAttribute('alt')||'').replace(/\\s+/g,' ').trim().slice(0,80)),
   path:path.join(' > '),style:{font:cs.fontSize+' '+cs.fontWeight,lh:cs.lineHeight,color:cs.color,bg:cs.backgroundColor,pad:cs.padding,radius:cs.borderRadius}})}
 return out}"""

# The buttons on the screen (inside an open sheet, if there is one), each with a selector that finds it again.
BUTTONS_JS = """o=>{const vis=e=>{const r=e.getBoundingClientRect();return r.width&&r.height};
 const sh=o.sheet?[...document.querySelectorAll(o.sheet)].find(vis):null;const root=sh||document;
 const pre=sh?':is('+o.sheet+') ':'';const seen=new Set(),out=[];
 const q=s=>String(s).replace(/["\\\\]/g,'\\\\$&');
 const path=e=>{const p=[];let a=e;while(a&&a!==document.body&&a!==root){let s=a.tagName.toLowerCase();if(a.id&&/^[A-Za-z][\\w-]*$/.test(a.id)){p.unshift('#'+a.id);break}
   const sib=a.parentElement?[...a.parentElement.children].filter(c=>c.tagName===a.tagName):[];if(sib.length>1)s+=':nth-of-type('+(sib.indexOf(a)+1)+')';p.unshift(s);a=a.parentElement}return p.join(' > ')};
 root.querySelectorAll(o.buttons).forEach(e=>{if(!vis(e))return;if(e.closest('[hidden]'))return;if(e.matches('[disabled]'))return;
  let sel,k;
  if(e.dataset.a){sel='[data-a="'+q(e.dataset.a)+'"]'+(e.dataset.v?'[data-v="'+q(e.dataset.v)+'"]':'')+(e.dataset.k?'[data-k="'+q(e.dataset.k)+'"]':'');k='a|'+sel}
  else if(e.getAttribute(o.part)){sel='['+o.part+'="'+q(e.getAttribute(o.part))+'"]';k='n|'+sel}
  else if(e.tagName==='A'&&e.getAttribute('href')){sel='a[href="'+q(e.getAttribute('href'))+'"]';k='h|'+sel}
  else if(e.id&&/^[A-Za-z][\\w-]*$/.test(e.id)){sel='#'+e.id;k='i|'+sel}
  else{sel=path(e);k='p|'+sel}
  if(seen.has(k))return;seen.add(k);
  const lbl=(e.getAttribute('aria-label')||e.innerText||e.textContent||e.title||e.value||((e.querySelector('img')||{}).alt)||'').replace(/\\s+/g,' ').trim().slice(0,60);
  const href=e.tagName==='A'?e.href:'';
  out.push({a:e.dataset.a||'',v:e.dataset.v||'',k:e.dataset.k||'',part:e.getAttribute(o.part)||'',label:lbl,href,target:e.getAttribute('target')||'',bar:!!(o.bar&&e.closest(o.bar)),
   sel:(sel.startsWith('#')?sel:pre+sel)})});
 return out}"""

TITLE_JS = """o=>{const vis=e=>{const r=e.getBoundingClientRect();return r.width&&r.height};
 const sh=o.sheet?[...document.querySelectorAll(o.sheet)].find(vis):null;
 if(sh){const h=sh.querySelector('h1,h2,h3');return ((sh.getAttribute('aria-label')||(h&&h.innerText)||'')+'').replace(/\\s+/g,' ').trim()}
 const root=document.querySelector(o.root)||document.body;const h=[...root.querySelectorAll('h1,h2')].find(vis);
 return ((h&&h.innerText)||document.title||'').replace(/\\s+/g,' ').trim()}"""

BOX_JS = """e=>{const r=e.getBoundingClientRect();return {x:Math.round(r.left),y:Math.round(r.top),w:Math.round(r.width),h:Math.round(r.height),
 label:(e.getAttribute('aria-label')||e.innerText||e.value||'').replace(/\\s+/g,' ').trim().slice(0,60)}}"""


def page_opts(st):
    """The settings the in-page scripts need."""
    ids = st.ids or {}
    return {'sheet': st.sheet, 'root': st.root, 'buttons': st.buttons, 'part': ids.get('part_attr', 'data-name'),
            'attr': ids.get('screen_attr', 'data-screen'), 'bar': getattr(st.mod, 'BAR', None)}


def rel(url, base):
    """An address inside the site, written from the site's root ('/', '/about.html', '/blog/'), or None if it's
    outside. A folder's index.html is the folder."""
    from urllib.parse import urlsplit
    if not url or not url.startswith(base.rstrip('/')): return None
    u = urlsplit(url[len(base.rstrip('/')):] or '/')
    p = '/' + u.path.lstrip('/')
    if p.endswith('/index.html'): p = p[:-len('index.html')]
    return p + ('?' + u.query if u.query else '')


def page_slug(key):
    import re
    k = re.sub(r'(^|/)index$', '', re.sub(r'\.html?$', '', key.split('?')[0].strip('/')))
    return re.sub(r'[^a-z0-9]+', '-', k.lower()).strip('-') or 'home'
