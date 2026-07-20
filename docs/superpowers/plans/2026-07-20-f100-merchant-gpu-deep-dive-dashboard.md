# F100 — Merchant-GPU Deep-Dive Dashboard — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the `chips.merchant-gpu` category page into a scannable dashboard (trimmed brief, dynamic KPI cards, demand-vs-supply chart, clickable six dimensions) where every element opens a slide-in "why" panel; fold the TSMC implications and standing calls into those panels.

**Architecture:** Pure renderer/projection layer over existing store artifacts. A new **deep-dive model** assembles one payload per dimension (why / evidence / confidence / rating-trend / folded implications + calls). The brief renderer emits the new light-theme dashboard plus an embedded JSON blob + a small inline script that builds the slide-in panel on click. No brain, scoring, gather, or registry change.

**Tech Stack:** Python 3 (stdlib only), deterministic HTML/CSS/SVG string rendering, one self-contained inline `<script>` (no external assets — Cloudflare Pages serves the bundle as-is). Tests: pytest under `tests/dashboard/`.

## Global Constraints

- **Frozen core is out of bounds:** never edit `gpu_agent/scoring.py`, `gpu_agent/report.py`, the brains, the eval fixtures, or `registry/indicators.json`. (Question-stop rule applies: if a task seems to need a frozen-core edit, STOP and write `.superpowers/handoffs/f100-dashboard-QUESTIONS.md`.)
- **No run-cycle step added** → do not touch `EXPECTED_STEPS` / the F83 fingerprint.
- **Gates stay green:** `tests/test_evals_baseline_pin.py` (F6) and the scoring v1 replay pin must be green at every commit. This work emits no brain prompts, so they should never move; if F6 goes red, STOP — do not "fix" the pin.
- **Python:** always `.venv/Scripts/python` from repo root (`../../.venv/Scripts/python` from the worktree). One shared root venv.
- **Self-contained output:** inline CSS/JS only; no CDN, no external fonts/images. The site is static.
- **Exec-copy register:** all new prose is read by a non-technical executive — no AI/doctrine/internal jargon; the existing `lint_exec_copy` + `lint_tile_labels` gate in `site_build.py` must still pass (banned tokens include `\bF\d{2,3}\b`, "this/prior/last run", etc.).
- **Never raises:** every model function degrades missing/malformed data to a safe default (empty string / empty list), never a traceback — mirror the existing `_read_json` / `try/except` style in `brief_model.py`.
- **Isolation:** implement in worktree `.worktrees/f100-dashboard` on branch `f100-dashboard` (create via the using-git-worktrees skill). Never edit `store/` — a live cycle may be running.

## Reference: data shapes (already verified in-store)

- Scorecard `store/chips.merchant-gpu/YYYY-MM-vN.json`:
  - `categoryStatus`: `{rating, direction, reason, constraintLabel}`
  - `narrative`: str (the long brief)
  - `demandSupply`: `{dmiContribution: float, smiContribution: float, sdgi, ...}`
  - `dimensionRatings[name]`: `{rating, direction, confidence:{level,basis}, findingIds:[...], rationale, voteSpread}`
  - `dimensionStatus[name]`: `{confidenceCap: bool, ...}`
  - `findings[i]`: `{id, statement, why, trend, evidence:[{source,url,tier}], ...}`
- Thesis book `store/theses/<cat>/book.json` → `entries[i]`: `{title, lens, conviction, lastVerdict, streak, falsifiableTrigger, status}` — **has `lens`, no `dimensions`.**
- Implication `store/implications/<cat>/<asOf>.json` → `lines[i]`: `{watchItem|text, dimensions:[...], thesisIds, findingIds}` — **has `dimensions`.**

## File structure

- **Modify** `gpu_agent/dashboard/brief_model.py` — add `first_n_sentences`, `chart_series`, `dimension_rating_history`; extend `build_brief_model` output with `brief_two`, `chart`, `deepdive`.
- **Create** `gpu_agent/dashboard/deepdive_model.py` — maps + `build_deepdive_targets(...)`.
- **Create** `gpu_agent/dashboard/deepdive_render.py` — `deepdive_json(targets)`, `render_deepdive_panel()` (static panel shell + inline script).
- **Modify** `gpu_agent/dashboard/brief_render.py` — new `DASHBOARD_CSS`; rewrite `_verdict`, `_agenda`, `_dims`; add `_chart`; drop `_tsmc`/`_calls` from `render_brief`; append the deep-dive panel + script.
- **Modify** `gpu_agent/dashboard/site_build.py` — bundle `SITE_CSS + DASHBOARD_CSS` (replacing `BRIEF_CSS`).
- **Tests:** `tests/dashboard/test_deepdive_model.py`, `tests/dashboard/test_deepdive_render.py`, additions to `tests/dashboard/test_brief_model.py` and `tests/dashboard/test_brief_render.py`.

---

## Phase 1 — model layer

### Task 1: Two-sentence brief

**Files:**
- Modify: `gpu_agent/dashboard/brief_model.py`
- Test: `tests/dashboard/test_brief_model.py`

**Interfaces:**
- Produces: `first_n_sentences(text: str, n: int = 2) -> str`; `build_brief_model(...)` output gains key `"brief_two": str`.

- [ ] **Step 1: Write the failing test**

```python
# tests/dashboard/test_brief_model.py  (add)
from gpu_agent.dashboard.brief_model import first_n_sentences

def test_first_n_sentences_takes_two():
    t = "Demand is at record levels. The gap is narrowing. A third point."
    assert first_n_sentences(t, 2) == "Demand is at record levels. The gap is narrowing."

def test_first_n_sentences_short_input_returns_all():
    assert first_n_sentences("Only one here.", 2) == "Only one here."

def test_first_n_sentences_empty():
    assert first_n_sentences("", 2) == "" and first_n_sentences(None, 2) == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/dashboard/test_brief_model.py -k first_n_sentences -v`
