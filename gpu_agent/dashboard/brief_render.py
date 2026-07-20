"""F97 Executive Brief HTML — blocks A-H per the 2026-07-16 format spec (v5)."""
from __future__ import annotations

import html
import re

from .site_render import page
from .deepdive_model import SLOT_TO_DIMENSION
from .agenda import load_slots
from .deepdive_render import deepdive_json, render_deepdive_panel

e = html.escape

_BANNED = [re.compile(p) for p in (
    r"\+\d+ more moved", r"because no alert rule fired", r"internal settings",
    r"\b(this|prior|last) run\b", r"\bF\d{2,3}\b")]

_CHIP_ICON = {"calm": "✓", "watch": "!", "elevated": "▲",
              "critical": "✖"}
_DIR_GLYPH = {"improving": "↑", "steady": "→", "worsening": "↓"}

BRIEF_CSS = """
.hero { font-size: 1.45rem; font-weight: 600; margin: 1rem 0 .5rem; }
.hero .rating { text-transform: uppercase; }
.chip { float: right; border-radius: 1em; padding: .25em .8em; font-size: .9rem;
        color: #fff; }
.chip small { display: block; font-size: .7rem; font-weight: 400; }
.status-calm { background: #0ca30c; }
.status-watch { background: #b97f00; }
.status-elevated { background: #c85f00; }
.status-critical { background: #d03b3b; }
.stalestrip { padding: .5rem .8rem; border-radius: .4rem; color: #fff;
              margin: .6rem 0; }
.kpis, .dims { display: flex; flex-wrap: wrap; gap: .8rem; margin: 1rem 0; }
.kpis .tile, .dims .tile { flex: 1 1 11rem; border: 1px solid var(--line);
        border-radius: .5rem; padding: .8rem; }
.tile .k { font-size: .75rem; letter-spacing: .05em; color: var(--muted);
           text-transform: uppercase; }
.tile .m { font-size: .85rem; margin-top: .15rem; }
.tile .v { font-size: 1.3rem; font-weight: 600; margin: .15rem 0; }
.tile .t, .tile .meta { font-size: .8rem; color: var(--muted); }
.calls td, .calls th { vertical-align: top; }
.calls .trigger { font-size: .85rem; color: var(--muted); }
.strip { list-style: none; padding: 0; }
.strip li { margin: .3rem 0; }
.strip .d { display: inline-block; width: 6.5rem; color: var(--muted);
            font-variant-numeric: tabular-nums; }
.footer { border-top: 1px solid var(--line); margin-top: 2rem; padding-top: .8rem;
          color: var(--muted); font-size: .9rem; }
.tag { font-size: .7rem; letter-spacing: .05em; color: var(--muted);
       text-transform: uppercase; }
"""

