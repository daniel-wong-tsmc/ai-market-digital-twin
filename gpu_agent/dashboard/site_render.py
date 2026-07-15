"""F95 site renderer — static, deterministic, self-contained pages (spec §3/§5).

No wall-clock, no LLM, no external assets beyond the sibling style.css. Only
<details> tags for expand/collapse — no scripting."""
from __future__ import annotations

from gpu_agent import bands as _bands

from .render import esc
from .site_model import rule_plain

HOW_LINKS = {"alert": "how/alert.html", "demand": "how/demand.html",
             "supply": "how/supply.html", "gap": "how/gap.html",
             "featured": "how/featured.html"}

_TILE_SIDES = ("demand", "supply", "gap")

SITE_CSS = """
:root { --ink:#1a1a1a; --muted:#666; --line:#ddd; --green:#2e7d32; --yellow:#f9a825;
        --orange:#ef6c00; --red:#c62828; }
* { box-sizing: border-box; }
body { font: 16px/1.5 system-ui, sans-serif; color: var(--ink); margin: 0 auto;
       max-width: 60rem; padding: 1.5rem; }
a { color: #0b57d0; }
h1 { font-size: 1.4rem; margin: .2rem 0; }
h2 { font-size: 1.1rem; margin-top: 2rem; border-top: 1px solid var(--line);
     padding-top: 1rem; }
.crumb, .asof, .muted { color: var(--muted); font-size: .9rem; }
.alertline { font-size: 1.15rem; margin: 1rem 0 .5rem; }
.dot { display: inline-block; width: .8em; height: .8em; border-radius: 50%;
       vertical-align: baseline; }
.dot.green{background:var(--green)} .dot.yellow{background:var(--yellow)}
.dot.orange{background:var(--orange)} .dot.red{background:var(--red)}
.tiles { display: flex; flex-wrap: wrap; gap: .8rem; margin: 1rem 0; }
.tile { flex: 1 1 12rem; border: 1px solid var(--line); border-radius: .5rem;
        padding: .8rem; }
.tile .k { font-size: .8rem; letter-spacing: .05em; color: var(--muted);
           text-transform: uppercase; }
.tile .v { font-size: 1.25rem; margin: .2rem 0; }
.tile .how { font-size: .85rem; }
table { border-collapse: collapse; width: 100%; }
.scroll { overflow-x: auto; }
th, td { text-align: left; padding: .35rem .5rem; border-bottom: 1px solid var(--line); }
ul { padding-left: 1.2rem; }
details { margin: .3rem 0; }
.callmore { color: var(--muted); }
"""


def page(title: str, body: str, depth: int = 0) -> str:
    css_href = ("../" * depth) + "style.css"
    return ("<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
            f"<title>{esc(title)}</title>\n"
            f"<link rel=\"stylesheet\" href=\"{css_href}\">\n"
            f"</head>\n<body>\n{body}\n</body>\n</html>\n")


def render_index_redirect(target_href: str, label: str) -> str:
    body = (f'<meta http-equiv="refresh" content="0; url={esc(target_href)}">\n'
            f'<p>AI market site - continue to <a href="{esc(target_href)}">'
            f"{esc(label)}</a>.</p>")
    return page("AI market", body)


def _dot(color: str) -> str:
    return f'<span class="dot {esc(color)}"></span>'


def _alert_line(alert) -> str:
    was = (f' (was {esc(alert["prior"].upper())})' if alert["prior"]
           else " (first tracked run)")
    return (f'<p class="alertline">{_dot(alert["color"])} '
            f'<strong>{esc(alert["color"].upper())}</strong>{was} '
            f'<a class="how" href="{HOW_LINKS["alert"]}">How was this decided?</a></p>')


def _tiles(model) -> str:
    out = ['<div class="tiles">']
    for side, tile in zip(_TILE_SIDES, model["tiles"]):
        out.append(
            f'<div class="tile"><div class="k">{esc(tile["label"])}</div>'
            f'<div class="v">{esc(tile["band"])}</div>'
            f'<a class="how" href="{HOW_LINKS[side]}">how?</a></div>')
    f = model.get("featured")
    if f is not None:
        out.append(
            f'<div class="tile"><div class="k">Worth watching: {esc(f["plain_label"])}'
            f'</div><div class="v">{esc(f["display"])}</div>'
            f'<div class="muted">{esc(f["delta_phrase"])}</div>'
            f'<a class="how" href="{HOW_LINKS["featured"]}">why this number?</a></div>')
    out.append("</div>")
    return "\n".join(out)


def _what_changed(model) -> str:
    items = "".join(f'<li><strong>{esc(w["phrase"])}:</strong> {esc(w["text"])}</li>'
                    for w in model["what_changed"])
    return f"<h2>What changed</h2>\n<ul>{items or '<li>No change lines this run.</li>'}</ul>"


def _implication(model) -> str:
    imp = model.get("implication")
    if not imp:
        return ""
    items = "".join(f"<li>{esc(l)}</li>" for l in imp["lines"])
    return f"<h2>For TSMC</h2>\n<ul>{items}</ul>"


