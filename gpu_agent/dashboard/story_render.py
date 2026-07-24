"""F101 Phase A: render the narrative category page."""
from __future__ import annotations

import json
import re as _re

from gpu_agent.dashboard.gap_chart import render_gap_svg, spark_svg
from gpu_agent.dashboard.render import esc
from gpu_agent.dashboard.site_render import page as _page


def evidence_json(evidence: dict) -> str:
    payload = json.dumps(evidence, ensure_ascii=True).replace("<", "\\u003c")
    return f'<script type="application/json" id="ev-data">{payload}</script>'


_PANEL = r"""<script>(function(){
var data={};try{data=JSON.parse(document.getElementById('ev-data').textContent);}catch(e){}
function el(t,c,x){var n=document.createElement(t);if(c)n.className=c;if(x!=null)n.textContent=x;return n;}
function spark(vals){if(!vals||vals.length<2)return null;
var w=120,h=28,lo=Math.min.apply(null,vals),hi=Math.max.apply(null,vals),sp=(hi-lo)||1,p=[];
for(var i=0;i<vals.length;i++){p.push((4+i*(w-8)/(vals.length-1)).toFixed(1)+','+(h-4-(vals[i]-lo)/sp*(h-8)).toFixed(1));}
var s=document.createElementNS('http://www.w3.org/2000/svg','svg');
s.setAttribute('viewBox','0 0 '+w+' '+h);s.setAttribute('class','ev-spark');
var pl=document.createElementNS('http://www.w3.org/2000/svg','polyline');
pl.setAttribute('points',p.join(' '));pl.setAttribute('fill','none');
pl.setAttribute('stroke','currentColor');pl.setAttribute('stroke-width','1.5');
s.appendChild(pl);return s;}
var scrim=el('div','ev-scrim'),panel=el('aside','ev-panel');
scrim.onclick=closeEV;document.body.appendChild(scrim);document.body.appendChild(panel);
window.openEV=function(k){var d=data[k];if(!d)return;panel.innerHTML='';
var x=el('button','ev-close','×');x.onclick=closeEV;panel.appendChild(x);
panel.appendChild(el('h3','ev-title',d.title||''));
panel.appendChild(el('p','ev-claim',d.claim_text||''));
if(d.series&&d.series.length>1){var sv=spark(d.series);if(sv)panel.appendChild(sv);}
var list=el('div','ev-chain');list.appendChild(el('div','ev-step','What we collected → where it came from'));
var finds=d.findings||[];
if(finds.length){finds.forEach(function(f){var row=el('div','ev-row');
row.appendChild(el('span','ev-src',(f.source||'')+' · '+(f.date||'')));
row.appendChild(el('span','ev-take',f.take||''));
if(f.url&&/^https?:/.test(f.url)){var a=el('a','ev-link','↗');
a.href=encodeURI(f.url);a.target='_blank';a.rel='noopener';row.appendChild(a);}
list.appendChild(row);});}else{list.appendChild(el('div','ev-empty','No linked sources for this yet.'));}
panel.appendChild(list);
if(d.explore&&(/^https?:/i.test(d.explore)||!/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(d.explore))&&!/^\/\//.test(d.explore)){var ex=el('a','ev-explore','see everything we have →');
ex.href=encodeURI(d.explore);panel.appendChild(ex);}
scrim.classList.add('on');panel.classList.add('on');};
window.closeEV=function(){scrim.classList.remove('on');panel.classList.remove('on');};
document.addEventListener('keydown',function(e){if(e.key==='Escape')closeEV();});
document.addEventListener('click',function(e){var t=e.target.closest&&e.target.closest('[data-ev]');
if(t){e.preventDefault();openEV(t.getAttribute('data-ev'));}});
})();</script>"""


def render_evidence_panel() -> str:
    return _PANEL