DASHBOARD_CSS = """
body { background:#fbfaf7; }
.crumb-row { display:flex; align-items:center; font:700 .68rem/1 Georgia,serif;
             letter-spacing:.14em; color:#8a6d3b; text-transform:uppercase; }
.crumb-row .spacer { flex:1; }
h1 { font-family:Georgia,serif; font-size:1.75rem; }
.rating-label { font:700 .8rem system-ui; letter-spacing:.06em; color:#2e7d32;
                text-transform:uppercase; margin:.2rem 0; }
.brief-two { font:400 1rem/1.6 Georgia,serif; color:#333; max-width:64ch; }
.kcards { display:grid; grid-template-columns:repeat(5,1fr); gap:.6rem; margin:1.2rem 0; }
@media(max-width:820px){ .kcards{grid-template-columns:1fr 1fr;} }
.kcard { background:#fff; border:1px solid #e3ded3; border-radius:.5rem; padding:.6rem .7rem;
         cursor:pointer; transition:.12s; }
.kcard:hover { transform:translateY(-2px); box-shadow:0 4px 12px rgba(0,0,0,.12); }
.kcard .kq { font:.56rem system-ui; color:#8a6d3b; min-height:2.2em; }
.kcard .km { font:.62rem system-ui; color:#999; margin:.25rem 0 .05rem; }
.kcard .kv { font:700 1.15rem ui-monospace,monospace; }
.kcard .kd { font:.56rem ui-monospace,monospace; }
.dash2 { display:grid; grid-template-columns:2fr 1fr; gap:1.2rem; }
@media(max-width:820px){ .dash2{grid-template-columns:1fr;} }
.ddchart-cap { font:600 .72rem system-ui; letter-spacing:.06em; color:#8a6d3b; text-transform:uppercase; }
.ddchart-legend { font:.68rem system-ui; color:#777; }
.dimlist .dimrow { display:flex; align-items:center; gap:.4rem; cursor:pointer;
                   padding:.15rem 0; font:.8rem system-ui; }
.dimlist .dimrow:hover { color:#2e7d32; }
.dimlist .ddot { width:.5rem; height:.5rem; border-radius:50%; display:inline-block; }
.dimlist .spacer { flex:1; }
.dd-scrim { position:fixed; inset:0; background:rgba(10,14,22,.5); opacity:0;
            pointer-events:none; transition:.2s; z-index:40; }
.dd-scrim.open { opacity:1; pointer-events:auto; }
.dd-drawer { position:fixed; top:0; right:0; height:100vh; width:min(460px,93vw);
             background:#fbfaf7; color:#1a1a1a; box-shadow:-8px 0 40px rgba(0,0,0,.35);
             transform:translateX(100%); transition:.24s cubic-bezier(.4,0,.2,1);
             z-index:41; overflow-y:auto; padding:1.1rem 1.2rem; }
.dd-drawer.open { transform:translateX(0); }
.dd-close { position:absolute; top:.8rem; right:.8rem; border:1px solid #e3ded3;
            background:#f4efe5; width:1.9rem; height:1.9rem; border-radius:.4rem; cursor:pointer; }
.dd-eyebrow { font:600 .6rem system-ui; letter-spacing:.09em; text-transform:uppercase; color:#8a6d3b; }
.dd-title { font:700 1.25rem Georgia,serif; margin:.2rem 2rem .4rem 0; }
.dd-badge { display:inline-block; font:600 .68rem system-ui; padding:.15rem .55rem;
            border-radius:.35rem; margin:0 .35rem .25rem 0; }
.dd-l { font:600 .6rem system-ui; letter-spacing:.09em; text-transform:uppercase;
        color:#8a6d3b; margin:1.1rem 0 .35rem; }
.dd-why { font:.8rem/1.55 system-ui; color:#333; margin:0 0 .4rem; }
.dd-ev { border-left:3px solid #2e7d32; background:#f4efe5; border-radius:0 .45rem .45rem 0;
         padding:.5rem .7rem; margin:.4rem 0; font:.75rem/1.5 system-ui; }
.dd-ev b { color:#2e7d32; font-size:.7rem; }
.dd-t { font-size:.65rem; color:#8a6d3b; }
.dd-box { background:#f4efe5; border-radius:.45rem; padding:.5rem .7rem; font:.75rem/1.5 system-ui; }
.dd-good{color:#2e7d32;} .dd-bad{color:#c0632a;}
.dd-full{display:inline-block;margin-top:1rem;font:600 .75rem system-ui;color:#2e7d32;}
"""


def lint_exec_copy(html_text: str) -> list[str]:
    return [p.pattern for p in _BANNED if p.search(html_text)]


# F98: catches a raw indicator code (e.g. "D2", "S10") slipping through as a
# tile label instead of the plain-English label it should have been mapped to.
_TILE_CODE = re.compile(r"\b[DSPX]\d{1,2}\b")


def lint_tile_labels(model) -> list[str]:
    return [o["metric_label"] for o in (model.get("agenda") or [])
            if _TILE_CODE.search(o.get("metric_label") or "")]


def _chip(a) -> str:
    sub = ""
    if a["lagging"]:
        sub = (f"<small>steps down after two calm days; today's raw read was"
               f" {e(a['raw_word'])}</small>")
    return (f'<a class="chip status-{e(a["css"])}" href="how/alert.html">'
            f'{_CHIP_ICON.get(a["word"], "")} Attention: {e(a["word"])}{sub}</a>')


def _masthead(m) -> str:
    stale = ""
    if m["stale"]:
        stale = (f'<p class="stalestrip status-watch">! Signal checks paused since'
                 f' {e(m["last_check"])}</p>')
    return (
        f'{_chip(m["attention"])}'
        f'<p class="crumb">AI market › Chips layer › {e(m["category_label"])}</p>'
        f'<h1>{e(m["category_label"].upper())} — Executive Brief</h1>'
        f'<p class="muted">Tracks the merchant AI-GPU market — demand, supply,'
        f' pricing, competition — and what it means one layer down: wafers,'
        f' packaging, memory.</p>'
        f'<p class="asof">Monthly read: {e(m["month_label"])} (revision'
        f' {m["revision"]}) · Last signal check: {e(m["last_check"])}</p>'
        f'{stale}')