def _calls(model) -> str:
    calls = model["calls"]
    if not calls:
        return "<h2>The top calls</h2>\n<p class=\"muted\">No tracked calls this run.</p>"
    top, rest = calls[:5], calls[5:]
    blocks = []
    for c in top:
        breaks = (f'<div class="muted">breaks if: {esc(c["breaks_if"])}</div>'
                  if c.get("breaks_if") else "")
        blocks.append(f'<p><strong>{esc(c["name"])}</strong> - {esc(c["plain"])}'
                      f"{breaks}</p>")
    more = ""
    if rest:
        lines = "".join(f'<li class="callmore">{esc(c["name"])} - {esc(c["plain"])}</li>'
                        for c in rest)
        more = f"<ul>{lines}</ul>"
    return f'<h2>The top calls ({len(top)} of {len(calls)})</h2>\n' + "\n".join(blocks) + more


def _why(model) -> str:
    paras = "".join(f'<p><strong>{esc(w["topic"].capitalize())}:</strong> '
                    f'{esc(w["text"])}</p>' for w in model["why"])
    return f"<h2>Why it reads this way</h2>\n{paras}"


def render_category_page(model) -> str:
    title = model["category_label"]
    body = [
        f'<p class="crumb">{esc(title)} &middot; Chips layer &middot; AI market</p>',
        f"<h1>{esc(model['category_id'].rsplit('.', 1)[-1].replace('-', ' ').upper())}</h1>",
        f'<p class="asof">as of {esc(model["as_of"])}</p>',
        _alert_line(model["alert"]),
        _tiles(model),
        f'<p>Main limiting factor: <strong>{esc(model["headline"]["limiting_factor"])}'
        "</strong></p>",
        _what_changed(model),
        _implication(model),
        _calls(model),
        _why(model),
        '<h2 id="appendix-links">Appendix</h2>',
        '<p><a href="appendix.html">Raw scores, every finding with its evidence, and the '
        "run history</a></p>",
    ]
    return page(f"{title} - {model['as_of']}", "\n".join(b for b in body if b))


_LADDER = [
    ("GREEN", "nothing on the watchlist moved this week"),
    ("YELLOW", "one thing moved: the gap band changed, a high-confidence call moved, the "
               "main limiting factor changed, or two calls moved together"),
    ("ORANGE", "two yellow-level things happened at once, a high-confidence call broke, or "
               "demand worsened while the gap moved toward glut"),
    ("RED", "a confirmed structural break: a high-confidence call broke AND the gap band "
            "flipped in the same week"),
]


def render_how_alert(model) -> str:
    a = model["alert"]
    ladder = "".join(f"<li><strong>{c}</strong>: {esc(d)}</li>" for c, d in _LADDER)
    fired = ("".join(f"<li>{esc(rule_plain(t))}</li>" for t in a["triggers"])
             or "<li>none - no rule fired</li>")
    flap = ""
    if a["raw"] != a["color"]:
        flap = (f'<p>Today\'s raw read was <strong>{esc(a["raw"].upper())}</strong>. The '
                "shown color steps down only after two calm runs in a row, so the page "
                f'still shows {esc(a["color"].upper())}.</p>')
    was = esc(a["prior"].upper()) if a["prior"] else "no prior run"
    body = (
        "<h1>How the alert color was decided</h1>"
        f'<p>Today: {_dot(a["color"])} <strong>{esc(a["color"].upper())}</strong> '
        f"(before: {was})</p>"
        "<h2>The ladder (first match from the top wins)</h2>"
        f"<ul>{ladder}</ul>"
        "<h2>What fired this run</h2>"
        f"<ul>{fired}</ul>" + flap +
        '<p><a href="../index.html">Back to the page</a></p>')
    return page("How the alert was decided", body, depth=1)


def _band_scale(value: float) -> str:
    words = ["contracting"] + [w for _, w in reversed(_bands.BANDS)]
    cur = _bands.band_word(value)
    cells = "".join(
        f"<td>{'&#9679; ' if w == cur else ''}{esc(w)}</td>" for w in words)
    return f'<div class="scroll"><table><tr>{cells}</tr></table></div>'


def _contrib_table(rows, side_key) -> str:
    live = [r for r in rows if r[side_key] != 0]
    if not live:
        return "<p>No scoring findings pulled this side this cycle.</p>"
    out = ['<div class="scroll"><table><tr><th>What</th><th>Weight</th>'
           "<th>Strength (1-3)</th><th>Pull</th></tr>"]
    for r in live:
        pull = f'{r[side_key]:+.3f}'
        # F95 item 5: only http(s) evidence URLs become links — esc() stops attribute
        # breakout but not a clickable javascript: URL, so gate on scheme too.
        ev = "".join(
            f'<li>{esc(e["source"])} ({esc(e["date"])}, {esc(e["tier"])} source)'
            + (f' - <a href="{esc(e["url"])}">link</a>'
               if e["url"] and e["url"].startswith(("http://", "https://")) else "")
            + "</li>" for e in r["evidence"])
        out.append(
            f'<tr><td><details><summary>{esc(r["label"])} ({esc(r["entity"])})</summary>'
            f'<p>{esc(r["statement"])}</p><ul>{ev or "<li>no evidence rows</li>"}</ul>'
            f'</details></td><td>{r["weight"]:g}</td><td>{r["magnitude"]}</td>'
            f"<td>{pull}</td></tr>")
    out.append("</table></div>")
    return "".join(out)