STORY_CSS = """
.st-page{max-width:860px;margin:0 auto;padding:0 16px;color:#1c1c1c;
 background:#fff;font-family:Georgia,'Times New Roman',serif}
.st-head{position:sticky;top:0;background:#fff;padding:18px 0 10px;
 border-bottom:1px solid #eee;z-index:20}
.st-head h1{font-size:38px;line-height:1.08;margin:0 0 8px;font-weight:800}
.st-head.condensed h1{font-size:19px;margin:0}
.st-head.condensed .st-deck,.st-head.condensed .st-date{display:none}
.st-deck{font-size:17px;color:#444;margin:0 0 4px}
.st-date{font-size:12px;color:#888;text-transform:uppercase;letter-spacing:.04em}
svg.gapchart{width:100%;height:auto;overflow:visible}
.gc-tick{font-size:11px;fill:#666;font-family:system-ui,sans-serif}
.gc-axis{font-size:11px;fill:#888;font-style:italic}
.gc-gap{font-size:12px;font-weight:700;fill:#a33}
.gc-note{font-size:11px;fill:#333;font-family:system-ui,sans-serif}
.gc-leader{stroke:#999;stroke-width:1}
.gc-i{fill:#1f7a8c}
.st-srcline{font-size:11px;color:#888;font-style:italic;margin:4px 0 18px}
.st-band{display:flex;gap:10px;flex-wrap:wrap;margin:12px 0 26px;
 font-family:system-ui,sans-serif}
.st-chip{position:relative;border:1px solid #ddd;border-radius:8px;
 padding:8px 12px;background:#fafafa;text-align:left;cursor:pointer;flex:1 1 140px;display:flex;flex-direction:column}
.st-chip-anchor{border:1.5px solid #333;background:#fff8ef}
.st-pin::before{content:'\\2693';font-size:10px;margin-right:4px}
.st-chip .spark{align-self:flex-start}
.st-chip .st-val{font-size:17px;font-weight:700}
.st-chip .st-lab{font-size:12px;color:#555}
.st-chip .st-cap{font-size:10px;color:#999}
.st-dot{display:inline-block;width:15px;height:15px;border-radius:50%;
 color:#fff;font-size:10px;line-height:15px;text-align:center;font-style:normal}
.st-dot-amber{background:#d69b26}.st-dot-terracotta{background:#b0562e}
.st-dot-teal{background:#1f7a8c}.st-dot-green{background:#3d8b4f}
.st-tip{display:none;position:absolute;left:0;top:100%;z-index:30;width:230px;
 background:#1c1c1c;color:#fff;font-size:12px;padding:8px 10px;border-radius:6px}
.st-chip:hover .st-tip,.st-chip:focus .st-tip{display:block}
.ev-scrim{display:none;position:fixed;inset:0;background:rgba(0,0,0,.25);z-index:40}
.ev-scrim.on{display:block}
.ev-panel{position:fixed;top:0;right:-360px;width:340px;height:100%;z-index:41;
 background:#fff;border-left:1px solid #ddd;padding:18px;overflow-y:auto;
 transition:right .2s;font-family:system-ui,sans-serif}
.ev-panel.on{right:0}
.ev-close{float:right;border:0;background:none;font-size:22px;cursor:pointer}
.ev-title{font-size:16px;margin:0 0 6px}.ev-claim{font-size:13px;color:#444}
.ev-step{font-size:11px;text-transform:uppercase;color:#888;margin:10px 0 4px}
.ev-row{border-top:1px solid #eee;padding:6px 0;font-size:12px;display:flex;
 gap:6px;align-items:baseline}
.ev-src{color:#666;white-space:nowrap}.ev-take{flex:1}
.ev-empty{padding:6px 0;font-size:12px;color:#888;font-style:italic}
.ev-link{color:#1f7a8c;text-decoration:none}
.ev-explore{display:block;margin-top:12px;font-size:13px;color:#1f7a8c}
.ev-spark{color:#1f7a8c;display:block;margin:6px 0}
a.ev{cursor:pointer;text-decoration:underline dotted}
@media (max-width:640px){.st-head h1{font-size:27px}
 .st-band{flex-direction:column}.ev-panel{width:88%}}
.st-scene{border-left:3px solid #eee;padding:4px 0 10px 18px;margin:0 0 8px;position:relative}
.st-scene .st-dot{position:absolute;left:-9px;top:6px}
.st-storyhead{font-size:14px;text-transform:uppercase;letter-spacing:.06em;color:#888}
.st-related{font-size:12px;color:#666}
.st-related a{color:#1f7a8c;margin-right:10px}
.st-visual{margin:8px 0;color:#1f7a8c}
.st-closing{border-top:1px solid #eee;padding:14px 0;font-size:13px}
.st-arch{display:inline-block;border:1px solid #ddd;border-radius:14px;padding:2px 10px;margin:0 6px 6px 0;font-size:12px;color:#555}
.st-explore{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0}
.st-tile{flex:1 1 150px;border:1px solid #ddd;border-radius:8px;padding:10px;text-decoration:none;color:#1c1c1c;font-size:12px}
.st-tile b{display:block;font-size:14px}
.st-foot{font-size:11px;color:#999;padding:16px 0;border-top:1px solid #eee}
"""