_RATING_DOT = {"very strong": "#2e7d32", "strong": "#2e7d32", "mixed": "#f9a825",
               "moderate": "#f9a825", "weak": "#ef6c00"}
_DELTA_GOOD = {"rising": "#1e7a34", "falling": "#c0632a"}  # default green up / amber down


def _slot_label_to_id():
    try:
        return {s["label"]: s["id"] for s in load_slots()}
    except Exception:
        return {}


_SLOT_LABEL_TO_ID = _slot_label_to_id()


def _verdict(m) -> str:
    s = m["status"]
    dash = f" / {e(s['direction'])}" if s.get("direction") else ""
    return (f'<div class="rating-label">{e(s["rating"])}{dash}</div>'
            f'<p class="brief-two">{e(m.get("brief_two") or "")}</p>')


def _kpi_cards(m) -> str:
    if len(m.get("agenda") or []) < 3:
        return ""
    cards = []
    for o in m["agenda"]:
        sid = _SLOT_LABEL_TO_ID.get(o["slot_label"], "")
        dim = SLOT_TO_DIMENSION.get(sid, "")
        onclick = f"openDD('{e(dim)}')" if dim else ""
        col = _DELTA_GOOD.get(o.get("trend_word"), "#999")
        cards.append(
            f'<div class="kcard" onclick="{onclick}">'
            f'<div class="kq">{e(o["slot_label"])}</div>'
            f'<div class="km">{e(o["metric_label"])}</div>'
            f'<div class="kv">{e(o["display"])}</div>'
            f'<div class="kd" style="color:{col}">{e(o["trend_word"])}</div></div>')
    return f'<div class="kcards">{"".join(cards)}</div>'


def _chart(m) -> str:
    c = m.get("chart") or {}
    dem, sup = c.get("demand") or [], c.get("supply") or []
    if len(dem) < 2 or len(sup) < 2:
        return ""
    xs = dem + sup
    mn, mx = min(xs), max(xs)
    rng = (mx - mn) or 1.0
    W, H = 520, 150

    def pts(series):
        return " ".join(
            f"{i/(len(series)-1)*W:.0f},{H-6-(y-mn)/rng*(H-16):.0f}"
            for i, y in enumerate(series))
    return (
        '<div class="ddchart-cap">Demand vs supply momentum</div>'
        f'<svg viewBox="0 0 {W} {H}" width="100%" height="170" class="ddchart">'
        f'<polyline fill="none" stroke="#4f8cff" stroke-width="2.5" points="{pts(dem)}"/>'
        f'<polyline fill="none" stroke="#e5843b" stroke-width="2" stroke-dasharray="5 3" points="{pts(sup)}"/>'
        '</svg><div class="ddchart-legend">'
        '<span style="color:#4f8cff">&#9473; demand</span> &nbsp; '
        '<span style="color:#e5843b">&#9548; supply</span></div>')


def _dims_list(m) -> str:
    rows = []
    for d in m["dimensions"]:
        dot = _RATING_DOT.get((d["rating"] or "").lower(), "#999")
        glyph = _DIR_GLYPH.get(d["direction"], "")
        rows.append(
            f'<div class="dimrow" onclick="openDD(\'{e(d["name"])}\')">'
            f'<span class="ddot" style="background:{dot}"></span> {e(d["name"])}'
            f'<span class="spacer"></span><b>{e(d["rating"])} {glyph}</b>'
            ' <span style="color:#8a6d3b">&#8594;</span></div>')
    return (f'<div class="ddchart-cap" style="margin-bottom:.4rem">Six dimensions</div>'
            f'<div class="dimlist">{"".join(rows)}</div>')


