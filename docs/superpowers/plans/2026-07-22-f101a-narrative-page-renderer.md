# F101 Phase A — Narrative-First Category Page (Renderer Skeleton) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the category `index.html` with the F101 narrative-first page — headline verdict, demand-vs-supply gap chart, KPI band, assembled stand-in story with scenes, evidence panel + hover tooltips, archive strip, Explore band — built entirely from existing committed store data (no pipeline change, no F6/F83 exposure).

**Architecture:** Three new focused modules in `gpu_agent/dashboard/`: `gap_chart.py` (gap data derivation + SVG), `story_model.py` (the page model, whose shape doubles as the Phase-B narrator artifact contract), `story_render.py` (HTML + CSS + the evidence-panel/tooltip script, extending the proven F100 inline-script pattern). `site_build.py` swaps `index.html` from `render_brief` to the new page. Old brief/deepdive modules stay in-tree as donors (appendix + how pages unchanged).

**Tech Stack:** Python 3 (repo venv `.venv/Scripts/python`), stdlib-only (json, pathlib, datetime, re), server-rendered inline SVG, one self-contained inline `<script>` (F100 scoped relaxation, user-approved), pytest.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-22-f101-narrative-page-design.md`. Phase A ONLY (§10.1): no new pipeline step, no brain prompts, no `registry/indicators.json` change — F6 pin and scoring v1 replay pin must stay GREEN and UNMOVED.
- Frozen core untouched: `gpu_agent/scoring.py`, `gpu_agent/report.py`, brains, eval fixtures.
- Banned words in rendered prose (outside `<script>` blocks and direct quotes): `momentum, strengthening, tightening, accelerating, DMI, SMI, allocation, doctrine, robust, leverage` (extends F97 `_BANNED`); `index/indexed` allowed exactly once (chart axis label).
- Voice: plain newspaper English (stop-slop conventions); reader is a non-technical executive.
- Every chart carries a visible `Source:` line; every KPI/callout/evidence link opens the evidence panel; KPI chips get CSS-only hover tooltips.
- All link `href`s built client-side must go through `encodeURI` (F100 XSS regression precedent, deepdive_render.py:41).
- Python from repo root: `.venv/Scripts/python` (worktree: `../../.venv/Scripts/python`). Suite green at every commit; expect 3–6 skips.
- Execution in worktree `.worktrees/f101a-story-page`, branch `f101a-story-page`. Never on root main.
- Wall-clock isolation: every model function takes `today: datetime.date` as a parameter; tests pass explicit dates.

**Store facts used throughout (verified 2026-07-22):**
- Monthly scorecards `store/chips.merchant-gpu/YYYY-MM-vN.json`; latest = highest rev of newest month. Keys: `asOf`, `categoryStatus{rating,direction,bottleneck,reason,constraintLabel}`, `demandSupply{dmiContribution,smiContribution,sdgi,sdgiDirection,anchors}`, `dimensionRatings{<dim>:{rating,direction,confidence,findingIds,rationale}}`, `findings[]`, `narrative`.
- Series rows (`store/series/<id>.jsonl`, read via `agenda.read_series`): `{indicatorId,period,value,unit,publishedAt,source{url,title},estimateGrade,label,note}`.
- Findings inside scorecards: normalized by `scorecards._norm_finding`; standalone `store/findings/*.json` have `evidence:[{source,url,date,excerpt,tier}]`.
- Implications: `store/implications/<cat>/<asOf>.json` → `lines:[{dimensions,findingIds,thesisIds,watchItem|text}]` via `brief_model.read_implication_lines`.
- Test fixture store: `tests/dashboard/fixtures` (`FIX`), pattern per `tests/dashboard/test_site_build.py:80`.

---

### Task 1: Gap-chart data derivation (`gap_chart.build_gap_data`)

**Files:**
- Create: `gpu_agent/dashboard/gap_chart.py`
- Test: `tests/dashboard/test_gap_chart.py`

**Interfaces:**
- Consumes: monthly scorecard files in a category dir (shape above); reuses `brief_model._MONTHLY_RE` convention (do not import the private regex — re-declare locally).
- Produces: `build_gap_data(cat_dir: Path, limit: int = 7) -> dict | None` returning
  `{"months": [{"key":"2026-07","label":"Jul"}...], "demand": [float...], "supply": [float...], "gap_now": float, "gap_prev": float, "gap_word": "widened"|"narrowed"|"held"}` (lists same length, oldest→newest, ≥2 points; None if <2 monthly points). Also `spark_svg(values: list[float], w: int = 60, h: int = 18) -> str` (tiny polyline SVG used by KPI chips).

**Derivation (the plan-time decision the spec §3.2 defers to here):** demand and supply render as cumulative levels indexed to 100 at the window start: `demand[i] = 100 + 10 * sum(dmiContribution[0..i])`, `supply[i] = 100 + 10 * sum(smiContribution[0..i])`, one point per month (highest rev per month, monthly files only). Gap = `demand[i] - supply[i]`. `gap_word`: compare `gap_now` vs `gap_prev` with a 0.5 dead-band → `held` inside the band. Fully reproducible from committed store data.

- [ ] **Step 1: Write the failing tests**

```python
# tests/dashboard/test_gap_chart.py
import json
from pathlib import Path
import pytest
from gpu_agent.dashboard.gap_chart import build_gap_data, spark_svg


def _mk_monthly(tmp_path, as_of, rev, dmi, smi):
    p = tmp_path / f"{as_of}-v{rev}.json"
    p.write_text(json.dumps({
        "asOf": as_of,
        "demandSupply": {"dmiContribution": dmi, "smiContribution": smi},
        "categoryStatus": {"rating": "Strong", "direction": "improving",
                           "reason": "", "constraintLabel": "HBM memory"},
        "dimensionRatings": {}, "findings": [],
    }), encoding="utf-8")
    return p


def test_build_gap_data_levels_and_word(tmp_path):
    _mk_monthly(tmp_path, "2026-05", 1, 1.0, 0.5)
    _mk_monthly(tmp_path, "2026-06", 2, 1.0, 1.0)   # highest rev of month wins
    _mk_monthly(tmp_path, "2026-06", 1, 9.9, 9.9)   # ignored (lower rev)
    _mk_monthly(tmp_path, "2026-07", 1, 2.0, 0.2)
    data = build_gap_data(tmp_path)
    assert [m["key"] for m in data["months"]] == ["2026-05", "2026-06", "2026-07"]
    assert data["months"][-1]["label"] == "Jul"
    assert data["demand"] == [110.0, 120.0, 140.0]   # 100+10*cumsum(1,1,2)
    assert data["supply"] == [105.0, 115.0, 117.0]   # 100+10*cumsum(.5,1,.2)
    assert data["gap_now"] == pytest.approx(23.0)
    assert data["gap_prev"] == pytest.approx(5.0)
    assert data["gap_word"] == "widened"


def test_build_gap_data_daily_files_ignored_and_none_when_thin(tmp_path):
    _mk_monthly(tmp_path, "2026-07", 1, 1.0, 1.0)
    (tmp_path / "2026-07-02-v1.json").write_text("{}", encoding="utf-8")
    assert build_gap_data(tmp_path) is None  # one monthly point is not enough


def test_gap_word_dead_band(tmp_path):
    _mk_monthly(tmp_path, "2026-06", 1, 1.0, 1.0)
    _mk_monthly(tmp_path, "2026-07", 1, 1.02, 1.0)  # gap moves 0.2 < 0.5
    assert build_gap_data(tmp_path)["gap_word"] == "held"


def test_spark_svg_shape():
    svg = spark_svg([1.0, 2.0, 1.5])
    assert svg.startswith("<svg") and "polyline" in svg and "viewBox" in svg
    assert spark_svg([]) == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `../../.venv/Scripts/python -m pytest tests/dashboard/test_gap_chart.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gpu_agent.dashboard.gap_chart'`

- [ ] **Step 3: Write the implementation**

```python
# gpu_agent/dashboard/gap_chart.py
"""F101: demand-vs-supply gap derivation + small SVG helpers.

Levels are cumulative sums of the stored monthly demand/supply
contributions, indexed to 100 at the window start, so the vertical
distance between the two lines is the gap the page talks about.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `../../.venv/Scripts/python -m pytest tests/dashboard/test_gap_chart.py -v`
Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add gpu_agent/dashboard/gap_chart.py tests/dashboard/test_gap_chart.py
git commit -m "feat(f101a): gap-chart data derivation from monthly scorecards"
```

---

### Task 2: Gap-chart SVG renderer (`gap_chart.render_gap_svg`)

**Files:**
- Modify: `gpu_agent/dashboard/gap_chart.py`
- Test: `tests/dashboard/test_gap_chart.py` (append)

**Interfaces:**
- Consumes: the `build_gap_data` dict (Task 1); callouts from the story model (Task 3) as `[{"month_key":"2026-06","text":"Jun: memory makers cut back","claim":"callout:1"}]` (`claim` optional → adds a panel-opening ⓘ).
- Produces: `render_gap_svg(data: dict, callouts: list[dict] | None = None) -> str` — one self-contained `<svg>` (~780×270 viewBox): terracotta demand polyline, teal supply polyline, amber shaded polygon between them with a stronger final-month wedge, bold `the gap, this week` label, dashed now-line at the right edge, month tick labels, plain legend (`What buyers want (demand)` / `What can be shipped (supply)`), y-axis micro-label `orders vs. chips shipped, indexed`, callout texts with leader lines. Panel triggers rendered as `<a class="ev" data-ev="callout:1">` wrapping the callout text.

- [ ] **Step 1: Write the failing tests** (append to `tests/dashboard/test_gap_chart.py`)

```python
from gpu_agent.dashboard.gap_chart import render_gap_svg


def _data(tmp_path):
    _mk_monthly(tmp_path, "2026-05", 1, 1.0, 0.5)
    _mk_monthly(tmp_path, "2026-06", 1, 1.0, 1.0)
    _mk_monthly(tmp_path, "2026-07", 1, 2.0, 0.2)
    return build_gap_data(tmp_path)


def test_render_gap_svg_structure(tmp_path):
    svg = render_gap_svg(_data(tmp_path))
    assert svg.count("<svg") == 1 and svg.count("</svg>") == 1
    assert "polyline" in svg and "polygon" in svg          # lines + shaded gap
    assert "the gap, this week" in svg
    assert "What buyers want (demand)" in svg
    assert "What can be shipped (supply)" in svg
    assert "orders vs. chips shipped, indexed" in svg
    assert 'stroke-dasharray' in svg                        # now-line
    assert ">Jul<" in svg and ">May<" in svg                # month ticks


def test_render_gap_svg_callout_is_panel_trigger(tmp_path):
    svg = render_gap_svg(_data(tmp_path), callouts=[
        {"month_key": "2026-06", "text": "Jun: memory makers cut back",
         "claim": "callout:1"}])
    assert 'data-ev="callout:1"' in svg
    assert "Jun: memory makers cut back" in svg


def test_render_gap_svg_escapes_callout_text(tmp_path):
    svg = render_gap_svg(_data(tmp_path), callouts=[
        {"month_key": "2026-06", "text": "<img src=x>", "claim": None}])
    assert "<img" not in svg and "&lt;img" in svg
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `../../.venv/Scripts/python -m pytest tests/dashboard/test_gap_chart.py -v -k render_gap`
Expected: FAIL — `ImportError: cannot import name 'render_gap_svg'`

- [ ] **Step 3: Write the implementation** (append to `gpu_agent/dashboard/gap_chart.py`)

```python
from gpu_agent.dashboard.render import esc

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
```

Note: the legend `<g>` hangs 2px below `_H`; set `overflow: visible` on `.gapchart` in Task 6's CSS (already included there).

- [ ] **Step 4: Run tests to verify they pass**

Run: `../../.venv/Scripts/python -m pytest tests/dashboard/test_gap_chart.py -v`
Expected: 7 PASS

- [ ] **Step 5: Commit**

```bash
git add gpu_agent/dashboard/gap_chart.py tests/dashboard/test_gap_chart.py
git commit -m "feat(f101a): gap-chart SVG renderer with shaded gap + callouts"
```

---

### Task 3: Story model — headline, KPI band, gap block (`story_model.py`, part 1)

**Files:**
- Create: `gpu_agent/dashboard/story_model.py`
- Test: `tests/dashboard/test_story_model.py`

**Interfaces:**
- Consumes: `gap_chart.build_gap_data`; `agenda.read_series(series_dir, ids)` @agenda.py:177; `brief_model.latest_monthly(cat_dir)` @brief_model.py:52; `brief_model.first_n_sentences` @:193; `glossary.load_glossary/term_swap` for jargon-free labels.
- Produces: `build_story_model(category_id: str, store_dir: str | Path, today: datetime.date) -> dict` with keys (this shape IS the Phase-B narrator artifact contract; Phase B swaps the assembler, not the shape):
  - `headline: str`, `deck: str`, `dateline: str`, `revision: int`, `as_of: str`
  - `gap: dict | None` (Task 1 shape), `callouts: [{"month_key","text","claim"}]`
  - `kpis: {"anchored": CHIP, "picks": [CHIP...]}` where `CHIP = {"claim","label","value","arrow","spark":[floats],"caption","tip","scene":int|None}`
  - `evidence: {claim_id: {"title","claim_text","findings":[{"source","date","take","url"}],"series":[floats],"explore":str}}` (grows in Task 4)
  - `scenes`, `archive`, `explore`, filled in Task 4.

**Phase-A assembly rules (deterministic, from committed data only):**
- Headline from `gap["gap_word"]`: widened → `"The GPU shortage got worse this month."`; narrowed → `"Supply gained ground on demand this month."`; held → `"The GPU shortage held steady this month."`; no gap data → `"The state of the GPU market."`
- Deck = `constraintLabel` + reason, jargon-swapped and trimmed: `f"The main chokepoint is {label}. {first_n_sentences(term_swap(reason, gl), 1)}"`.
- Dateline = `today.strftime("%A, %B %d, %Y").replace(" 0", " ") + " · updated with each run"`.
- KPI anchored = `gpuRentalOnDemand` latest row → label `"What a GPU rents for"`, value `f"${v:,.2f}/hr"`, caption `"always shown — the market's price of scarcity"`.
- Phase-A static picks (scene mapping added in Task 4): `hyperscalerCapexRevision` → `"Big buyers' spending plans"` (value `"raised again"` if last value > 0 else `"trimmed"` / `"holding"` at 0), `odmMonthlyAiRevenue` → `"Servers actually shipped"` (`"+{v:.0f}% vs last year"`), `hbmSupplyCapex` → `"Memory factory spending"` (`"+{v:.0f}% vs last year"`), `gpuSpotPrice` → `"Street price per GPU"` (`"${v:,.0f}"`). Arrow: compare last two values (`▲`/`▼`/`→`). Skip chips whose series is empty; band renders whatever survives.
- Each chip: `claim = f"kpi:{indicatorId}"`, `tip` = 2-sentence plain description (fixed per-indicator table in the module), `spark` = last ≤8 series values.
- Every chip mints an `evidence[claim]` entry: title `f"{label}: {value} — says who?"`, claim_text = tip first sentence, findings = up to 3 rows from the series rows' `source` fields (`{"source": title, "date": publishedAt, "take": note-or-label trimmed to 90 chars, "url": url}`), series = spark values, explore = `"appendix.html"`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/dashboard/test_story_model.py
import datetime as dt
import json
from pathlib import Path
from gpu_agent.dashboard.story_model import build_story_model

CAT = "chips.merchant-gpu"


def _store(tmp_path, dmi_smi=((1.0, 0.5), (2.0, 0.2))):
    cat = tmp_path / CAT
    cat.mkdir(parents=True)
    months = ["2026-06", "2026-07"]
    for m, (dmi, smi) in zip(months, dmi_smi):
        (cat / f"{m}-v1.json").write_text(json.dumps({
            "asOf": m,
            "demandSupply": {"dmiContribution": dmi, "smiContribution": smi},
            "categoryStatus": {"rating": "Strong", "direction": "improving",
                               "bottleneck": "bottleneck",
                               "reason": "Packaging capacity is booked out.",
                               "constraintLabel": "advanced packaging"},
            "dimensionRatings": {
                "bottleneck": {"rating": "Weak", "direction": "worsening",
                                "findingIds": ["f-1"],
                                "rationale": "Memory makers cut back supply. New lines take a year."},
                "momentum": {"rating": "Strong", "direction": "improving",
                              "findingIds": ["f-2"],
                              "rationale": "Buyers raised budgets again."}},
            "findings": [
                {"id": "f-1", "statement": "SK Hynix shifted HBM output",
                 "evidence": [{"source": "Micron call", "url": "https://x.example/a",
                                "date": "2026-06-24", "excerpt": "…", "tier": "primary"}]},
                {"id": "f-2", "statement": "Oracle capex up 162%",
                 "evidence": [{"source": "CNBC", "url": "https://x.example/b",
                                "date": "2026-06-10", "excerpt": "…", "tier": "secondary"}]}],
        }), encoding="utf-8")
    series = tmp_path / "series"
    series.mkdir()
    rows = {
        "gpuRentalOnDemand": [("2026-05", 15.10), ("2026-06", 14.62)],
        "odmMonthlyAiRevenue": [("2026-05", 61.0), ("2026-06", 68.8)],
        "hbmSupplyCapex": [("2026-05", 42.0), ("2026-06", 50.0)],
        "hyperscalerCapexRevision": [("2026-05", 1.0), ("2026-06", 1.0)],
        "gpuSpotPrice": [("2026-02", 31000.0), ("2026-03", 32516.0)],
    }
    for ind, pts in rows.items():
        (series / f"{ind}.jsonl").write_text("\n".join(json.dumps({
            "indicatorId": ind, "period": p, "value": v, "unit": "x",
            "publishedAt": p + "-28",
            "source": {"url": f"https://src.example/{ind}", "title": f"{ind} source"},
        }) for p, v in pts), encoding="utf-8")
    (tmp_path / "implications" / CAT).mkdir(parents=True)
    (tmp_path / "implications" / CAT / "2026-07.json").write_text(json.dumps({
        "asOf": "2026-07", "categoryId": CAT,
        "lines": [{"dimensions": ["bottleneck"], "findingIds": ["f-1"],
                   "thesisIds": [], "watchItem": "Watch memory supply recovery."}],
    }), encoding="utf-8")
    return tmp_path


def test_headline_deck_dateline(tmp_path):
    m = build_story_model(CAT, _store(tmp_path), dt.date(2026, 7, 22))
    assert m["headline"] == "The GPU shortage got worse this month."
    assert "advanced packaging" in m["deck"]
    assert m["dateline"].startswith("Wednesday, July 22, 2026")
    assert m["gap"]["gap_word"] == "widened"


def test_headline_when_gap_narrows(tmp_path):
    st = _store(tmp_path, dmi_smi=((2.0, 0.2), (0.5, 2.0)))
    m = build_story_model(CAT, st, dt.date(2026, 7, 22))
    assert m["headline"] == "Supply gained ground on demand this month."


def test_kpi_band_anchored_and_picks(tmp_path):
    m = build_story_model(CAT, _store(tmp_path), dt.date(2026, 7, 22))
    a = m["kpis"]["anchored"]
    assert a["claim"] == "kpi:gpuRentalOnDemand"
    assert a["value"] == "$14.62/hr" and a["arrow"] == "▼"
    assert "price of scarcity" in a["caption"]
    labels = [p["label"] for p in m["kpis"]["picks"]]
    assert "Servers actually shipped" in labels
    assert "Big buyers' spending plans" in labels
    pick = next(p for p in m["kpis"]["picks"] if p["label"] == "Servers actually shipped")
    assert pick["value"] == "+69% vs last year" and pick["arrow"] == "▲"
    assert pick["tip"]  # hover description present


def test_every_chip_has_evidence_entry(tmp_path):
    m = build_story_model(CAT, _store(tmp_path), dt.date(2026, 7, 22))
    chips = [m["kpis"]["anchored"], *m["kpis"]["picks"]]
    for c in chips:
        ev = m["evidence"][c["claim"]]
        assert "says who?" in ev["title"]
        assert ev["findings"] and ev["findings"][0]["url"].startswith("https://")


def test_missing_series_chip_skipped(tmp_path):
    st = _store(tmp_path)
    (st / "series" / "odmMonthlyAiRevenue.jsonl").unlink()
    m = build_story_model(CAT, st, dt.date(2026, 7, 22))
    assert "Servers actually shipped" not in [p["label"] for p in m["kpis"]["picks"]]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `../../.venv/Scripts/python -m pytest tests/dashboard/test_story_model.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gpu_agent.dashboard.story_model'`

- [ ] **Step 3: Write the implementation**

```python
# gpu_agent/dashboard/story_model.py
"""F101 Phase A: assemble the narrative-page model from committed store data.

The returned dict's shape doubles as the Phase-B narrator artifact
contract: Phase B replaces this assembler with a reader of
store/<cat>/story/<date>.json, and the renderer must not notice.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from gpu_agent.dashboard.agenda import read_series
from gpu_agent.dashboard.brief_model import (first_n_sentences,
                                             latest_monthly,
                                             read_implication_lines)
from gpu_agent.dashboard.gap_chart import build_gap_data
from gpu_agent.dashboard.glossary import load_glossary, term_swap

_SERIES_IDS = ["gpuRentalOnDemand", "hyperscalerCapexRevision",
               "odmMonthlyAiRevenue", "hbmSupplyCapex", "gpuSpotPrice"]

_CHIP_DEFS = {
    "gpuRentalOnDemand": {
        "label": "What a GPU rents for",
        "fmt": lambda v: f"${v:,.2f}/hr",
        "tip": ("The hourly price to rent a top GPU in the cloud, on demand. "
                "When supply catches up to demand, this number falls."),
    },
    "hyperscalerCapexRevision": {
        "label": "Big buyers' spending plans",
        "fmt": lambda v: "raised again" if v > 0 else ("trimmed" if v < 0 else "holding"),
        "tip": ("Whether the largest data-center builders raised or cut their "
                "spending plans most recently. Rising plans mean demand keeps growing."),
    },
    "odmMonthlyAiRevenue": {
        "label": "Servers actually shipped",
        "fmt": lambda v: f"+{v:.0f}% vs last year",
        "tip": ("Monthly revenue growth of the Taiwanese builders who assemble "
                "AI servers. This is supply actually arriving, not promises."),
    },
    "hbmSupplyCapex": {
        "label": "Memory factory spending",
        "fmt": lambda v: f"+{v:.0f}% vs last year",
        "tip": ("How fast memory makers are growing spending on new factories. "
                "Relief for the shortage — but new lines take about a year."),
    },
    "gpuSpotPrice": {
        "label": "Street price per GPU",
        "fmt": lambda v: f"${v:,.0f}",
        "tip": ("What one top GPU costs to buy outright today. "
                "Scarcity shows up here first."),
    },
}

_HEADLINES = {"widened": "The GPU shortage got worse this month.",
              "narrowed": "Supply gained ground on demand this month.",
              "held": "The GPU shortage held steady this month."}


def _arrow(rows: list[dict]) -> str:
    if len(rows) < 2:
        return "→"
    a, b = rows[-2]["value"], rows[-1]["value"]
    return "▲" if b > a else ("▼" if b < a else "→")


def _chip(ind: str, rows: list[dict]) -> dict | None:
    if not rows:
        return None
    d = _CHIP_DEFS[ind]
    return {"claim": f"kpi:{ind}", "label": d["label"],
            "value": d["fmt"](rows[-1]["value"]), "arrow": _arrow(rows),
            "spark": [r["value"] for r in rows[-8:]],
            "caption": "", "tip": d["tip"], "scene": None}


def _series_evidence(ind: str, rows: list[dict]) -> list[dict]:
    out, seen = [], set()
    for r in reversed(rows):
        src = r.get("source") or {}
        key = src.get("url", "")
        if not key or key in seen:
            continue
        seen.add(key)
        take = (r.get("note") or r.get("label") or "latest reading")[:90]
        out.append({"source": src.get("title", "source"),
                    "date": r.get("publishedAt", ""), "take": take,
                    "url": key})
        if len(out) == 3:
            break
    return out


def build_story_model(category_id: str, store_dir: str | Path,
                      today: dt.date) -> dict:
    store_root = Path(store_dir)
    cat_dir = store_root / category_id
    latest, _prior, as_of, rev = latest_monthly(cat_dir)
    latest = latest or {}
    gl = load_glossary()
    gap = build_gap_data(cat_dir)
    status = latest.get("categoryStatus") or {}

    headline = _HEADLINES.get((gap or {}).get("gap_word"),
                              "The state of the GPU market.")
    label = status.get("constraintLabel") or "supply of key components"
    reason = first_n_sentences(term_swap(status.get("reason") or "", gl), 1)
    deck = f"The main chokepoint is {label}. {reason}".strip()
    dateline = (today.strftime("%A, %B %d, %Y").replace(" 0", " ")
                + " · updated with each run")

    series = read_series(store_root / "series", _SERIES_IDS)
    evidence: dict[str, dict] = {}
    anchored = _chip("gpuRentalOnDemand", series.get("gpuRentalOnDemand", []))
    picks = []
    for ind in _SERIES_IDS[1:]:
        c = _chip(ind, series.get(ind, []))
        if c:
            picks.append(c)
    if anchored:
        anchored["caption"] = "always shown — the market's price of scarcity"
    for c in filter(None, [anchored, *picks]):
        ind = c["claim"].split(":", 1)[1]
        evidence[c["claim"]] = {
            "title": f"{c['label']}: {c['value']} — says who?",
            "claim_text": c["tip"].split(". ")[0] + ".",
            "findings": _series_evidence(ind, series.get(ind, [])),
            "series": c["spark"], "explore": "appendix.html"}

    model = {"category_id": category_id, "as_of": as_of, "revision": rev,
             "headline": headline, "deck": deck, "dateline": dateline,
             "gap": gap, "callouts": [], "kpis": {"anchored": anchored,
                                                  "picks": picks},
             "evidence": evidence, "scenes": [], "archive": [],
             "explore": {}}
    _add_scenes(model, latest, store_root, cat_dir, series, gl)
    return model


def _add_scenes(model, latest, store_root, cat_dir, series, gl):
    """Filled in by Task 4."""
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `../../.venv/Scripts/python -m pytest tests/dashboard/test_story_model.py -v`
Expected: 5 PASS. If `glossary.load_glossary`'s signature differs (check `gpu_agent/dashboard/glossary.py` first — read-first), adapt the two call sites, nothing else.

- [ ] **Step 5: Commit**

```bash
git add gpu_agent/dashboard/story_model.py tests/dashboard/test_story_model.py
git commit -m "feat(f101a): story model part 1 - headline, deck, KPI band, evidence seeds"
```

---

### Task 4: Story model — scenes, archive, explore (`story_model.py`, part 2)

**Files:**
- Modify: `gpu_agent/dashboard/story_model.py` (replace `_add_scenes` stub)
- Test: `tests/dashboard/test_story_model.py` (append)

**Interfaces:**
- Consumes: `read_implication_lines(store_root, category_id, as_of)` @brief_model.py:100; scorecard `dimensionRatings` + embedded `findings`; `gap_chart._monthly_records` for archive.
- Produces (mutates `model` in place):
  - `scenes: [{"n":1,"accent":"amber","title":str,"paragraphs":[str],"visual":{"kind":"spark","series":[floats],"label":str},"source_line":str,"related":[{"outlet","title","date","url"}],"claims":[claim_id...]}]`
  - `callouts` (≤2, derived from scene 1 + gap word) wired to scene claims
  - KPI picks get `scene` numbers (pick i ↔ scene i+1 where both exist)
  - `evidence["scene:N"]` entries per scene (findings resolved from scorecard `findings` by `findingIds`, evidence rows from each finding's `evidence` list)
  - `archive: [{"key":"2026-06","label":"June 2026","text":<headline for that month>}]` (from per-month gap words over the last 4 months)
  - `explore: {"entities":int,"findings":int,"series":int,"history":int}` (counts: `store/wiki/entity/*.md`, `store/findings/*.json`, `store/series/*.jsonl`, monthly+daily scorecard files)

**Phase-A scene assembly (fixed 4-scene frame; scenes with no data are dropped):**
1. **amber — "What tightened"**: bottleneck dimension. Paragraphs: jargon-swapped `first_n_sentences(rationale, 2)` + one sentence from `categoryStatus.reason`. Visual: `hbmSupplyCapex` spark. Claims: findings behind `bottleneck.findingIds`.
2. **terracotta — "Demand kept climbing"**: momentum dimension (never say "momentum" in prose — title is fixed text). Visual: `hyperscalerCapexRevision` spark.
3. **teal — "Where supply is gaining"**: unitEconomics + `odmMonthlyAiRevenue`. Visual: `odmMonthlyAiRevenue` spark.
4. **green — "What would close the gap"** (always last, forward-looking): implication `watchItem`/`text` lines as a bullet-like paragraph each (≤3). Visual: `hbmSupplyCapex` spark.
- `source_line`: `"Source: " + "; ".join(unique finding evidence sources, max 3)`, fallback `"Source: agent-tracked filings and reporting"`.
- `related`: from the scene's findings' `evidence` rows with `tier == "secondary"` → `{"outlet": source, "title": excerpt[:60] or statement[:60], "date": date, "url": url}`, max 2, deduped by url.
- Scene accents cycle `["amber", "terracotta", "teal", "green"]` (spec §7).

- [ ] **Step 1: Write the failing tests** (append to `tests/dashboard/test_story_model.py`)

```python
def test_scenes_assembled(tmp_path):
    m = build_story_model(CAT, _store(tmp_path), dt.date(2026, 7, 22))
    titles = [s["title"] for s in m["scenes"]]
    assert titles[0] == "What tightened"
    assert titles[-1] == "What would close the gap"
    s1 = m["scenes"][0]
    assert s1["n"] == 1 and s1["accent"] == "amber"
    assert any("memory makers cut back" in p.lower() for p in s1["paragraphs"])
    assert s1["visual"]["kind"] == "spark" and s1["visual"]["series"]
    assert s1["source_line"].startswith("Source: ")
    assert "momentum" not in " ".join(
        p for s in m["scenes"] for p in s["paragraphs"]).lower()


def test_scene_evidence_and_related(tmp_path):
    m = build_story_model(CAT, _store(tmp_path), dt.date(2026, 7, 22))
    ev = m["evidence"]["scene:1"]
    assert ev["findings"][0]["source"] == "Micron call"
    assert ev["findings"][0]["url"] == "https://x.example/a"
    demand_scene = next(s for s in m["scenes"] if s["title"] == "Demand kept climbing")
    assert demand_scene["related"][0]["outlet"] == "CNBC"


def test_forward_scene_from_implications(tmp_path):
    m = build_story_model(CAT, _store(tmp_path), dt.date(2026, 7, 22))
    last = m["scenes"][-1]
    assert any("memory supply recovery" in p.lower() for p in last["paragraphs"])


def test_kpi_scene_links_and_callouts(tmp_path):
    m = build_story_model(CAT, _store(tmp_path), dt.date(2026, 7, 22))
    linked = [p["scene"] for p in m["kpis"]["picks"] if p["scene"]]
    assert linked and linked == sorted(linked)
    assert m["callouts"] and m["callouts"][0]["claim"].startswith("scene:")


def test_archive_and_explore_counts(tmp_path):
    st = _store(tmp_path)
    (st / "wiki" / "entity").mkdir(parents=True)
    (st / "wiki" / "entity" / "nvidia.md").write_text("x", encoding="utf-8")
    (st / "findings").mkdir()
    (st / "findings" / "a.json").write_text("{}", encoding="utf-8")
    m = build_story_model(CAT, st, dt.date(2026, 7, 22))
    assert m["explore"] == {"entities": 1, "findings": 1, "series": 5,
                            "history": 2}
    assert m["archive"] and m["archive"][-1]["key"] == "2026-06"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `../../.venv/Scripts/python -m pytest tests/dashboard/test_story_model.py -v -k "scenes or scene_ or forward or archive or callouts"`
Expected: FAIL — scenes list empty / KeyError "scene:1"

- [ ] **Step 3: Write the implementation** (replace the `_add_scenes` stub)

```python
_ACCENTS = ["amber", "terracotta", "teal", "green"]


def _resolve_findings(latest: dict, ids: list[str]) -> list[dict]:
    by_id = {f.get("id"): f for f in latest.get("findings") or []}
    return [by_id[i] for i in ids if i in by_id]


def _finding_rows(findings: list[dict]) -> list[dict]:
    rows, seen = [], set()
    for f in findings:
        for e in f.get("evidence") or []:
            url = e.get("url", "")
            if not url or url in seen:
                continue
            seen.add(url)
            rows.append({"source": e.get("source", "source"),
                         "date": e.get("date", ""),
                         "take": (f.get("statement") or "")[:90],
                         "url": url})
    return rows[:3]


def _related(findings: list[dict]) -> list[dict]:
    out, seen = [], set()
    for f in findings:
        for e in f.get("evidence") or []:
            if e.get("tier") != "secondary":
                continue
            url = e.get("url", "")
            if not url or url in seen:
                continue
            seen.add(url)
            out.append({"outlet": e.get("source", ""),
                        "title": (e.get("excerpt") or f.get("statement") or "")[:60],
                        "date": e.get("date", ""), "url": url})
            if len(out) == 2:
                return out
    return out


def _source_line(findings: list[dict]) -> str:
    names = []
    for f in findings:
        for e in f.get("evidence") or []:
            s = e.get("source")
            if s and s not in names:
                names.append(s)
    return "Source: " + ("; ".join(names[:3]) if names
                         else "agent-tracked filings and reporting")


def _mk_scene(n, title, paragraphs, series_vals, series_label, findings):
    return {"n": n, "accent": _ACCENTS[(n - 1) % 4], "title": title,
            "paragraphs": [p for p in paragraphs if p],
            "visual": {"kind": "spark", "series": series_vals,
                       "label": series_label},
            "source_line": _source_line(findings),
            "related": _related(findings),
            "claims": [f"scene:{n}"]}


def _add_scenes(model, latest, store_root, cat_dir, series, gl):
    dims = latest.get("dimensionRatings") or {}
    status = latest.get("categoryStatus") or {}
    sv = lambda ind: [r["value"] for r in series.get(ind, [])[-8:]]
    plain = lambda t, n=2: first_n_sentences(term_swap(t or "", gl), n)

    specs = []
    if dims.get("bottleneck"):
        d = dims["bottleneck"]
        specs.append(("What tightened",
                      [plain(d.get("rationale")), plain(status.get("reason"), 1)],
                      sv("hbmSupplyCapex"), "Memory factory spending",
                      _resolve_findings(latest, d.get("findingIds") or [])))
    if dims.get("momentum"):
        d = dims["momentum"]
        specs.append(("Demand kept climbing", [plain(d.get("rationale"))],
                      sv("hyperscalerCapexRevision"), "Big buyers' spending plans",
                      _resolve_findings(latest, d.get("findingIds") or [])))
    if dims.get("unitEconomics") or series.get("odmMonthlyAiRevenue"):
        d = dims.get("unitEconomics") or {}
        specs.append(("Where supply is gaining", [plain(d.get("rationale"))],
                      sv("odmMonthlyAiRevenue"), "Servers actually shipped",
                      _resolve_findings(latest, d.get("findingIds") or [])))
    lines = read_implication_lines(store_root, model["category_id"],
                                   model["as_of"]) or []
    watch = [plain(l.get("text") or "", 1) for l in lines[:3]]
    watch_f = _resolve_findings(
        latest, [i for l in lines for i in l.get("finding_ids") or []])
    if watch:
        specs.append(("What would close the gap", watch,
                      sv("hbmSupplyCapex"), "Memory factory spending", watch_f))

    for i, (title, paras, vals, vlabel, finds) in enumerate(specs, start=1):
        sc = _mk_scene(i, title, paras, vals, vlabel, finds)
        if not sc["paragraphs"]:
            continue
        model["scenes"].append(sc)
        model["evidence"][f"scene:{sc['n']}"] = {
            "title": f"{title} — says who?",
            "claim_text": sc["paragraphs"][0],
            "findings": _finding_rows(finds) or model["evidence"].get(
                "kpi:gpuRentalOnDemand", {}).get("findings", []),
            "series": vals, "explore": "appendix.html"}

    for i, pick in enumerate(model["kpis"]["picks"]):
        if i < len(model["scenes"]):
            pick["scene"] = model["scenes"][i]["n"]
            pick["caption"] = pick["caption"] or "picked by today's story"

    if model["gap"] and model["scenes"]:
        month = model["gap"]["months"][-1]
        model["callouts"] = [{
            "month_key": month["key"],
            "text": f"{month['label']}: {model['scenes'][0]['title'].lower()}",
            "claim": "scene:1"}]

    from gpu_agent.dashboard.gap_chart import _monthly_records
    recs = _monthly_records(cat_dir)
    arch = []
    for j in range(max(1, len(recs) - 4), len(recs)):
        d_ = recs[j]["dmi"] - recs[j]["smi"]
        p_ = recs[j - 1]["dmi"] - recs[j - 1]["smi"]
        word = "widened" if d_ > p_ else ("narrowed" if d_ < p_ else "held")
        key = recs[j]["key"]
        label = dt.date(int(key[:4]), int(key[5:7]), 1).strftime("%B %Y")
        arch.append({"key": key, "label": label,
                     "text": _HEADLINES.get(word, "")})
    model["archive"] = arch[:-1]  # the last month IS today's story

    model["explore"] = {
        "entities": len(list((store_root / "wiki" / "entity").glob("*.md"))),
        "findings": len(list((store_root / "findings").glob("*.json"))),
        "series": len(list((store_root / "series").glob("*.jsonl"))),
        "history": len(list(cat_dir.glob("*.json")))}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `../../.venv/Scripts/python -m pytest tests/dashboard/test_story_model.py -v`
Expected: 10 PASS

- [ ] **Step 5: Commit**

```bash
git add gpu_agent/dashboard/story_model.py tests/dashboard/test_story_model.py
git commit -m "feat(f101a): story model part 2 - scenes, archive, explore counts"
```

---

### Task 5: Evidence panel + tooltip script (`story_render.py`, part 1)

**Files:**
- Create: `gpu_agent/dashboard/story_render.py`
- Test: `tests/dashboard/test_story_render.py`

**Interfaces:**
- Consumes: `model["evidence"]` (Tasks 3–4); F100 pattern from `deepdive_render.py` (JSON blob + IIFE; do NOT import it — the payload differs).
- Produces:
  - `evidence_json(evidence: dict) -> str` — `<script type="application/json" id="ev-data">` blob, `json.dumps(..., ensure_ascii=True).replace("<", "\\u003c")` (F100 precedent @deepdive_render.py:11).
  - `render_evidence_panel() -> str` — self-contained IIFE defining `window.openEV(k)` / `window.closeEV()`: right slide-in panel (scrim + Escape close), title, claim text, why-chain (findings rows with `↗` links via `encodeURI(url)` gated on `/^https?:/`), sparkline (client `spark()` like deepdive_render.py:26), footer explore link. Also a delegated click handler: any element with `data-ev` opens its claim (`e.preventDefault()`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/dashboard/test_story_render.py
import json
from gpu_agent.dashboard.story_render import evidence_json, render_evidence_panel

EV = {"kpi:x": {"title": "X: 1 — says who?", "claim_text": "X measures x.",
                "findings": [{"source": "S", "date": "2026-06-01",
                               "take": "t", "url": "https://s.example/a"}],
                "series": [1.0, 2.0], "explore": "appendix.html"}}


def test_evidence_json_blob_escapes_lt():
    blob = evidence_json({"k": {"title": "<script>alert(1)</script>"}})
    assert 'id="ev-data"' in blob and "<script>alert" not in blob.split(">", 1)[1]
    body = blob.split(">", 1)[1].rsplit("<", 1)[0]
    assert json.loads(body)["k"]["title"] == "<script>alert(1)</script>"


def test_panel_script_contract():
    js = render_evidence_panel()
    assert "window.openEV" in js and "window.closeEV" in js
    assert "encodeURI(" in js               # F100 XSS regression carry-over
    assert "data-ev" in js                  # delegated trigger
    assert "Escape" in js                   # keyboard close
    assert js.count("<script>") == 1 and js.count("</script>") == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `../../.venv/Scripts/python -m pytest tests/dashboard/test_story_render.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Write the implementation**

```python
# gpu_agent/dashboard/story_render.py
"""F101 Phase A: render the narrative category page."""
from __future__ import annotations

import json

from gpu_agent.dashboard.render import esc  # noqa: F401  (used from Task 6 on)


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
(d.findings||[]).forEach(function(f){var row=el('div','ev-row');
row.appendChild(el('span','ev-src',(f.source||'')+' · '+(f.date||'')));
row.appendChild(el('span','ev-take',f.take||''));
if(f.url&&/^https?:/.test(f.url)){var a=el('a','ev-link','↗');
a.href=encodeURI(f.url);a.target='_blank';a.rel='noopener';row.appendChild(a);}
list.appendChild(row);});panel.appendChild(list);
if(d.explore){var ex=el('a','ev-explore','see everything we have →');
ex.href=encodeURI(d.explore);panel.appendChild(ex);}
scrim.classList.add('on');panel.classList.add('on');};
window.closeEV=function(){scrim.classList.remove('on');panel.classList.remove('on');};
document.addEventListener('keydown',function(e){if(e.key==='Escape')closeEV();});
document.addEventListener('click',function(e){var t=e.target.closest&&e.target.closest('[data-ev]');
if(t){e.preventDefault();openEV(t.getAttribute('data-ev'));}});
})();</script>"""


def render_evidence_panel() -> str:
    return _PANEL
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `../../.venv/Scripts/python -m pytest tests/dashboard/test_story_render.py -v`
Expected: 2 PASS

- [ ] **Step 5: Commit**

```bash
git add gpu_agent/dashboard/story_render.py tests/dashboard/test_story_render.py
git commit -m "feat(f101a): evidence panel script with encodeURI-hardened links"
```

---

### Task 6: Page renderer — header, chart block, KPI band (`story_render.py`, part 2)

**Files:**
- Modify: `gpu_agent/dashboard/story_render.py`
- Test: `tests/dashboard/test_story_render.py` (append)

**Interfaces:**
- Consumes: full model (Tasks 3–4); `gap_chart.render_gap_svg`, `gap_chart.spark_svg`; `site_render.page(title, body, depth)` @site_render.py:50 for the HTML skeleton.
- Produces:
  - `STORY_CSS: str` module constant (all `.st-*`, `.ev-*`, `.gc-*`, `.gapchart`, `.tip` rules; includes `svg.gapchart{overflow:visible}`; light editorial per spec §7; sticky `.st-head` with `.condensed` variant; `.tip`-on-hover rules `.st-chip:hover .st-tip{display:block}`; mobile `@media (max-width: 640px)` single-column stack).
  - `_headline_block(model) -> str`, `_chart_block(model) -> str`, `_kpi_band(model) -> str` (private helpers, tested through `render_story_page` in Task 7 plus targeted asserts here).
  - Chart block includes the NYT source line: `Source: agent-tracked orders and shipment data; company filings · <first month label>–<last month label> <year>`.
  - KPI chips: `<button class="st-chip" data-ev="kpi:...">` containing value, arrow, label, server-side `spark_svg`, micro-caption, scene dot (`<i class="st-dot st-dot-<accent>">N</i>` when `scene` set, pin `📌`-free: use `<i class="st-pin">` styled in CSS for the anchored chip), and a hidden `<span class="st-tip">` with the `tip` text (CSS hover reveal).
  - A tiny pinned-header script `render_condense_script() -> str`: IIFE adding `.condensed` to `.st-head` past 120px scroll.

- [ ] **Step 1: Write the failing tests** (append)

```python
import datetime as dt
from tests.dashboard.test_story_model import _store, CAT
from gpu_agent.dashboard.story_model import build_story_model
from gpu_agent.dashboard.story_render import (_chart_block, _headline_block,
                                              _kpi_band, STORY_CSS,
                                              render_condense_script)


def _model(tmp_path):
    return build_story_model(CAT, _store(tmp_path), dt.date(2026, 7, 22))


def test_headline_block(tmp_path):
    h = _headline_block(_model(tmp_path))
    assert "The GPU shortage got worse this month." in h
    assert "updated with each run" in h
    assert 'class="st-head"' in h


def test_chart_block_has_svg_and_source_line(tmp_path):
    c = _chart_block(_model(tmp_path))
    assert "<svg" in c and "the gap, this week" in c
    assert "Source: agent-tracked orders and shipment data" in c


def test_kpi_band_chips(tmp_path):
    band = _kpi_band(_model(tmp_path))
    assert 'data-ev="kpi:gpuRentalOnDemand"' in band
    assert "price of scarcity" in band
    assert 'class="st-tip"' in band          # hover tooltip content present
    assert 'class="st-pin"' in band          # anchored marker
    assert "st-dot" in band                  # scene dots on picks
    assert band.count("st-chip") >= 3


def test_css_and_condense_script():
    assert ".st-chip:hover .st-tip" in STORY_CSS
    assert "overflow:visible" in STORY_CSS.replace(" ", "")
    assert "@media" in STORY_CSS
    js = render_condense_script()
    assert "condensed" in js and js.count("<script>") == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `../../.venv/Scripts/python -m pytest tests/dashboard/test_story_render.py -v`
Expected: new tests FAIL — names not defined

- [ ] **Step 3: Write the implementation** (append; representative core, complete enough to satisfy the contract)

```python
from gpu_agent.dashboard.gap_chart import render_gap_svg, spark_svg

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
 padding:8px 12px;background:#fafafa;text-align:left;cursor:pointer;flex:1 1 140px}
.st-chip-anchor{border:1.5px solid #333;background:#fff8ef}
.st-pin::before{content:'\\2693';font-size:10px;margin-right:4px}
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
.ev-link{color:#1f7a8c;text-decoration:none}
.ev-explore{display:block;margin-top:12px;font-size:13px;color:#1f7a8c}
.ev-spark{color:#1f7a8c;display:block;margin:6px 0}
a.ev{cursor:pointer;text-decoration:underline dotted}
@media (max-width:640px){.st-head h1{font-size:27px}
 .st-band{flex-direction:column}.ev-panel{width:88%}}
"""


def _headline_block(model: dict) -> str:
    return (f'<header class="st-head"><h1>{esc(model["headline"])}</h1>'
            f'<p class="st-deck">{esc(model["deck"])}</p>'
            f'<p class="st-date">{esc(model["dateline"])}</p></header>')


def _chart_block(model: dict) -> str:
    if not model.get("gap"):
        return ""
    months = model["gap"]["months"]
    span = f'{months[0]["label"]}–{months[-1]["label"]} {months[-1]["key"][:4]}'
    return (f'<section class="st-chart">'
            f'{render_gap_svg(model["gap"], model.get("callouts"))}'
            f'<p class="st-srcline">Source: agent-tracked orders and shipment '
            f'data; company filings · {esc(span)}</p></section>')


def _chip_html(c: dict, anchored: bool = False) -> str:
    marker = ('<i class="st-pin"></i>' if anchored else
              (f'<i class="st-dot st-dot-{["amber","terracotta","teal","green"][(c["scene"]-1)%4]}">'
               f'{c["scene"]}</i>' if c.get("scene") else ""))
    cls = "st-chip st-chip-anchor" if anchored else "st-chip"
    return (f'<button class="{cls}" data-ev="{esc(c["claim"])}">'
            f'{marker}<span class="st-val">{esc(c["value"])} {c["arrow"]}</span>'
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
    cap = ('<p class="st-srcline">picked by today’s story · '
           'tap any number to ask: says who?</p>')
    return f'<section class="st-band">{"".join(chips)}</section>{cap}'


_CONDENSE = ("<script>(function(){var h=document.querySelector('.st-head');"
             "if(!h)return;addEventListener('scroll',function(){"
             "h.classList.toggle('condensed',scrollY>120);});})();</script>")


def render_condense_script() -> str:
    return _CONDENSE
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `../../.venv/Scripts/python -m pytest tests/dashboard/test_story_render.py -v`
Expected: 6 PASS

- [ ] **Step 5: Commit**

```bash
git add gpu_agent/dashboard/story_render.py tests/dashboard/test_story_render.py
git commit -m "feat(f101a): headline, chart block, KPI band renderers + story CSS"
```

---

### Task 7: Page renderer — scenes, archive, explore, full page (`story_render.py`, part 3)

**Files:**
- Modify: `gpu_agent/dashboard/story_render.py`
- Test: `tests/dashboard/test_story_render.py` (append)

**Interfaces:**
- Consumes: everything above; `site_render.page` for the skeleton.
- Produces:
  - `_scene_html(scene) -> str` — rail dot (accent class), title, paragraphs (first paragraph gets `<a class="ev" data-ev="scene:N">` wrapped around its first 6 words + ⓘ), `spark_svg` visual with label, `source_line` as `.st-srcline`, related row (`Related coverage: <a href=...>outlet · title · date</a>`, hrefs server-side escaped via `esc`, only `http(s)` urls rendered).
  - `_closing_strip(model) -> str` — "Tomorrow's entry will update this story." + archive chips (label + text) + `story archive →` placeholder anchor `#` (Phase C wires it).
  - `_explore_band(model) -> str` — 4 tiles with counts + one-liners from spec §3.6; Entities/Findings/Series/History link to `appendix.html` (Phase C gives them real pages).
  - `render_story_page(model) -> str` — assembles: headline block, chart block, KPI band, `<section class="st-story">` with scenes on a rail, closing strip, explore band, footer `Built by an autonomous research agent · evidence-linked · revision N`, then `evidence_json(model["evidence"])` + `render_evidence_panel()` + `render_condense_script()`. Wrapped in `site_render.page("Merchant GPU — <headline>", body, depth=1)`.
  - `lint_story_copy(html_text: str) -> list[str]` — strips `<script>...</script>` blocks, then scans for banned tokens `["DMI","SMI","momentum","strengthening","tightening","accelerating","allocation","doctrine","robust","leverage"]` case-insensitively as whole words; returns violations (empty = clean). Allows at most one `indexed`.

- [ ] **Step 1: Write the failing tests** (append)

```python
from gpu_agent.dashboard.story_render import (render_story_page,
                                              lint_story_copy)


def test_render_story_page_end_to_end(tmp_path):
    html = render_story_page(_model(tmp_path))
    assert "The GPU shortage got worse this month." in html
    assert "the gap, this week" in html
    assert 'data-ev="kpi:gpuRentalOnDemand"' in html
    assert "What tightened" in html and "What would close the gap" in html
    assert "Related coverage" in html and "CNBC" in html
    assert html.count("Source: ") >= 2       # chart + at least one scene
    assert "Tomorrow" in html
    assert "Entities" in html and "Findings" in html
    assert 'id="ev-data"' in html and "window.openEV" in html
    assert "revision" in html.lower()


def test_page_passes_its_own_lint(tmp_path):
    assert lint_story_copy(render_story_page(_model(tmp_path))) == []


def test_lint_catches_banned_words_outside_scripts():
    bad = "<p>Demand momentum is strengthening.</p><script>var momentum=1;</script>"
    hits = lint_story_copy(bad)
    assert any("momentum" in h for h in hits)
    assert any("strengthening" in h for h in hits)
    assert lint_story_copy("<script>var momentum=1;</script>") == []


def test_scene_first_paragraph_is_evidence_trigger(tmp_path):
    html = render_story_page(_model(tmp_path))
    assert 'data-ev="scene:1"' in html
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `../../.venv/Scripts/python -m pytest tests/dashboard/test_story_render.py -v -k "page or lint or trigger"`
Expected: FAIL — names not defined

- [ ] **Step 3: Write the implementation** (append)

```python
import re as _re

from gpu_agent.dashboard.site_render import page as _page

_BANNED_STORY = ["DMI", "SMI", "momentum", "strengthening", "tightening",
                 "accelerating", "allocation", "doctrine", "robust", "leverage"]


def lint_story_copy(html_text: str) -> list[str]:
    prose = _re.sub(r"<script.*?</script>", "", html_text,
                    flags=_re.S | _re.I)
    hits = []
    for w in _BANNED_STORY:
        if _re.search(rf"\b{w}\b", prose, _re.I):
            hits.append(f"banned word in page prose: {w}")
    if len(_re.findall(r"\bindexed?\b", prose, _re.I)) > 1:
        hits.append("'index/indexed' appears more than once")
    return hits


def _scene_html(scene: dict) -> str:
    paras = []
    for i, p in enumerate(scene["paragraphs"]):
        if i == 0:
            words = p.split(" ")
            head, tail = " ".join(words[:6]), " ".join(words[6:])
            paras.append(f'<p><a class="ev" href="#" '
                         f'data-ev="scene:{scene["n"]}">{esc(head)}'
                         f'<sup>ⓘ</sup></a> {esc(tail)}</p>')
        else:
            paras.append(f"<p>{esc(p)}</p>")
    vis = ""
    if scene["visual"]["series"]:
        vis = (f'<div class="st-visual">{spark_svg(scene["visual"]["series"], 300, 60)}'
               f'<span class="st-lab">{esc(scene["visual"]["label"])}</span></div>')
    rel = ""
    if scene["related"]:
        links = " ".join(
            f'<a href="{esc(r["url"])}" target="_blank" rel="noopener">'
            f'{esc(r["outlet"])} · {esc(r["title"])} · {esc(r["date"])}</a>'
            for r in scene["related"] if r["url"].startswith("http"))
        rel = f'<p class="st-related">Related coverage: {links}</p>'
    return (f'<article class="st-scene st-scene-{scene["accent"]}">'
            f'<i class="st-dot st-dot-{scene["accent"]}">{scene["n"]}</i>'
            f'<h2>{esc(scene["title"])}</h2>{"".join(paras)}{vis}'
            f'<p class="st-srcline">{esc(scene["source_line"])}</p>{rel}'
            f'</article>')


def _closing_strip(model: dict) -> str:
    chips = "".join(
        f'<span class="st-arch">{esc(a["label"])} · {esc(a["text"])}</span>'
        for a in model["archive"])
    return (f'<section class="st-closing"><p>Tomorrow’s entry will update '
            f'this story.</p>{chips}<a href="#">story archive →</a></section>')


_EXPLORE_DESC = {
    "entities": "companies and players, each with its own page",
    "findings": "every piece of evidence we’ve collected",
    "series": "the raw numbers over time",
    "history": "how our answer has changed"}


def _explore_band(model: dict) -> str:
    tiles = "".join(
        f'<a class="st-tile" href="appendix.html"><b>{k.title()} '
        f'({model["explore"].get(k, 0)})</b>'
        f'<span>{_EXPLORE_DESC[k]}</span></a>'
        for k in ["entities", "findings", "series", "history"])
    return f'<section class="st-explore">{tiles}</section>'


def render_story_page(model: dict) -> str:
    scenes = "".join(_scene_html(s) for s in model["scenes"])
    body = (f'<div class="st-page">{_headline_block(model)}'
            f'{_chart_block(model)}{_kpi_band(model)}'
            f'<section class="st-story"><h2 class="st-storyhead">The story, '
            f'step by step</h2>{scenes}</section>'
            f'{_closing_strip(model)}{_explore_band(model)}'
            f'<footer class="st-foot">Built by an autonomous research agent '
            f'· evidence-linked · revision {model["revision"]}</footer>'
            f'</div>{evidence_json(model["evidence"])}'
            f'{render_evidence_panel()}{render_condense_script()}')
    return _page(f'Merchant GPU — {model["headline"]}', body, depth=1)
```

Also append to `STORY_CSS` (same commit): `.st-scene{border-left:3px solid #eee;padding:4px 0 10px 18px;margin:0 0 8px;position:relative}`, `.st-scene .st-dot{position:absolute;left:-9px;top:6px}`, `.st-storyhead{font-size:14px;text-transform:uppercase;letter-spacing:.06em;color:#888}`, `.st-related{font-size:12px;color:#666}`, `.st-related a{color:#1f7a8c;margin-right:10px}`, `.st-visual{margin:8px 0;color:#1f7a8c}`, `.st-closing{border-top:1px solid #eee;padding:14px 0;font-size:13px}`, `.st-arch{display:inline-block;border:1px solid #ddd;border-radius:14px;padding:2px 10px;margin:0 6px 6px 0;font-size:12px;color:#555}`, `.st-explore{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0}`, `.st-tile{flex:1 1 150px;border:1px solid #ddd;border-radius:8px;padding:10px;text-decoration:none;color:#1c1c1c;font-size:12px}`, `.st-tile b{display:block;font-size:14px}`, `.st-foot{font-size:11px;color:#999;padding:16px 0;border-top:1px solid #eee}`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `../../.venv/Scripts/python -m pytest tests/dashboard/test_story_render.py -v`
Expected: 10 PASS

- [ ] **Step 5: Commit**

```bash
git add gpu_agent/dashboard/story_render.py tests/dashboard/test_story_render.py
git commit -m "feat(f101a): scenes, closing strip, explore band, full page + story lint"
```

---

### Task 8: Wire into the site build (`site_build.py`) + reconcile old index tests

**Files:**
- Modify: `gpu_agent/dashboard/site_build.py` (index swap + CSS + lint)
- Modify: `tests/dashboard/test_site_build.py` (reconcile index assertions — enumerated below, nothing silently gutted)
- Test: `tests/dashboard/test_site_build.py`

**Interfaces:**
- Consumes: `build_story_model`, `render_story_page`, `lint_story_copy`, `STORY_CSS`.
- Produces: `build_site(...)` now writes `<cat>/index.html` = story page; stylesheet = `SITE_CSS + BRIEF_CSS + DASHBOARD_CSS + STORY_CSS` (brief/dd CSS retained — appendix/how reuse `SITE_CSS`, and keeping donor CSS avoids touching those pages); summary dict gains `"story_lint": []`. `ValueError` raised if `lint_story_copy` reports violations (mirrors the existing brief-lint abort @site_build.py:38). The brief is NO LONGER rendered to any page (spec §9 default: no second entry page) — `render_brief` stays in-tree, unused by the build.

**Old-test reconciliation (explicit per-test plan):**
- `test_build_site_index_is_brief` → rename `test_build_site_index_is_story`; assert the new page (`"The story, step by step"`, `"says who?"` caption, `summary["story_lint"] == []`) instead of `"Executive Brief"`/`"Standing calls"`.
- Any other assertion in `test_site_build.py` that greps index.html for brief-only strings (`"Executive Brief"`, agenda tile markup) → point at the story-page equivalents. Assertions about appendix/how pages/root redirect stay UNCHANGED.
- `tests/dashboard/test_brief_render.py`, `test_brief_model.py`, `test_deepdive_*.py` keep passing untouched (they test module functions directly, not the build output). If any asserts build output, flag it in the task report — do not silently rewrite.

- [ ] **Step 1: Update the site-build test** (edit `tests/dashboard/test_site_build.py`)

```python
def test_build_site_index_is_story(tmp_path):
    summary = _build(tmp_path)          # existing helper @test_site_build.py:13
    idx = (tmp_path / "site" / CAT / "index.html").read_text(encoding="utf-8")
    assert "The story, step by step" in idx
    assert "says who?" in idx
    assert 'id="ev-data"' in idx
    assert "Executive Brief" not in idx
    assert summary["story_lint"] == []
    css = (tmp_path / "site" / CAT / "style.css").read_text(encoding="utf-8")
    assert ".st-chip" in css and ".ev-panel" in css
```

- [ ] **Step 2: Run to verify it fails**

Run: `../../.venv/Scripts/python -m pytest tests/dashboard/test_site_build.py -v`
Expected: new test FAILS (index is still the brief); note every OTHER failure — each must be on the enumerated reconciliation list above before you touch it.

- [ ] **Step 3: Modify `site_build.py`**

In `build_site` (@site_build.py:21): replace the brief render of index.html with:

```python
from gpu_agent.dashboard.story_model import build_story_model
from gpu_agent.dashboard.story_render import (STORY_CSS, lint_story_copy,
                                              render_story_page)

# inside build_site, replacing the render_brief index write:
story_model = build_story_model(category_id, store_dir, today or dt.date.today())
index_html = render_story_page(story_model)
story_lint = lint_story_copy(index_html)
if story_lint:
    raise ValueError(f"story copy lint failed: {story_lint}")
_write(out / category_id / "index.html", index_html)
```

CSS write becomes `SITE_CSS + BRIEF_CSS + DASHBOARD_CSS + STORY_CSS`; summary gains `"story_lint": story_lint`. Remove the now-dead `render_brief`/`build_brief_model` imports from `site_build.py` only (modules stay).

- [ ] **Step 4: Run the dashboard suite; reconcile enumerated tests**

Run: `../../.venv/Scripts/python -m pytest tests/dashboard/ -v`
Expected: green after the enumerated reconciliations; any failure NOT on the list → STOP and report (question-stop rule).

- [ ] **Step 5: Commit**

```bash
git add gpu_agent/dashboard/site_build.py tests/dashboard/test_site_build.py
git commit -m "feat(f101a): category index is now the narrative story page"
```

---

### Task 9: Real-store smoke build + full suite + close-out

**Files:**
- Create: `.superpowers/handoffs/f101a-story-page-DONE.md` (gitignored sentinel — written at the very end)
- No source changes expected; fix-forward only with enumerated causes.

- [ ] **Step 1: Real-store smoke build against a COPY of the live store**

```bash
mkdir -p ../../work/f101a-smoke && cp -r ../../store ../../work/f101a-smoke/store
../../.venv/Scripts/python -m gpu_agent site --store ../../work/f101a-smoke/store/chips.merchant-gpu --out ../../work/f101a-smoke/site
```

(Never build against the root `store/` in place — a concurrent cycle may be running; F100 precedent.) If the CLI's `--store` wiring passes the category dir rather than the store root to `build_story_model`, adapt `_site`/`build_site` param plumbing the same way `build_brief_model` receives it today (read `cli.py:1242-1260` first).

- [ ] **Step 2: Inspect the smoke output**

Open `work/f101a-smoke/site/chips.merchant-gpu/index.html` in a browser. Verify by eye + grep: headline present and jargon-free; gap chart renders with shaded gap + month ticks; KPI band shows the anchored rent chip (real $ value) + picks with sparklines; ≥2 scenes with source lines; evidence panel opens (click a chip) with real source links; hover tooltip appears; explore counts are the real 23/156/9/~44. Record the observed counts in the DONE sentinel.

- [ ] **Step 3: Full suite**

Run: `../../.venv/Scripts/python -m pytest -q`
Expected: all green, 3–6 skips, **F6 pin green** (`tests/test_evals_baseline_pin.py` untouched by this lane — if it is RED, STOP: something touched prompts; that is a lane-stop, not a fix-forward), scoring v1 replay pin green.

- [ ] **Step 4: Write the DONE sentinel**

`.superpowers/handoffs/f101a-story-page-DONE.md`: lane summary, task commits, smoke observations, any question-stops raised + answers, deferred items, "STOP before merge — only the user merges" (standing rule).

- [ ] **Step 5: Final commit**

```bash
git add -A && git status --short   # verify only intended files
git commit -m "feat(f101a): phase A close-out - smoke verified against store copy"
```

---

## Self-Review (run after writing; issues found → fixed inline)

1. **Spec coverage (Phase A slice):** headline §3.1 → T3/T6; gap chart §3.2 → T1/T2; KPI band §3.3 → T3/T6; stand-in story §3.4+§10.1 → T4/T7; closing strip §3.5 → T7; explore band §3.6 → T7; footer §3.7 → T7; hover+panel §5 → T5/T6; scripting scope §6 → T5/T6 (self-contained IIFEs only); visual language §7 → STORY_CSS; frozen core §8 → no task touches it; F100 relationship §9 → T8 (brief unmounted, donors retained). Phase B/C items (narrator artifact, related-coverage from day's corpus, real Explore sub-pages, story-archive pages) are explicitly OUT — stand-ins noted in T7.
2. **Placeholders:** none — every code step carries real code; T9's fix-forward is bounded by enumerated causes.
3. **Type consistency:** `build_story_model(category_id, store_dir, today)` consistent across T3/T4/T8; chip dict keys (`claim/label/value/arrow/spark/caption/tip/scene`) consistent T3→T6; evidence payload keys (`title/claim_text/findings/series/explore`) consistent T3/T4→T5; `lint_story_copy` return `list[str]` consistent T7→T8.