def _headline_block(model: dict) -> str:
    return (f'<header class="st-head"><h1>{esc(model["headline"])}</h1>'
            f'<p class="st-deck">{esc(model["deck"])}</p>'
            f'<p class="st-date">{esc(model["dateline"])}</p></header>')


def _chart_block(model: dict) -> str:
    if not model.get("gap"):
        # Not enough monthly history to draw the demand-vs-supply chart --
        # say so plainly instead of rendering nothing, which reads as broken.
        return ('<section class="st-chart"><p class="st-srcline">Not enough '
                'monthly history yet to draw the demand-vs-supply chart.'
                '</p></section>')
    months = model["gap"]["months"]
    y0, y1 = months[0]["key"][:4], months[-1]["key"][:4]
    if y0 == y1:
        span = f'{months[0]["label"]}–{months[-1]["label"]} {y1}'
    else:
        # A window crossing New Year (e.g. Nov 2026 - Feb 2027) must carry
        # the year on both ends -- otherwise "Nov" silently reads as if it
        # were the same year as "Feb".
        span = f'{months[0]["label"]} {y0}–{months[-1]["label"]} {y1}'
    # F101c Task 7: the "the gap, this week" label opens the verdict-history
    # page. render_gap_svg lives in gap_chart.py (outside this lane's scope), so
    # the label is wrapped here in an SVG <a> as a pure link-target addition —
    # the SVG's own structure is untouched.
    svg = render_gap_svg(model["gap"], model.get("callouts"))
    svg = _re.sub(r'(<text[^>]*class="gc-gap"[^>]*>the gap, this week</text>)',
                  r'<a href="history.html">\1</a>', svg)
    return (f'<section class="st-chart">'
            f'{svg}'
            f'<p class="st-srcline">Source: agent-tracked orders and shipment '
            f'data; company filings · {esc(span)}</p></section>')


def _chip_html(c: dict, anchored: bool = False) -> str:
    marker = ('<i class="st-pin"></i>' if anchored else
              (f'<i class="st-dot st-dot-{["amber","terracotta","teal","green"][(c["scene"]-1)%4]}">'
               f'{c["scene"]}</i>' if c.get("scene") else ""))
    cls = "st-chip st-chip-anchor" if anchored else "st-chip"
    # A categorical chip (see story_model._CHIP_DEFS) carries no arrow --
    # avoid leaving a stray trailing space after the value in that case.
    val = f'{esc(c["value"])} {c["arrow"]}' if c["arrow"] else esc(c["value"])
    return (f'<button class="{cls}" data-ev="{esc(c["claim"])}">'
            f'{marker}<span class="st-val">{val}</span>'
            f'<span class="st-lab">{esc(c["label"])}</span>'
            f'{spark_svg(c["spark"])}'
            f'<span class="st-cap">{esc(c["caption"])}</span>'
            f'<span class="st-tip">{esc(c["tip"])}</span></button>')


def _kpi_band(model: dict) -> str:
    k = model["kpis"]
    chips = []
    if k.get("anchored"):
        chips.append(_chip_html(k["anchored"], anchored=True))
    chips += [_chip_html(c) for c in k["picks"]]
    if not chips:
        # No chips to show (e.g. a category with no series data at all) --
        # an empty band still carrying the "tap any number" caption reads as
        # broken. Suppress the whole band and its caption.
        return ""
    cap = ('<p class="st-srcline">picked by today\'s story · '
           'tap any number to ask: says who?</p>')
    return f'<section class="st-band">{"".join(chips)}</section>{cap}'


