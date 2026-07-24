"""F101: demand-vs-supply gap derivation + small SVG helpers.

Levels are cumulative sums of the stored monthly demand/supply
contributions, indexed to 100 at the window start, so the vertical
distance between the two lines is the gap the page talks about.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from gpu_agent.dashboard.render import esc

_MONTHLY = re.compile(r"^(\d{4}-\d{2})-v(\d+)\.json$")
_MONTH_LABEL = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_DEAD_BAND = 0.5
_SCALE = 10.0


def _monthly_records(cat_dir: Path) -> list[dict]:
    best: dict[str, tuple[int, Path]] = {}
    for p in Path(cat_dir).glob("*.json"):
        m = _MONTHLY.match(p.name)
        if not m:
            continue
        key, rev = m.group(1), int(m.group(2))
        if key not in best or rev > best[key][0]:
            best[key] = (rev, p)
    out = []
    for key in sorted(best):
        # A filename can match the pattern with an impossible month (e.g.
        # "2026-13-v1.json") and later blow up any code that turns the key
        # into a real date/month-name (dt.date(...), the month-label
        # lookup). Skip such a file rather than let the build crash.
        month_num = int(key[5:7])
        if not (1 <= month_num <= 12):
            continue
        try:
            d = json.loads(best[key][1].read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        ds = d.get("demandSupply") or {}
        dmi, smi = ds.get("dmiContribution"), ds.get("smiContribution")
        if dmi is None or smi is None:
            continue
        out.append({"key": key, "dmi": float(dmi), "smi": float(smi)})
    return out


def build_gap_data(cat_dir: Path, limit: int = 7) -> dict | None:
    recs = _monthly_records(cat_dir)[-limit:]
    if len(recs) < 2:
        return None
    months, demand, supply = [], [], []
    d_lvl = s_lvl = 100.0
    for r in recs:
        d_lvl += _SCALE * r["dmi"]
        s_lvl += _SCALE * r["smi"]
        months.append({"key": r["key"],
                       "label": _MONTH_LABEL[int(r["key"][5:7])]})
        demand.append(round(d_lvl, 4))
        supply.append(round(s_lvl, 4))
    gap_now = demand[-1] - supply[-1]
    gap_prev = demand[-2] - supply[-2]
    if gap_now - gap_prev > _DEAD_BAND:
        word = "widened"
    elif gap_prev - gap_now > _DEAD_BAND:
        word = "narrowed"
    else:
        word = "held"
    return {"months": months, "demand": demand, "supply": supply,
            "gap_now": round(gap_now, 4), "gap_prev": round(gap_prev, 4),
            "gap_word": word}


def spark_svg(values: list[float], w: int = 60, h: int = 18) -> str:
    if not values:
        return ""
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0
    pts = []
    for i, v in enumerate(values):
        x = 2 + i * (w - 4) / max(len(values) - 1, 1)
        y = h - 2 - (v - lo) / span * (h - 4)
        pts.append(f"{x:.1f},{y:.1f}")
    return (f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
            f'class="spark" aria-hidden="true">'
            f'<polyline points="{" ".join(pts)}" fill="none" '
            f'stroke="currentColor" stroke-width="1.5"/></svg>')


_W, _H = 780, 270
_PAD_L, _PAD_R, _PAD_T, _PAD_B = 46, 16, 46, 34
_DEMAND, _SUPPLY, _GAP_FILL = "#b0562e", "#1f7a8c", "#f2c14e"


def _scale(data):
    xs = list(range(len(data["months"])))
    lo = min(min(data["demand"]), min(data["supply"]))
    hi = max(max(data["demand"]), max(data["supply"]))
    span = (hi - lo) or 1.0
    px = lambda i: _PAD_L + i * (_W - _PAD_L - _PAD_R) / max(len(xs) - 1, 1)
    py = lambda v: _H - _PAD_B - (v - lo) / span * (_H - _PAD_T - _PAD_B)
    return px, py


def render_gap_svg(data: dict, callouts: list[dict] | None = None) -> str:
    px, py = _scale(data)
    n = len(data["months"])
    d_pts = " ".join(f"{px(i):.1f},{py(data['demand'][i]):.1f}" for i in range(n))
    s_pts = " ".join(f"{px(i):.1f},{py(data['supply'][i]):.1f}" for i in range(n))
    band = (d_pts + " " +
            " ".join(f"{px(i):.1f},{py(data['supply'][i]):.1f}"
                     for i in reversed(range(n))))
    wedge = (f"{px(n-2):.1f},{py(data['demand'][n-2]):.1f} "
             f"{px(n-1):.1f},{py(data['demand'][n-1]):.1f} "
             f"{px(n-1):.1f},{py(data['supply'][n-1]):.1f} "
             f"{px(n-2):.1f},{py(data['supply'][n-2]):.1f}")
    ticks = "".join(
        f'<text x="{px(i):.1f}" y="{_H-12}" class="gc-tick" '
        f'text-anchor="middle">{esc(m["label"])}</text>'
        for i, m in enumerate(data["months"]))
    keyed = {m["key"]: i for i, m in enumerate(data["months"])}
    notes = []
    for j, c in enumerate(callouts or []):
        i = keyed.get(c.get("month_key"))
        if i is None:
            continue
        x, y = px(i), py(data["demand"][i]) - 18 - 14 * j
        body = esc(c["text"])
        if c.get("claim"):
            body = (f'<a class="ev" data-ev="{esc(c["claim"])}" '
                    f'href="#">{body}<tspan class="gc-i"> ⓘ</tspan></a>')
        notes.append(
            f'<line x1="{x:.1f}" y1="{y+4:.1f}" x2="{x:.1f}" '
            f'y2="{py(data["demand"][i])-2:.1f}" class="gc-leader"/>'
            f'<text x="{x:.1f}" y="{y:.1f}" class="gc-note" '
            f'text-anchor="middle">{body}</text>')
    gap_x, gap_y = px(n - 1) - 6, (py(data["demand"][n-1]) +
                                   py(data["supply"][n-1])) / 2
    return f"""<svg viewBox="0 0 {_W} {_H}" class="gapchart" role="img"
 aria-label="Demand and supply over time; the shaded area is the gap">