Expected: FAIL (ImportError: cannot import name `first_n_sentences`).

- [ ] **Step 3: Implement**

```python
# gpu_agent/dashboard/brief_model.py  — add near _first_sentence
def first_n_sentences(text, n=2):
    text = (text or "").strip()
    out, rest = [], text
    for _ in range(n):
        s = _first_sentence(rest)
        if not s:
            break
        out.append(s)
        rest = rest[len(s):].strip()
        if not rest:
            break
    return " ".join(out)
```

Then in `build_brief_model`, add to the returned dict (next to `"narrative"`):

```python
        "brief_two": first_n_sentences(latest.get("narrative") or "", 2),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/dashboard/test_brief_model.py -k first_n_sentences -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add gpu_agent/dashboard/brief_model.py tests/dashboard/test_brief_model.py
git commit -m "F100: two-sentence brief projection"
```

---

### Task 2: Demand-vs-supply chart series

**Files:**
- Modify: `gpu_agent/dashboard/brief_model.py`
- Test: `tests/dashboard/test_brief_model.py`

**Interfaces:**
- Produces: `chart_series(cat_dir, limit: int = 12) -> dict` = `{"labels": list[str], "demand": list[float], "supply": list[float]}` (chronological, oldest→newest, monthly revisions only). `build_brief_model` output gains key `"chart": <that dict>`.

- [ ] **Step 1: Write the failing test**

```python
# tests/dashboard/test_brief_model.py  (add)
import json
from gpu_agent.dashboard.brief_model import chart_series

def _rev(cat, name, dmi, smi):
    (cat / name).write_text(json.dumps({
        "asOf": name[:7], "demandSupply": {"dmiContribution": dmi, "smiContribution": smi},
        "findings": []}), encoding="utf-8")

def test_chart_series_orders_and_limits(tmp_path):
    cat = tmp_path / "store" / CAT; cat.mkdir(parents=True)
    _rev(cat, "2026-07-v1.json", 1.0, -0.2)
    _rev(cat, "2026-07-v2.json", 1.5, -0.1)
    _rev(cat, "2026-07-v3.json", 2.0, 0.1)
    (cat / "2026-07-05-v1.json").write_text(json.dumps({"demandSupply": {}, "findings": []}), encoding="utf-8")  # daily excluded
    s = chart_series(cat, limit=2)
    assert s["demand"] == [1.5, 2.0]        # last 2, chronological
    assert s["supply"] == [-0.1, 0.1]
    assert s["labels"] == ["2026-07-v2", "2026-07-v3"]

def test_chart_series_missing_dir_is_empty(tmp_path):
    s = chart_series(tmp_path / "nope")
    assert s == {"labels": [], "demand": [], "supply": []}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/dashboard/test_brief_model.py -k chart_series -v`
Expected: FAIL (ImportError).

- [ ] **Step 3: Implement**

```python
# gpu_agent/dashboard/brief_model.py — add (reuses _MONTHLY_RE, _read_json)
def chart_series(cat_dir, limit=12):
    cat_dir = Path(cat_dir)
    try:
        paths = list(cat_dir.iterdir())
    except OSError:
        return {"labels": [], "demand": [], "supply": []}
    revs = sorted(((m.group(1), int(m.group(2)), p)
                   for p in paths for m in [_MONTHLY_RE.match(p.name)] if m),
                  key=lambda t: (t[0], t[1]))[-limit:]
    labels, demand, supply = [], [], []
    for as_of, rev, p in revs:
        art = _read_json(p) or {}
        ds = art.get("demandSupply")
        ds = ds if isinstance(ds, dict) else {}
        labels.append(f"{as_of}-v{rev}")
        demand.append(float(ds.get("dmiContribution") or 0.0))
        supply.append(float(ds.get("smiContribution") or 0.0))
    return {"labels": labels, "demand": demand, "supply": supply}
```

Add to `build_brief_model` returned dict:

```python
        "chart": chart_series(cat_dir),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/dashboard/test_brief_model.py -k chart_series -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add gpu_agent/dashboard/brief_model.py tests/dashboard/test_brief_model.py
git commit -m "F100: demand/supply chart series projection"
```

---

### Task 3: Dimension rating-history (for panel sparklines)

**Files:**
- Modify: `gpu_agent/dashboard/brief_model.py`
- Test: `tests/dashboard/test_brief_model.py`

**Interfaces:**
- Produces: `dimension_rating_history(cat_dir, limit: int = 12) -> dict[str, list[float]]` — per dimension name, an ordinal series (chronological) using `deepdive_model.RATING_ORDINAL` (default 1 for unknown words). Imported lazily to avoid a cycle.

- [ ] **Step 1: Write the failing test**

```python
# tests/dashboard/test_brief_model.py  (add)
from gpu_agent.dashboard.brief_model import dimension_rating_history

def _rev_dims(cat, name, bott):
    (cat / name).write_text(json.dumps({
        "dimensionRatings": {"bottleneck": {"rating": bott}}, "findings": []}),
        encoding="utf-8")

def test_dimension_rating_history_ordinals(tmp_path):
    cat = tmp_path / "store" / CAT; cat.mkdir(parents=True)
    _rev_dims(cat, "2026-07-v1.json", "Weak")
    _rev_dims(cat, "2026-07-v2.json", "Strong")
    h = dimension_rating_history(cat)
    assert h["bottleneck"] == [0.0, 2.0]   # Weak=0, Strong=2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/dashboard/test_brief_model.py -k rating_history -v`
Expected: FAIL (ImportError).