_CONDENSE = ("<script>(function(){var h=document.querySelector('.st-head');"
             "if(!h)return;addEventListener('scroll',function(){"
             "h.classList.toggle('condensed',scrollY>120);});})();</script>")


def render_condense_script() -> str:
    return _CONDENSE


_BANNED_STORY = ["DMI", "SMI", "momentum", "strengthening", "tightening",
                 "accelerating", "allocation", "doctrine", "robust", "leverage"]

# Non-greedy "<script>...</script>" stripping stops at the *first* literal
# "</script>" it finds, so a script whose own body contains that literal
# text (e.g. inside a JS string) would end the strip early and leave the
# rest of the script scanned as page prose. The lookahead below rejects a
# candidate close tag whenever another "</script>" follows before the next
# "<script" open tag, forcing the match to extend to the *last* such close
# tag in that run instead — which still stops correctly at the boundary
# between two separate, real script blocks.
_SCRIPT_RE = _re.compile(
    r"<script.*?</script>(?!(?:(?!<script).)*</script)", _re.S | _re.I)


def lint_story_copy(html_text: str) -> list[str]:
    prose = _SCRIPT_RE.sub("", html_text)
    hits = []
    # Word-boundary matching runs on the rendered HTML, not a markup-aware
    # text extraction, so a banned word split across tags (e.g.
    # "Lever<b>age</b>") would slip past this scan undetected. That gap is
    # accepted for now: every piece of data text in this lane is escaped
    # and inserted as plain, untagged text, so no code path here can
    # produce mid-word markup today. A future page that inserts richer
    # (tag-wrapped) content will need a markup-aware scanner instead.
    for w in _BANNED_STORY:
        if _re.search(rf"\b{w}\b", prose, _re.I):
            hits.append(f"banned word in page prose: {w}")
    if len(_re.findall(r"\bindex(?:ed)?\b", prose, _re.I)) > 1:
        hits.append("'index/indexed' appears more than once")
    return hits


def _link_entities(text_html: str, entity_links: dict, used: set) -> str:
    """Wrap the first still-unlinked occurrence of each entity title in `text_html`
    (already esc()'d) with a link to its dossier. Word-boundary match so a title
    never matches mid-word; `used` tracks titles already linked earlier in the
    same scene so each entity is linked at most once per scene."""
    for title, href in entity_links.items():
        if title in used:
            continue
        et = esc(title)
        m = _re.search(rf"(?<![\w-]){_re.escape(et)}(?![\w-])", text_html)
        if m:
            text_html = (text_html[:m.start()]
                         + f'<a href="{esc(href)}">{et}</a>'
                         + text_html[m.end():])
            used.add(title)
    return text_html