def render_how_tile(model, side) -> str:
    ds = model["demand_supply"]
    if side == "gap":
        body = (
            "<h1>How the gap tile was computed</h1>"
            "<p>The gap score is simply demand minus supply:</p>"
            f'<p><strong>{ds["dmi"]:+.2f} (demand) minus {ds["smi"]:+.2f} (supply) '
            f'= {ds["sdgi"]:+.2f}</strong>, currently '
            f'{esc(ds["sdgi_direction"] or "balanced")}.</p>'
            "<p>To see what moved each side: "
            '<a href="demand.html">demand</a> &middot; '
            '<a href="supply.html">supply</a></p>'
            f"{_band_scale(ds['sdgi'])}"
            '<p><a href="../index.html">Back to the page</a></p>')
        return page("How the gap was computed", body, depth=1)
    key = "dmi" if side == "demand" else "smi"
    side_key = f"{side}_contribution"
    # F95 item 1 (label honestly): the contribution rows below are this cycle's raw
    # finding-level arithmetic; the headline tile blends that with longer-horizon
    # signals. State both numbers and say why they can differ, so the page never lets
    # the parts silently contradict the whole.
    total = sum(r[side_key] for r in model["contributions"])
    body = (
        f"<h1>How the {side} tile was computed</h1>"
        f"<p>The {side} score this run is <strong>{ds[key]:+.2f}</strong>. It lands on "
        "this five-word scale:</p>"
        f"{_band_scale(ds[key])}"
        "<h2>What pulled it (weight &times; direction &times; strength / 3, from this "
        "cycle's findings)</h2>"
        f"{_contrib_table(model['contributions'], side_key)}"
        f"<p>These pulls add up to <strong>{total:+.3f}</strong> for this cycle's "
        "findings. The tile above blends this with longer-horizon signals, so the "
        f"headline score ({ds[key]:+.2f}) can differ.</p>"
        "<p>Every row expands to the finding behind it and each piece of evidence: "
        "who published it, when, and whether it is a primary source.</p>"
        '<p><a href="../index.html">Back to the page</a></p>')
    return page(f"How the {side} tile was computed", body, depth=1)


def render_how_featured(model) -> str:
    f = model["featured"]
    note = f'<p class="muted">{esc(f["honesty_note"])}</p>' if f["honesty_note"] else ""
    src = ("Median of each cloud provider's median price, nearest stored day."
           if f["metric_id"].startswith("gpu-rent")
           else "From the desk's own scoring pipeline for this cycle.")
    body = (
        f'<h1>Why this number: {esc(f["plain_label"])}</h1>'
        f'<p><strong>{esc(f["display"])}</strong> - {esc(f["delta_phrase"])}</p>'
        f'<p>{esc(f["reason_text"])}</p>'
        "<p>The page shows one featured number per run, picked by a fixed rule: first, a "
        "metric tied to whatever set off today's alert; otherwise the metric that moved "
        "the most since the last run; otherwise a standing order with price first.</p>"
        f'<p>How to read it: {esc(f["how_to_read"])}</p>'
        f"<p>Source: {esc(src)}</p>" + note +
        '<p><a href="../index.html">Back to the page</a></p>')
    return page("Why this number", body, depth=1)


def render_appendix(model) -> str:
    t = model["trend"]
    head = "".join(f"<th>{esc(d)}</th>" for d in t["dates"])
    def row(label, xs):
        cells = "".join(f"<td>{x:+.2f}</td>" for x in xs)
        return f"<tr><td>{esc(label)}</td>{cells}</tr>"
    findings = "".join(
        f'<li><details><summary>{esc(f["plain"])}</summary>'
        f'<p class="muted">observed {esc(f.get("observed_at") or "n/a")} - '
        f'{esc(f.get("source_name") or "unnamed source")} ({esc(f.get("tier") or "?")})'
        "</p></details></li>"
        for f in model["top_signals"])
    runs = "".join(f'<li>{esc(r["date"])}: {r["findings"]} findings, {r["sources"]} '
                   "sources</li>" for r in model["runs"])
    body = (
        "<h1>Appendix</h1>"
        "<h2>Raw scores by run</h2>"
        f'<div class="scroll"><table><tr><th></th>{head}</tr>'
        f'{row("Demand", t["dmi"])}{row("Supply", t["smi"])}{row("Gap", t["sdgi"])}'
        "</table></div>"
        "<p>These raw scores read as direction, not level - the words on the main page "
        "are the honest summary.</p>"
        "<h2>Every ranked signal this run</h2>"
        f"<ul>{findings}</ul>"
        "<h2>Run history</h2>"
        f"<ul>{runs}</ul>"
        '<p><a href="index.html">Back to the page</a></p>')
    return page("Appendix", body, depth=0)
