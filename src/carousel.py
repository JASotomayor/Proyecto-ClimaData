"""Swipeable card carousel rendered as a self-contained HTML component.

Uses st.components.v1.html() so all interaction (touch swipe, mouse drag,
dot navigation) runs entirely client-side inside an iframe — no Streamlit
round-trips, no session state, no buttons.

Usage
-----
    from src.carousel import render_swipe_carousel

    render_swipe_carousel([
        "<b>Primer insight</b> — texto del panel 1.",
        "<b>Segundo insight</b> — texto del panel 2.",
    ])
"""
from __future__ import annotations

import re
import uuid


def render_swipe_carousel(
    slides: list[str],
    height: int | None = None,
) -> None:
    """Render a horizontally swipeable carousel of insight cards.

    Parameters
    ----------
    slides:
        List of HTML strings, one per card.
    height:
        Iframe height in pixels.  If *None* the height is estimated from
        the length of the longest slide text.
    """
    import streamlit.components.v1 as components

    if not slides:
        return

    n = len(slides)
    uid = uuid.uuid4().hex[:8]

    # ── Height estimation ─────────────────────────────────────────────────────
    if height is None:
        # Strip HTML tags to get approximate character count
        plain_max = max(len(re.sub(r"<[^>]+>", "", s)) for s in slides)
        lines = max(3, plain_max // 62)          # ~62 chars per line on mobile
        height = max(110, lines * 22 + 52)       # 22 px/line + bottom bar (tighter)

    # ── Build HTML fragments ──────────────────────────────────────────────────
    slides_html = "".join(
        f'<div class="sl">{s}</div>' for s in slides
    )
    dots_html = "".join(
        f'<span class="dot{"  on" if i == 0 else ""}" data-i="{i}"></span>'
        for i in range(n)
    )

    # ── Full component HTML ───────────────────────────────────────────────────
    html = f"""<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width,initial-scale=1">
<link
  href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;600;700&display=swap"
  rel="stylesheet">
<style>
*{{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}}
html,body{{background:transparent;overflow:hidden}}
body{{font-family:'Montserrat','Segoe UI',system-ui,sans-serif;padding:0}}

/* ── wrapper: clips the fade edge ── */
.wrap{{position:relative;overflow:hidden;border-radius:0 9px 9px 0}}

/* ── right-edge fade: affordance visual de swipe ── */
.wrap::after{{
  content:'';
  position:absolute;
  top:0;right:0;bottom:0;
  width:36px;
  background:linear-gradient(to right,transparent,#F7F6F5 85%);
  pointer-events:none;
  border-radius:0 9px 9px 0;
  transition:opacity .3s;
  z-index:2;
}}
.wrap.last::after{{opacity:0}}

/* ── carousel shell ── */
.car{{
  width:100%;
  overflow:hidden;
  user-select:none;
  -webkit-user-select:none;
  cursor:grab;
  touch-action:pan-y;
}}
.car.drag{{cursor:grabbing}}

/* ── sliding track ── */
.trk{{
  display:flex;
  transition:transform .38s cubic-bezier(.4,0,.2,1);
  will-change:transform;
}}

/* ── individual card ── */
.sl{{
  min-width:100%;
  padding:.85rem 1.1rem;
  background:#F7F6F5;
  border-left:3px solid #EF9645;
  border-radius:0 9px 9px 0;
  font-size:.88rem;
  line-height:1.68;
  color:#1E3953;
  word-break:break-word;
}}

/* ── bottom bar: dots + counter ── */
.bottom{{
  display:flex;
  align-items:center;
  justify-content:space-between;
  padding:5px 2px 0;
}}
.dots{{
  display:flex;
  align-items:center;
  gap:6px;
}}
.dot{{
  width:8px;height:8px;
  border-radius:50%;
  background:#D8D4D0;
  cursor:pointer;
  transition:background .22s,transform .22s;
  flex-shrink:0;
}}
.dot.on{{
  background:#1E3953;
  transform:scale(1.45);
}}
.ctr{{
  font-size:.68rem;
  font-weight:600;
  color:#8FA8BB;
  letter-spacing:.04em;
  padding-right:2px;
}}
</style>
</head>
<body>
<div class="wrap" id="wrp{uid}">
  <div class="car" id="car{uid}">
    <div class="trk" id="trk{uid}">{slides_html}</div>
  </div>
</div>
<div class="bottom">
  <div class="dots" id="dts{uid}">{dots_html}</div>
  <span class="ctr" id="ctr{uid}">1 / {n}</span>
</div>

<script>
(function(){{
  var wrp = document.getElementById('wrp{uid}');
  var car = document.getElementById('car{uid}');
  var trk = document.getElementById('trk{uid}');
  var dots = document.querySelectorAll('#dts{uid} .dot');
  var ctr  = document.getElementById('ctr{uid}');
  var N = {n};
  var cur = 0;
  var sx = 0, sy = 0;
  var dragging = false;

  function goTo(i) {{
    cur = Math.max(0, Math.min(i, N - 1));
    trk.style.transform = 'translateX(-' + (cur * 100) + '%)';
    dots.forEach(function(d, j) {{ d.classList.toggle('on', j === cur); }});
    ctr.textContent = (cur + 1) + ' / ' + N;
    /* hide right fade on last slide */
    if (cur === N - 1) wrp.classList.add('last');
    else wrp.classList.remove('last');
  }}

  car.addEventListener('touchstart', function(e) {{
    sx = e.touches[0].clientX;
    sy = e.touches[0].clientY;
  }}, {{ passive: true }});

  car.addEventListener('touchmove', function(e) {{
    var dx = Math.abs(e.touches[0].clientX - sx);
    var dy = Math.abs(e.touches[0].clientY - sy);
    if (dx > dy && dx > 8) e.preventDefault();
  }}, {{ passive: false }});

  car.addEventListener('touchend', function(e) {{
    var dx = sx - e.changedTouches[0].clientX;
    var dy = sy - e.changedTouches[0].clientY;
    if (Math.abs(dx) > Math.abs(dy) && Math.abs(dx) > 30) {{
      goTo(cur + (dx > 0 ? 1 : -1));
    }}
  }}, {{ passive: true }});

  car.addEventListener('mousedown', function(e) {{
    sx = e.clientX;
    dragging = true;
    car.classList.add('drag');
    e.preventDefault();
  }});

  window.addEventListener('mouseup', function(e) {{
    if (!dragging) return;
    dragging = false;
    car.classList.remove('drag');
    var dx = sx - e.clientX;
    if (Math.abs(dx) > 30) goTo(cur + (dx > 0 ? 1 : -1));
  }});

  dots.forEach(function(d, i) {{
    d.addEventListener('click', function() {{ goTo(i); }});
  }});
}})();
</script>
</body>
</html>"""

    components.html(html, height=height, scrolling=False)