def _scene_html(scene: dict, entity_links: dict | None = None) -> str:
    # `entity_links` (title -> dossier href) is the F101c Task 7 narrative-first
    # wiring: entity names mentioned in scene prose become links to their
    # Explore dossier. Default None keeps the front page's original behavior
    # byte-identical; the link pass runs server-side only when a map is supplied.
    used: set = set()
    paras = []
    for i, p in enumerate(scene["paragraphs"]):
        if i == 0:
            words = p.split(" ")
            head, tail = " ".join(words[:6]), " ".join(words[6:])
            # Only the tail is entity-linked: the head is already inside the
            # evidence-trigger anchor, and nesting <a> tags is invalid.
            tail_html = _link_entities(esc(tail), entity_links, used) if entity_links else esc(tail)
            paras.append(f'<p><a class="ev" href="#" '
                         f'data-ev="scene:{scene["n"]}">{esc(head)}'
                         f'<sup>ⓘ</sup></a> {tail_html}</p>')
        else:
            p_html = _link_entities(esc(p), entity_links, used) if entity_links else esc(p)
            paras.append(f"<p>{p_html}</p>")
    vis = ""
    if scene["visual"]["series"]:
        vis = (f'<div class="st-visual">{spark_svg(scene["visual"]["series"], 300, 60)}'
               f'<span class="st-lab">{esc(scene["visual"]["label"])}</span></div>')
    rel = ""
    if scene["related"]:
        links = " ".join(
            f'<a href="{esc(r["url"])}" target="_blank" rel="noopener">'
            f'{esc(r["outlet"])} · {esc(r["title"])} · {esc(r["date"])}</a>'
            for r in scene["related"]
            if r["url"].startswith(("http://", "https://")))
        # Only render the row if at least one link survived the http/https
        # check -- otherwise it's a dangling "Related coverage:" label with
        # nothing after it.
        if links:
            rel = f'<p class="st-related">Related coverage: {links}</p>'
    return (f'<article class="st-scene st-scene-{scene["accent"]}">'
            f'<i class="st-dot st-dot-{scene["accent"]}">{scene["n"]}</i>'
            f'<h2>{esc(scene["title"])}</h2>{"".join(paras)}{vis}'
            f'<p class="st-srcline">{esc(scene["source_line"])}</p>{rel}'
            f'</article>')


def _closing_strip(model: dict) -> str:
    # F101c Task 7: archive chips and the "story archive →" link route into the
    # story archive (link-target change only — the chip content is unchanged).
    chips = "".join(
        f'<a class="st-arch" href="story/">{esc(a["label"])} · '
        f'{esc(a["text"])}</a>'
        for a in model["archive"])
    return (f'<section class="st-closing"><p>Tomorrow’s entry will update '
            f'this story.</p>{chips}'
            f'<a href="story/">story archive →</a></section>')


_EXPLORE_DESC = {
    "entities": "companies and players, each with its own page",
    "findings": "every piece of evidence we’ve collected",
    "series": "the raw numbers over time",
    "history": "how our answer has changed"}

# F101c Task 7: each explore-band tile routes to its own deep page instead of
# the retired catch-all appendix. Directory routes (served by Cloudflare Pages
# as each dir's index.html) so no visible front-page link carries the word
# "index" -- the front page already spends its one allowed index/indexed
# occurrence on the gap-chart axis label, and lint_story_copy bans a second.
_EXPLORE_ROUTES = {
    "entities": "entities/",
    "findings": "findings/",
    "series": "series/",
    "history": "history.html"}


def _explore_band(model: dict) -> str:
    tiles = "".join(
        f'<a class="st-tile" href="{_EXPLORE_ROUTES[k]}"><b>{k.title()} '
        f'({model["explore"].get(k, 0)})</b>'
        f'<span>{_EXPLORE_DESC[k]}</span></a>'
        for k in ["entities", "findings", "series", "history"])
    return f'<section class="st-explore">{tiles}</section>'


def render_story_page(model: dict, entity_links: dict | None = None) -> str:
    scenes = "".join(_scene_html(s, entity_links) for s in model["scenes"])
    # No scenes (e.g. a category with no monthly scorecards) -- an empty
    # "The story, step by step" section reads as broken. Suppress it.
    story_section = (
        f'<section class="st-story"><h2 class="st-storyhead">The story, '
        f'step by step</h2>{scenes}</section>' if model["scenes"] else "")
    body = (f'<div class="st-page">{_headline_block(model)}'
            f'{_chart_block(model)}{_kpi_band(model)}'
            f'{story_section}'
            f'{_closing_strip(model)}{_explore_band(model)}'
            f'<footer class="st-foot">Built by an autonomous research agent '
            f'· evidence-linked · revision {model["revision"]}</footer>'
            f'</div>{evidence_json(model["evidence"])}'
            f'{render_evidence_panel()}{render_condense_script()}')
    # This page sits at site/<category>/index.html -- its sibling style.css
    # lives right beside it (depth 0), not one level up. depth=1 only
    # "worked" because the build happens to write two identical copies of
    # the stylesheet (out/style.css and out/<category>/style.css).
    return _page(f'Merchant GPU — {model["headline"]}', body, depth=0)
