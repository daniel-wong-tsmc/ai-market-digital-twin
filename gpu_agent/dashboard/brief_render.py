"""F97 Executive Brief HTML — blocks A-H per the 2026-07-16 format spec (v5)."""
from __future__ import annotations

import html
import re

from .site_render import page

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
.narrative { max-width: 66ch; }
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


def lint_exec_copy(html_text: str) -> list[str]:
    return [p.pattern for p in _BANNED if p.search(html_text)]


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
        f'<h1>{e(m["category_label"]).upper()} — Executive Brief</h1>'
        f'<p class="muted">Tracks the merchant AI-GPU market — demand, supply,'
        f' pricing, competition — and what it means one layer down: wafers,'
        f' packaging, memory.</p>'
        f'<p class="asof">Monthly read: {e(m["month_label"])} (revision'
        f' {m["revision"]}) · Last signal check: {e(m["last_check"])}</p>'
        f'{stale}')


def _verdict(m) -> str:
    s = m["status"]
    dash = f" / {e(s['direction'])}" if s["direction"] else ""
    return (f'<p class="hero"><span class="rating">{e(s["rating"])}{dash}</span>'
            f' — {e(s["reason"])}</p>'
            f'<p class="narrative">{e(m["narrative"])}</p>')


def _agenda(m) -> str:
    if len(m["agenda"]) < 3:
        return ""
    tiles = []
    for o in m["agenda"]:
        was = f'<div class="meta">(was: {e(o["was"])})</div>' if o["was"] else ""
        tiles.append(
            f'<div class="tile"><div class="k">{e(o["slot_label"])}</div>'
            f'<div class="m">{e(o["metric_label"])}</div>'
            f'<div class="v">{e(o["display"])}</div>'
            f'<div class="t">{e(o["trend_word"])}</div>'
            f'<div class="meta">as of {e(o["as_of"])} · {e(o["source"])}</div>'
            f'{was}</div>')
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
        verdict = f'{e(r["verdict"])} {r["glyph"]}'.strip()
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
    body = "".join([_masthead(model), _verdict(model), _agenda(model),
                    _tsmc(model), _calls(model), _strip(model), _dims(model),
                    _footer(model)])
    return page(f"{model['category_label']} — Executive Brief ·"
                f" {model['month_label']}", body)
