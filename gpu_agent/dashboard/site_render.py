"""F95 site renderer — static, deterministic, self-contained pages (spec §3/§5).

No wall-clock, no LLM, no external assets beyond the sibling style.css. Only
<details> tags for expand/collapse — no scripting."""
from __future__ import annotations

from .render import esc

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


def page(title: str, body: str) -> str:
    return ("<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
            f"<title>{esc(title)}</title>\n"
            "<link rel=\"stylesheet\" href=\"style.css\">\n"
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