def _agenda(m) -> str:
    if len(m["agenda"]) < 3:
        return ""
    tiles = []
    for o in m["agenda"]:
        was = f'<div class="meta">(was: {e(o["was"])})</div>' if o["was"] else ""
        delta = (f'<div class="meta">{e(o["delta_line"])}</div>'
                 if o.get("delta_line") else "")
        tiles.append(
            f'<div class="tile"><div class="k">{e(o["slot_label"])}</div>'
            f'<div class="m">{e(o["metric_label"])}</div>'
            f'<div class="v">{e(o["display"])}</div>'
            f'<div class="t">{e(o["trend_word"])}</div>'
            f'<div class="meta">as of {e(o["as_of"])} · {e(o["source"])}</div>'
            f'{delta}{was}</div>')
    return f'<div class="kpis">{"".join(tiles)}</div>'


def _tsmc(m) -> str:
    if not m["tsmc"]:
        return ""
    items = []
    for ln in m["tsmc"]:
        tags = " ".join(f'<span class="tag">{e(d)}</span>' for d in ln["dims"])
        links = " ".join(f'<a href="appendix.html#f-{e(f)}">evidence</a>'
                         for f in ln["finding_ids"][:1])
        items.append(f"<li>{e(ln['text'])} {tags} {links}</li>")
    return f'<h2>What this means for TSMC</h2><ul>{"".join(items)}</ul>'


def _calls(m) -> str:
    c = m["calls"]
    if not c["rows"]:
        return ('<h2>Standing calls</h2><p class="muted">No standing calls yet;'
                ' first reads are being established.</p>')
    rows = []
    for r in c["rows"]:
        verdict = f'{e(r["verdict"])} {e(r["glyph"])}'.strip()
        rows.append(
            f'<tr><td>{e(r["title"])}</td><td class="tag">{e(r["lens"])}</td>'
            f'<td>{e(r["conviction"])}</td><td>{verdict}</td>'
            f'<td style="text-align:right">{r["streak"]}</td>'
            f'<td class="trigger">{e(r["trigger"])}</td></tr>')
    return (
        '<h2>Standing calls</h2><div class="scroll"><table class="calls">'
        '<tr><th>Call</th><th>Lens</th><th>Conviction</th><th>Verdict</th>'
        '<th>Held</th><th>What would change our mind</th></tr>'
        f'{"".join(rows)}</table></div>'
        f'<p class="muted">All {c["total"]} calls, including {c["provisional"]}'
        f' provisional →</p>')


def _strip(m) -> str:
    if not m["strip"]:
        return ""
    items = "".join(
        f'<li><span class="d">{e(x["date"])}</span> {e(x["text"])}'
        f' <span class="muted">({e(x["source"])})</span></li>'
        for x in m["strip"])
    return f'<h2>Latest signal</h2><ul class="strip">{items}</ul>'


def _dims(m) -> str:
    tiles = []
    for d in m["dimensions"]:
        cap = '<div class="meta">confidence capped</div>' if d["capped"] else ""
        glyph = _DIR_GLYPH.get(d["direction"], "")
        tiles.append(
            f'<div class="tile"><div class="k">{e(d["name"])}</div>'
            f'<div class="v">{e(d["rating"])}</div>'
            f'<div class="t">{e(d["direction"])} {glyph} ·'
            f' {e(d["confidence"])} confidence</div>'
            f'<div class="meta">{e(d["sentence"])}</div>{cap}'
            f'<a class="how" href="appendix.html#dim-{e(d["name"])}">how was this'
            f' rated?</a></div>')
    return f'<h2>The six dimensions</h2><div class="dims">{"".join(tiles)}</div>'


def _footer(m) -> str:
    ev = m["evidence"]
    return (
        f'<div class="footer"><p>{ev["n"]} signals · median observation'
        f' {e(ev["median"])} · oldest {e(ev["oldest"])} · {ev["primary"]}'
        f' trace to primary sources · <a href="appendix.html">full appendix'
        f' →</a></p><p>Built by an autonomous research agent; every claim on'
        f' this page links to its evidence. Between signal checks the monthly read'
        f' stands.</p></div>')


def render_brief(model) -> str:
    body = "".join([
        _masthead(model),
        _verdict(model),
        _kpi_cards(model),
        '<div class="dash2"><div>', _chart(model), '</div><div>',
        _dims_list(model), '</div></div>',
        _strip(model),
        _footer(model),
        deepdive_json(model.get("deepdive") or {}),
        render_deepdive_panel(),
    ])
    return page(f"{model['category_label']} — Executive Brief ·"
                f" {model['month_label']}", body)