- [ ] **Step 3: Implement** (Task 4 creates `deepdive_model.RATING_ORDINAL`; this task imports it — implement Task 4's map first if executing strictly in order, or add the constant in Task 4 and re-run. To keep this task self-contained, define the map inline and Task 4 will import *from here*.)

```python
# gpu_agent/dashboard/brief_model.py — add
RATING_ORDINAL = {"weak": 0.0, "mixed": 1.0, "moderate": 1.0,
                  "strong": 2.0, "very strong": 3.0}

def dimension_rating_history(cat_dir, limit=12):
    cat_dir = Path(cat_dir)
    try:
        paths = list(cat_dir.iterdir())
    except OSError:
        return {}
    revs = sorted(((m.group(1), int(m.group(2)), p)
                   for p in paths for m in [_MONTHLY_RE.match(p.name)] if m),
                  key=lambda t: (t[0], t[1]))[-limit:]
    hist = {}
    for _, _, p in revs:
        art = _read_json(p) or {}
        ratings = art.get("dimensionRatings")
        if not isinstance(ratings, dict):
            continue
        for name, r in ratings.items():
            if not isinstance(r, dict):
                continue
            word = (r.get("rating") or "").strip().lower()
            hist.setdefault(name, []).append(RATING_ORDINAL.get(word, 1.0))
    return hist
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/dashboard/test_brief_model.py -k rating_history -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add gpu_agent/dashboard/brief_model.py tests/dashboard/test_brief_model.py
git commit -m "F100: per-dimension rating history projection"
```

---

### Task 4: Deep-dive model — payload per dimension

**Files:**
- Create: `gpu_agent/dashboard/deepdive_model.py`
- Test: `tests/dashboard/test_deepdive_model.py`

**Interfaces:**
- Consumes: scorecard dict (`latest`), `rating_history` (Task 3), thesis `book_entries` (list), `implication_lines` (list from `read_implication_lines`).
- Produces:
  - `LENS_TO_DIMENSION: dict[str,str]`, `SLOT_TO_DIMENSION: dict[str,str]` (re-exports `RATING_ORDINAL` from `brief_model`).
  - `build_deepdive_targets(latest, rating_history, book_entries, implication_lines) -> dict[str, dict]` keyed by dimension name; each value:
    `{eyebrow, title, badges:[{text,tone}], why, trend:[float], trend_good:bool, evidence:[{source,trend,text,url}], confidence, change, tsmc:[str], calls:[{title,verdict,trigger}]}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/dashboard/test_deepdive_model.py
from gpu_agent.dashboard.deepdive_model import (
    LENS_TO_DIMENSION, SLOT_TO_DIMENSION, build_deepdive_targets)

def _latest():
    return {
      "dimensionRatings": {"bottleneck": {
          "rating": "Weak", "direction": "improving",
          "confidence": {"level": "medium", "basis": "3/3 samples; capped"},
          "voteSpread": "3/3 Weak", "rationale": "Packaging sold out. Gap narrowing.",
          "findingIds": ["f1", "f2"]}},
      "dimensionStatus": {"bottleneck": {"confidenceCap": True}},
      "findings": [
          {"id": "f1", "statement": "CoWoS sold out through 2027.", "trend": "rising",
           "evidence": [{"source": "TradingKey", "url": "https://x", "tier": "secondary"}]},
          {"id": "f2", "statement": "Gap narrows to 10%.", "trend": "falling",
           "evidence": [{"source": "TrendForce", "url": "https://y", "tier": "secondary"}]}],
    }

def test_maps_present():
    assert LENS_TO_DIMENSION["supply"] == "bottleneck"
    assert SLOT_TO_DIMENSION["binding-constraint"] == "bottleneck"

def test_build_targets_bottleneck_payload():
    calls = [{"title": "Supply binding", "lens": "supply",
              "falsifiableTrigger": "HBM eases", "lastVerdict": "reaffirmed"}]
    impls = [{"text": "Packaging caps GPU revenue.", "dimensions": ["bottleneck"]}]
    t = build_deepdive_targets(_latest(), {"bottleneck": [0.0, 2.0]}, calls, impls)
    b = t["bottleneck"]
    assert b["title"].startswith("bottleneck")
    assert "Packaging sold out" in b["why"]
    assert b["trend"] == [0.0, 2.0]
    assert b["trend_good"] is True                       # improving → good
    assert len(b["evidence"]) == 2 and b["evidence"][0]["source"] == "TradingKey"
    assert "3/3 Weak" in b["confidence"]
    assert b["tsmc"] == ["Packaging caps GPU revenue."]
    assert b["calls"][0]["trigger"] == "HBM eases"
    assert b["change"] == "HBM eases"                    # first mapped call's trigger
    assert any(x["text"] == "Weak" for x in b["badges"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/dashboard/test_deepdive_model.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement**

```python
# gpu_agent/dashboard/deepdive_model.py
"""F100 deep-dive payloads — one per dimension, projected from store artifacts.
Pure, never raises: missing/malformed data degrades to empty."""
from __future__ import annotations

from .brief_model import RATING_ORDINAL  # re-exported

LENS_TO_DIMENSION = {"demand": "momentum", "supply": "bottleneck",
                     "risk": "strategicRisk", "competitive": "competitiveStructure"}
SLOT_TO_DIMENSION = {"demand-durability": "momentum",
                     "binding-constraint": "bottleneck",
                     "customer-mix": "competitiveStructure",
                     "end-market-economics": "unitEconomics",
                     "demand-quality": "strategicRisk"}

_RATING_TONE = {"weak": "bad", "mixed": "neutral", "strong": "good",
                "very strong": "good"}
_DIR_TONE = {"improving": "good", "steady": "neutral", "worsening": "bad"}
# "improving" is good even when the current rating is weak (bottleneck easing).
_GOOD_DIRECTION = {"improving"}


def _findings_by_id(latest):
    out = {}
    for f in (latest.get("findings") or []):
        if isinstance(f, dict) and f.get("id"):
            out[f["id"]] = f
    return out


def build_deepdive_targets(latest, rating_history, book_entries, implication_lines):
    ratings = latest.get("dimensionRatings")
    if not isinstance(ratings, dict):
        return {}
    dstat = latest.get("dimensionStatus")
    dstat = dstat if isinstance(dstat, dict) else {}
    fbi = _findings_by_id(latest)

    # pre-group folded content by dimension
    impl_by_dim = {}
    for ln in (implication_lines or []):
        text = ln.get("text") or ln.get("watchItem")
        for dim in (ln.get("dimensions") or []):
            if text:
                impl_by_dim.setdefault(dim, []).append(text)
    calls_by_dim = {}
    for e in (book_entries or []):
        dim = LENS_TO_DIMENSION.get(e.get("lens"))
        if dim:
            calls_by_dim.setdefault(dim, []).append({
                "title": e.get("title") or "",
                "verdict": e.get("lastVerdict") or "not yet judged",
                "trigger": e.get("falsifiableTrigger") or ""})

    out = {}
    for name, r in ratings.items():
        if not isinstance(r, dict):
            continue
        rating = r.get("rating") or "—"
        direction = r.get("direction") or "steady"
        conf = r.get("confidence")
        conf = conf if isinstance(conf, dict) else {}
        capped = bool(dstat.get(name, {}).get("confidenceCap")) if isinstance(dstat.get(name), dict) else False

        badges = [{"text": rating, "tone": _RATING_TONE.get(rating.lower(), "neutral")},
                  {"text": f"{direction}", "tone": _DIR_TONE.get(direction, "neutral")}]
        if conf.get("level"):
            badges.append({"text": f"{conf['level']} confidence", "tone": "neutral"})
        if capped:
            badges.append({"text": "confidence capped", "tone": "neutral"})

        evidence = []
        for fid in (r.get("findingIds") or [])[:5]:
            f = fbi.get(fid)
            if not isinstance(f, dict):
                continue
            ev0 = next((x for x in (f.get("evidence") or []) if isinstance(x, dict)), {})
            evidence.append({"source": ev0.get("source") or "source",
                             "trend": f.get("trend") or "",
                             "text": f.get("statement") or "",
                             "url": ev0.get("url") or ""})

        calls = calls_by_dim.get(name, [])
        conf_basis = conf.get("basis") or ""
        vote = r.get("voteSpread") or ""
        confidence = " · ".join(x for x in (vote, conf_basis) if x)

        out[name] = {
            "eyebrow": "Dimension" + (" · confidence capped" if capped else ""),
            "title": f"{name} — {rating}, {direction}",
            "badges": badges,
            "why": r.get("rationale") or "",
            "trend": list(rating_history.get(name) or []),
            "trend_good": direction in _GOOD_DIRECTION or rating.lower() in ("strong", "very strong"),
            "evidence": evidence,
            "confidence": confidence,
            "change": calls[0]["trigger"] if calls else "",
            "tsmc": impl_by_dim.get(name, []),
            "calls": calls,
        }
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/dashboard/test_deepdive_model.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add gpu_agent/dashboard/deepdive_model.py tests/dashboard/test_deepdive_model.py
git commit -m "F100: deep-dive payload model (per dimension, folded calls+implications)"
```

---

### Task 5: Wire deep-dive targets into the brief model

**Files:**
- Modify: `gpu_agent/dashboard/brief_model.py`
- Test: `tests/dashboard/test_brief_model.py`

**Interfaces:**
- Consumes: Task 3 `dimension_rating_history`, Task 4 `build_deepdive_targets`, existing `read_thesis_book` / `read_implication_lines`.
- Produces: `build_brief_model(...)` output gains key `"deepdive": dict[str,dict]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/dashboard/test_brief_model.py  (add)
from gpu_agent.dashboard.brief_model import build_brief_model
import datetime

def test_build_brief_model_has_deepdive(tmp_path):
    root = tmp_path / "store"; cat = root / CAT; cat.mkdir(parents=True)
    (cat / "2026-07-v1.json").write_text(json.dumps({
        "asOf": "2026-07", "narrative": "One. Two. Three.",
        "categoryStatus": {"rating": "Strong", "direction": "improving", "reason": "r."},
        "dimensionRatings": {"bottleneck": {"rating": "Weak", "direction": "improving",
            "confidence": {"level": "medium", "basis": "b"}, "rationale": "Why text.",
            "findingIds": [], "voteSpread": "3/3 Weak"}},
        "dimensionStatus": {}, "findings": []}), encoding="utf-8")
    m = build_brief_model(CAT, root, datetime.date(2026, 7, 20))
    assert "bottleneck" in m["deepdive"]
    assert m["deepdive"]["bottleneck"]["why"] == "Why text."
    assert m["brief_two"] == "One. Two."
    assert "demand" in m["chart"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/dashboard/test_brief_model.py -k has_deepdive -v`
Expected: FAIL (KeyError: 'deepdive').

- [ ] **Step 3: Implement**

At the top of `brief_model.py` imports add:

```python
from .deepdive_model import build_deepdive_targets
```

In `build_brief_model`, after `book = read_thesis_book(...)` and the `tsmc`/implication read, compute and add to the returned dict:

```python
        "deepdive": build_deepdive_targets(
            latest,
            dimension_rating_history(cat_dir),
            book,
            read_implication_lines(store_root, category_id, as_of)),
```

(`book` and the implication lines are already read in the function; reuse them — do not re-read.)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/dashboard/test_brief_model.py -k has_deepdive -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add gpu_agent/dashboard/brief_model.py tests/dashboard/test_brief_model.py
git commit -m "F100: expose deepdive payloads on the brief model"
```

---

## Phase 2 — render layer

### Task 6: Deep-dive panel renderer (JSON blob + shell + script)

**Files:**
- Create: `gpu_agent/dashboard/deepdive_render.py`
- Test: `tests/dashboard/test_deepdive_render.py`

**Interfaces:**
- Consumes: `targets` dict from Task 4.
- Produces:
  - `deepdive_json(targets) -> str` — a `<script type="application/json" id="dd-data">…</script>` block, HTML-safe (escapes `<`).
  - `render_deepdive_panel() -> str` — the static scrim + drawer shell + the inline `<script>` that reads `#dd-data`, and on `openDD(key)` fills the drawer; closes on scrim click / Esc.

- [ ] **Step 1: Write the failing test**

```python
# tests/dashboard/test_deepdive_render.py
import json, re
from gpu_agent.dashboard.deepdive_render import deepdive_json, render_deepdive_panel

def test_deepdive_json_roundtrips_and_escapes():
    blob = deepdive_json({"bottleneck": {"why": "a < b & c", "evidence": []}})
    m = re.search(r'id="dd-data"[^>]*>(.*?)</script>', blob, re.S)
    data = json.loads(m.group(1).replace("\\u003c", "<"))
    assert data["bottleneck"]["why"] == "a < b & c"
    assert "<" not in m.group(1)               # raw '<' must be escaped for safety

def test_panel_shell_has_hooks():
    html = render_deepdive_panel()
    assert 'id="dd-scrim"' in html and 'id="dd-drawer"' in html
    assert "function openDD" in html and "dd-data" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/dashboard/test_deepdive_render.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement**

```python
# gpu_agent/dashboard/deepdive_render.py
"""F100 deep-dive panel — embedded JSON + a self-contained inline script.
No external assets. The script builds the slide-in panel from #dd-data on click."""
from __future__ import annotations

import json


def deepdive_json(targets) -> str:
    # ensure_ascii keeps it single-byte; escape '<' so the blob can't break out
    # of the <script> or inject markup.
    blob = json.dumps(targets, ensure_ascii=True).replace("<", "\\u003c")
    return f'<script type="application/json" id="dd-data">{blob}</script>'


_PANEL = """
<div class="dd-scrim" id="dd-scrim" onclick="closeDD()"></div>
<aside class="dd-drawer" id="dd-drawer" aria-hidden="true">
  <button class="dd-close" onclick="closeDD()" aria-label="Close">×</button>
  <div id="dd-head"></div><div id="dd-body"></div>
</aside>
<script>
(function(){
  var DATA={};
  try{DATA=JSON.parse(document.getElementById('dd-data').textContent);}catch(e){}
  function esc(s){var d=document.createElement('div');d.textContent=s==null?'':s;return d.innerHTML;}
  function spark(v,good){
    if(!v||!v.length)return '';
    var w=420,h=48,mn=Math.min.apply(0,v),mx=Math.max.apply(0,v),r=(mx-mn)||1,c=good?'#2e7d32':'#c0632a';
    var p=v.map(function(y,i){return (i/(v.length-1)*w).toFixed(0)+','+(h-4-(y-mn)/r*(h-10)).toFixed(0);}).join(' ');
    return '<svg viewBox="0 0 '+w+' '+h+'" width="100%" height="'+h+'"><polyline fill="none" stroke="'+c+'" stroke-width="2.5" points="'+p+'"/></svg>';
  }
  window.openDD=function(k){
    var d=DATA[k];if(!d)return;
    var tone={good:'#e6f4ea',bad:'#fdeae6',neutral:'#f0f2f5'},ink={good:'#1e7a34',bad:'#b23a12',neutral:'#555'};
    var bd=(d.badges||[]).map(function(b){return '<span class="dd-badge" style="background:'+tone[b.tone]+';color:'+ink[b.tone]+'">'+esc(b.text)+'</span>';}).join('');
    document.getElementById('dd-head').innerHTML='<div class="dd-eyebrow">'+esc(d.eyebrow)+'</div><div class="dd-title">'+esc(d.title)+'</div>'+bd;
    var h='';
    if(d.why){h+='<div class="dd-l">Why it\\'s rated this way</div><p class="dd-why">'+esc(d.why)+'</p>';}
    if(d.trend&&d.trend.length){h+='<div class="dd-l">Trend</div>'+spark(d.trend,d.trend_good);}
    if(d.evidence&&d.evidence.length){h+='<div class="dd-l">Evidence ('+d.evidence.length+')</div>';
      d.evidence.forEach(function(e){var a=/^https?:/.test(e.url||'')?' <a href="'+esc(e.url)+'">open source \\u2192</a>':'';
        h+='<div class="dd-ev"><b>'+esc(e.source)+'</b> <span class="dd-t">'+esc(e.trend)+'</span><div>'+esc(e.text)+'</div>'+a+'</div>';});}
    if(d.confidence){h+='<div class="dd-l">Confidence</div><div class="dd-box">'+esc(d.confidence)+'</div>';}
    if(d.change){h+='<div class="dd-l">What would change our mind</div><div class="dd-box">'+esc(d.change)+'</div>';}
    if(d.tsmc&&d.tsmc.length){h+='<div class="dd-l">What this means for TSMC</div>';
      d.tsmc.forEach(function(t){h+='<p class="dd-why">'+esc(t)+'</p>';});}
    if(d.calls&&d.calls.length){h+='<div class="dd-l">Standing calls</div>';
      d.calls.forEach(function(c){h+='<div class="dd-ev"><b>'+esc(c.title)+'</b> \\u2014 '+esc(c.verdict)+'<div class="dd-t">'+esc(c.trigger)+'</div></div>';});}
    document.getElementById('dd-body').innerHTML=h;
    document.getElementById('dd-scrim').classList.add('open');
    var dr=document.getElementById('dd-drawer');dr.classList.add('open');dr.setAttribute('aria-hidden','false');
  };
  window.closeDD=function(){
    document.getElementById('dd-scrim').classList.remove('open');
    var dr=document.getElementById('dd-drawer');dr.classList.remove('open');dr.setAttribute('aria-hidden','true');
  };
  document.addEventListener('keydown',function(e){if(e.key==='Escape')closeDD();});
})();
</script>
"""


def render_deepdive_panel() -> str:
    return _PANEL
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/dashboard/test_deepdive_render.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add gpu_agent/dashboard/deepdive_render.py tests/dashboard/test_deepdive_render.py
git commit -m "F100: deep-dive panel renderer (embedded JSON + inline script)"
```

---

### Task 7: New dashboard CSS theme

**Files:**
- Modify: `gpu_agent/dashboard/brief_render.py` (add `DASHBOARD_CSS`)
- Test: `tests/dashboard/test_brief_render.py`

**Interfaces:**
- Produces: module constant `DASHBOARD_CSS: str` covering `.dash-*`, `.kcard`, `.dd-*`, `.dimrow`, `.ddchart`, light theme.

- [ ] **Step 1: Write the failing test**

```python
# tests/dashboard/test_brief_render.py  (add)
from gpu_agent.dashboard.brief_render import DASHBOARD_CSS

def test_dashboard_css_covers_core_classes():
    for sel in [".kcard", ".dd-drawer", ".dd-scrim", ".dimrow", ".ddchart", ".brief-two"]:
        assert sel in DASHBOARD_CSS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/dashboard/test_brief_render.py -k dashboard_css -v`
Expected: FAIL (ImportError).

- [ ] **Step 3: Implement** — add to `brief_render.py`. (Full stylesheet; light editorial theme, cards, chart, clickable dim rows, slide-in drawer. Keep colours from the approved mockup: bg `#fbfaf7`, accent green `#2e7d32`, muted gold `#8a6d3b`.)

```python
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
"""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/dashboard/test_brief_render.py -k dashboard_css -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add gpu_agent/dashboard/brief_render.py tests/dashboard/test_brief_render.py
git commit -m "F100: dashboard CSS theme (light cards, chart, deep-dive drawer)"
```

---

### Task 8: New brief sections — verdict, KPI cards, chart, dims

**Files:**
- Modify: `gpu_agent/dashboard/brief_render.py`
- Test: `tests/dashboard/test_brief_render.py`

**Interfaces:**
- Consumes: `model` keys `brief_two`, `agenda`, `chart`, `dimensions` (+ `SLOT_TO_DIMENSION` mapping by slot label→id).
- Produces: internal renderers `_verdict`, `_kpi_cards`, `_chart`, `_dims_list` returning HTML strings. KPI cards and dim rows carry `onclick="openDD('<dimension>')"`.

**Note on the slot→dimension link:** `model["agenda"][i]["slot_label"]` is the human label (e.g. "Binding constraint"). Map it to a slot id via a label→id lookup built from `registry/agenda-slots.json` labels, then `SLOT_TO_DIMENSION`. Add a small module-level dict `_SLOT_LABEL_TO_ID` loaded once from `load_slots()`.

- [ ] **Step 1: Write the failing test**

```python
# tests/dashboard/test_brief_render.py  (add)
from gpu_agent.dashboard.brief_render import _verdict, _kpi_cards, _chart, _dims_list

def test_verdict_uses_two_sentence_and_rating():
    m = {"status": {"rating": "Strong", "direction": "improving"}, "brief_two": "One. Two."}
    h = _verdict(m)
    assert "Strong" in h and "One. Two." in h and "brief-two" in h

def test_kpi_cards_clickable_to_dimension():
    m = {"agenda": [{"slot_label": "Binding constraint", "metric_label": "Lead times",
                     "display": "40 wk", "trend_word": "rising", "as_of": "2026-07-16",
                     "source": "TechTimes", "was": "", "delta_line": ""}]}
    h = _kpi_cards(m)
    assert "openDD('bottleneck')" in h and "40 wk" in h and "Lead times" in h

def test_chart_draws_two_polylines():
    m = {"chart": {"labels": ["a", "b"], "demand": [1.0, 2.0], "supply": [-0.1, 0.1]}}
    h = _chart(m)
    assert h.count("<polyline") >= 2 and "ddchart" in h

def test_dims_list_rows_clickable():
    m = {"dimensions": [{"name": "bottleneck", "rating": "Weak", "direction": "improving",
                         "confidence": "medium", "sentence": "s", "capped": True}]}
    h = _dims_list(m)
    assert "openDD('bottleneck')" in h and "Weak" in h
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/dashboard/test_brief_render.py -k "verdict or kpi or chart or dims_list" -v`
Expected: FAIL (ImportError for `_kpi_cards`/`_chart`/`_dims_list`; `_verdict` signature differs).

- [ ] **Step 3: Implement** — in `brief_render.py`:

```python
from .deepdive_model import SLOT_TO_DIMENSION
from .agenda import load_slots

_RATING_DOT = {"very strong": "#2e7d32", "strong": "#2e7d32", "mixed": "#f9a825",
               "moderate": "#f9a825", "weak": "#ef6c00"}
_DELTA_GOOD = {"rising": "#1e7a34", "falling": "#c0632a"}  # default green up / amber down

def _slot_label_to_id():
    try:
        return {s["label"]: s["id"] for s in load_slots()}
    except Exception:
        return {}
_SLOT_LABEL_TO_ID = _slot_label_to_id()

def _verdict(m):
    s = m["status"]
    dash = f" / {e(s['direction'])}" if s.get("direction") else ""
    return (f'<div class="rating-label">{e(s["rating"])}{dash}</div>'
            f'<p class="brief-two">{e(m.get("brief_two") or "")}</p>')

def _kpi_cards(m):
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

def _chart(m):
    c = m.get("chart") or {}
    dem, sup = c.get("demand") or [], c.get("supply") or []
    if len(dem) < 2:
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

def _dims_list(m):
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/dashboard/test_brief_render.py -k "verdict or kpi or chart or dims_list" -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add gpu_agent/dashboard/brief_render.py tests/dashboard/test_brief_render.py
git commit -m "F100: dashboard section renderers (verdict, KPI cards, chart, dim rows)"
```

---

### Task 9: Assemble `render_brief`; fold calls/implications out of the main flow; attach panel

**Files:**
- Modify: `gpu_agent/dashboard/brief_render.py`
- Test: `tests/dashboard/test_brief_render.py`

**Interfaces:**
- Consumes: all Task 6–8 pieces + `model["deepdive"]`.
- Produces: updated `render_brief(model)` — new body order: masthead → verdict → KPI cards → `<div class="dash2">` chart + dims → latest-signal strip → footer → deep-dive JSON blob → panel shell. `_tsmc`/`_calls` are **no longer called** by `render_brief` (their content now lives in the panel via `deepdive`). Keep the functions defined (still unit-tested) but unused by the main page.

- [ ] **Step 1: Write the failing test**

```python
# tests/dashboard/test_brief_render.py  (add)
from gpu_agent.dashboard.brief_render import render_brief

def _model():
    return {
      "category_label": "Merchant GPU", "month_label": "July 2026", "revision": 12,
      "last_check": "2026-07-20", "stale": False,
      "attention": {"word": "elevated", "css": "elevated", "raw_word": "elevated", "lagging": False},
      "status": {"rating": "Strong", "direction": "improving", "reason": "r.", "constraint": ""},
      "brief_two": "One. Two.",
      "agenda": [{"slot_label": "Binding constraint", "metric_label": "Lead times",
                  "display": "40 wk", "trend_word": "rising", "as_of": "2026-07-16",
                  "source": "TechTimes", "was": "", "delta_line": ""}] * 3,
      "chart": {"labels": ["a", "b"], "demand": [1.0, 2.0], "supply": [-0.1, 0.1]},
      "dimensions": [{"name": "bottleneck", "rating": "Weak", "direction": "improving",
                      "confidence": "medium", "sentence": "s", "capped": True}],
      "strip": [], "tsmc": [], "calls": {"rows": [], "total": 0, "provisional": 0},
      "evidence": {"n": 1, "median": "2026-07-01", "oldest": "2026-06-01", "primary": 1},
      "deepdive": {"bottleneck": {"eyebrow": "Dimension", "title": "bottleneck — Weak, improving",
                   "badges": [], "why": "w", "trend": [0, 2], "trend_good": True,
                   "evidence": [], "confidence": "3/3 Weak", "change": "x", "tsmc": [], "calls": []}},
    }

def test_render_brief_dashboard_shape():
    h = render_brief(_model())
    assert 'id="dd-data"' in h and 'id="dd-drawer"' in h        # panel wired
    assert "kcards" in h and "ddchart" in h and "dimlist" in h  # new sections
    assert "<h2>What this means for TSMC</h2>" not in h         # folded away
    assert "<h2>Standing calls</h2>" not in h                   # folded away
    assert '"bottleneck"' in h                                  # payload embedded
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/dashboard/test_brief_render.py -k dashboard_shape -v`
Expected: FAIL (old `render_brief` still emits the TSMC/calls `<h2>` and no `dd-data`).

- [ ] **Step 3: Implement** — update imports and `render_brief`:

```python
from .deepdive_render import deepdive_json, render_deepdive_panel

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/dashboard/test_brief_render.py -v`
Expected: PASS (all brief_render tests).

- [ ] **Step 5: Commit**

```bash
git add gpu_agent/dashboard/brief_render.py tests/dashboard/test_brief_render.py
git commit -m "F100: assemble dashboard render_brief; fold TSMC/calls into deep-dive"
```

---

### Task 10: Bundle the new CSS in the site build

**Files:**
- Modify: `gpu_agent/dashboard/site_build.py`
- Test: `tests/dashboard/test_site_build.py`

**Interfaces:**
- Consumes: `DASHBOARD_CSS`.
- Produces: `style.css` = `SITE_CSS + DASHBOARD_CSS` (BRIEF_CSS retained for the older `.hero`/`.kpis` classes still used by appendix/how pages **only if referenced**; otherwise drop it). Keep the exec-copy lint gate.

- [ ] **Step 1: Write the failing test**

```python
# tests/dashboard/test_site_build.py  (add — follow the file's existing build harness)
def test_style_css_includes_dashboard_theme(tmp_path):
    out = _run_build(tmp_path)        # reuse this module's existing build helper
    css = (out / "chips.merchant-gpu" / "style.css").read_text(encoding="utf-8")
    assert ".kcard" in css and ".dd-drawer" in css
```

(If `test_site_build.py` has no reusable helper, build inline with `build_site(CAT, <fixture store>, work, plain, out, today=date(2026,7,20))` mirroring `test_build_e2e.py`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/dashboard/test_site_build.py -k dashboard_theme -v`
Expected: FAIL (`.kcard` not in css).

- [ ] **Step 3: Implement** — in `site_build.py`:

```python
from .brief_render import BRIEF_CSS, DASHBOARD_CSS, lint_exec_copy, lint_tile_labels, render_brief
...
    bundle = SITE_CSS + BRIEF_CSS + DASHBOARD_CSS
    _write(out / "style.css", bundle)
    _write(cat / "style.css", bundle)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/dashboard/test_site_build.py -k dashboard_theme -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add gpu_agent/dashboard/site_build.py tests/dashboard/test_site_build.py
git commit -m "F100: bundle dashboard CSS into the site build"
```

---

## Phase 3 — full page, smoke, gates

### Task 11: Panel "full page" link → appendix anchor

**Files:**
- Modify: `gpu_agent/dashboard/deepdive_render.py` (add link into the panel body)
- Test: `tests/dashboard/test_deepdive_render.py`

**Interfaces:**
- Produces: each opened panel ends with `Open full page for this topic →` linking to `appendix.html#dim-<key>` (the anchor `render_appendix` already emits). Implemented in the inline script using the target key.

- [ ] **Step 1: Write the failing test**

```python
# tests/dashboard/test_deepdive_render.py  (add)
def test_panel_script_builds_appendix_fulllink():
    html = render_deepdive_panel()
    assert "appendix.html#dim-" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/dashboard/test_deepdive_render.py -k fulllink -v`
Expected: FAIL.

- [ ] **Step 3: Implement** — in the inline script's `openDD`, before writing `dd-body`, append:

```javascript
    h+='<a class="dd-full" href="appendix.html#dim-'+encodeURIComponent(k)+'">Open full page for this topic \\u2192</a>';
```

Add to `DASHBOARD_CSS` (Task 7 file) if iterating: `.dd-full{display:inline-block;margin-top:1rem;font:600 .75rem system-ui;color:#2e7d32;}` — if Task 7 is already committed, add this rule here in a one-line CSS append is not possible (CSS lives in brief_render); instead add the rule in this task to `DASHBOARD_CSS` and re-commit brief_render.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/dashboard/test_deepdive_render.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add gpu_agent/dashboard/deepdive_render.py gpu_agent/dashboard/brief_render.py
git commit -m "F100: panel full-page link to appendix dimension anchor"
```

---

### Task 12: Real-store smoke build + never-raises + full suite

**Files:**
- Test: `tests/dashboard/test_build_e2e.py` (add one assertion), plus a manual smoke build.

**Interfaces:**
- Consumes: everything above.
- Produces: verified live-store render (against a **copy** of `store/`, never the live tree).

- [ ] **Step 1: Add an e2e assertion**

```python
# tests/dashboard/test_build_e2e.py  (add to the existing real-ish build test)
def test_e2e_index_has_panel_and_no_folded_headers(built_index_html):
    assert 'id="dd-drawer"' in built_index_html
    assert "<h2>Standing calls</h2>" not in built_index_html
```

(Use the module's existing built-HTML fixture; if none, build into `tmp_path` with `build_site` over `tests/dashboard/fixtures`.)

- [ ] **Step 2: Run the dashboard suite**

Run: `.venv/Scripts/python -m pytest tests/dashboard -v`
Expected: PASS (all).

- [ ] **Step 3: Smoke-build against a copy of the live store**

```bash
mkdir -p work/f100-smoke && cp -r store work/f100-smoke/store
.venv/Scripts/python -c "import datetime,gpu_agent.dashboard.site_build as sb; print(sb.build_site('chips.merchant-gpu','work/f100-smoke/store','work/f100-smoke/work',None,'work/f100-smoke/site',today=datetime.date(2026,7,20)))"
```

Expected: prints `{'pages': N, ...}` with no traceback; `brief_lint` empty. Open `work/f100-smoke/site/chips.merchant-gpu/index.html` in a browser: verify the brief is two sentences, five KPI cards, the dual-line chart renders, clicking a dimension/KPI opens the panel with why/evidence/confidence, and the "full page" link resolves to an appendix anchor. (`work/` is gitignored — do not commit it.)

- [ ] **Step 4: Full suite + gates**

Run: `.venv/Scripts/python -m pytest -q`
Expected: green (expect 3–4 skips). Confirm `tests/test_evals_baseline_pin.py` (F6) and the scoring v1 replay pin are **green** (unchanged — no brain prompts emitted). If F6 is red, STOP and follow HANDOFF's standing rule; do not edit the pin.

- [ ] **Step 5: Commit**

```bash
git add tests/dashboard/test_build_e2e.py
git commit -m "F100: e2e assertion for dashboard panel + folded-section removal"
```

---

## Self-review (done while writing)

- **Spec coverage:** brief Option-4 (Task 1/8), dynamic KPI cards no DMI/SMI (Task 8 — agenda band already excludes them), demand-vs-supply chart (Task 2/8), six dimensions list (Task 8), deep-dive panel + full-page link (Tasks 4/6/9/11), fold TSMC + calls into panels (Tasks 4/9), latest-signal kept (Task 9 keeps `_strip`), light theme no dark strip (Task 7), scope = merchant-gpu page only (all tasks touch the brief path). ✓
- **Placeholder scan:** every code/test step carries real code; the only deferral ("exact CSS values") is fully specified in Task 7. ✓
- **Type consistency:** `build_deepdive_targets` payload keys (`why/trend/trend_good/evidence/confidence/change/tsmc/calls/badges/eyebrow/title`) are produced in Task 4 and consumed verbatim by the Task 6 script and Task 9 embed. `SLOT_TO_DIMENSION` defined Task 4, used Task 8. `chart` dict keys (`labels/demand/supply`) defined Task 2, used Task 8. ✓

## Open risks / notes

- **Inline JS vs the F95 "no scripting" convention:** the deep-dive requires one self-contained inline `<script>` (no external requests) on the category page only. This is a deliberate, scoped relaxation the user approved (slide-in panel). Appendix/how pages stay script-free.
- **A live cycle may be running:** never read/write `store/`; smoke-build against a copy under gitignored `work/`.
- **Merge is the user's call** (frozen-core project). After the lane is green + whole-branch reviewed, STOP and write `.superpowers/handoffs/f100-dashboard-DONE.md`; only the user merges to main.