<text x="{_PAD_L}" y="16" class="gc-axis">orders vs. chips shipped, indexed</text>
<polygon points="{band}" fill="{_GAP_FILL}" opacity="0.28"/>
<polygon points="{wedge}" fill="#e4572e" opacity="0.30"/>
<polyline points="{d_pts}" fill="none" stroke="{_DEMAND}" stroke-width="2.5"/>
<polyline points="{s_pts}" fill="none" stroke="{_SUPPLY}" stroke-width="2.5"/>
<line x1="{px(n-1):.1f}" y1="{_PAD_T}" x2="{px(n-1):.1f}" y2="{_H-_PAD_B}"
 stroke="#666" stroke-dasharray="4 3"/>
<text x="{px(n-1):.1f}" y="{_PAD_T-6}" class="gc-tick" text-anchor="end">now</text>
<text x="{gap_x:.1f}" y="{gap_y:.1f}" class="gc-gap" text-anchor="end">the gap, this week</text>
{ticks}{"".join(notes)}
<g class="gc-legend"><circle cx="{_PAD_L+6}" cy="{_H-2}" r="4" fill="{_DEMAND}"/>
<text x="{_PAD_L+14}" y="{_H+2}" class="gc-tick">What buyers want (demand)</text>
<circle cx="{_PAD_L+216}" cy="{_H-2}" r="4" fill="{_SUPPLY}"/>
<text x="{_PAD_L+224}" y="{_H+2}" class="gc-tick">What can be shipped (supply)</text></g>
</svg>"""


_TL_ROWS = 3
_TL_ROW_STEP = 12


def render_timeline_svg(gap_data: dict | None, month_headlines: list[str]) -> str:
    """The full-history gap chart (every month `gap_data` carries, not just
    the front page's last 7) with each month's own headline pinned above
    the plot as a small label + leader line down to that month's point on
    the demand line. Reuses `_scale` (and the same `_W`/`_H`/`_PAD_*`
    canvas) verbatim -- this does not change how the front-page gap chart
    is laid out, it only draws more months into the same coordinate system.
    Labels cycle across `_TL_ROWS` vertical rows (by month index) so
    adjacent months' leader lines don't all land on the same baseline.
    `month_headlines` is expected to line up 1:1 with `gap_data["months"]`;
    a short list (or a blank headline) just means fewer labels are drawn,
    it never raises."""
    if not gap_data or not gap_data.get("months"):
        return ""
    px, py = _scale(gap_data)
    n = len(gap_data["months"])
    d_pts = " ".join(f"{px(i):.1f},{py(gap_data['demand'][i]):.1f}" for i in range(n))
    s_pts = " ".join(f"{px(i):.1f},{py(gap_data['supply'][i]):.1f}" for i in range(n))
    band = (d_pts + " " +
            " ".join(f"{px(i):.1f},{py(gap_data['supply'][i]):.1f}"
                     for i in reversed(range(n))))
    ticks = "".join(
        f'<text x="{px(i):.1f}" y="{_H-12}" class="gc-tick" '
        f'text-anchor="middle">{esc(m["label"])}</text>'
        for i, m in enumerate(gap_data["months"]))
    labels = []
    for i, m in enumerate(gap_data["months"]):
        headline = month_headlines[i] if i < len(month_headlines) else ""
        if not headline:
            continue
        x = px(i)
        y = 12 + (i % _TL_ROWS) * _TL_ROW_STEP
        labels.append(
            f'<line x1="{x:.1f}" y1="{y+4:.1f}" x2="{x:.1f}" y2="{_PAD_T-2}" '
            f'class="gc-leader"/>'
            f'<text x="{x:.1f}" y="{y:.1f}" class="gc-note" '
            f'text-anchor="middle">{esc(headline)}</text>')
    return f"""<svg viewBox="0 0 {_W} {_H}" class="gapchart gc-timeline" role="img"
 aria-label="Demand and supply over every month on record, with each month's headline pinned above it">
<polygon points="{band}" fill="{_GAP_FILL}" opacity="0.28"/>
<polyline points="{d_pts}" fill="none" stroke="{_DEMAND}" stroke-width="2"/>
<polyline points="{s_pts}" fill="none" stroke="{_SUPPLY}" stroke-width="2"/>
{ticks}{"".join(labels)}
<g class="gc-legend"><circle cx="{_PAD_L+6}" cy="{_H-2}" r="4" fill="{_DEMAND}"/>
<text x="{_PAD_L+14}" y="{_H+2}" class="gc-tick">What buyers want (demand)</text>
<circle cx="{_PAD_L+216}" cy="{_H-2}" r="4" fill="{_SUPPLY}"/>
<text x="{_PAD_L+224}" y="{_H+2}" class="gc-tick">What can be shipped (supply)</text></g>
</svg>"""
