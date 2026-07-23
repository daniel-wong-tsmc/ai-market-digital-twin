# F101 Phase B — Daily Narrator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A new tool-less narrator brain writes the day's story as a structured artifact; the story page renders from it (with dynamic KPI picks and related coverage), falling back to the Phase A assembler when gates fail — all behind a dedicated prompt pin and an F83 lockstep step-add.

**Architecture:** New `gpu_agent/narrator/` package (schema, inputs, prompt, gate, store, pin) mirroring the implication brain's emit/accept CLI pattern. `story_model.build_story_model` prefers a valid same-day artifact and otherwise runs the existing assembler unchanged. Run-cycle gains sub-step 3(e3) between implication and report.

**Tech Stack:** Python 3 (`.venv/Scripts/python`; worktree: `../../.venv/Scripts/python`), pydantic (repo's existing version), stdlib, pytest.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-23-f101b-daily-narrator-design.md` (as amended §7). Parent spec §4/§10.2.
- **THE GATED LANE**: no other prompt-affecting lane may be active. MUST-NOT-TOUCH: `gpu_agent/scoring.py`, `gpu_agent/report.py`, the four existing brains' prompt modules (`extraction/prompt.py`, `judgment/prompt.py`, `thesis.py` prompt builders, `implication.py` prompt builders), `gpu_agent/evals/*`, `fixtures/evals/*`, `registry/indicators.json`. The F6 pin (`tests/test_evals_baseline_pin.py`) and scoring v1 replay pin must stay GREEN and their fixtures byte-identical — verify with `git diff --stat fixtures/evals gpu_agent/evals` (must be empty) at every task commit.
- Banned words in narrator prose (prompt + gate, same list as Phase A `lint_story_copy` @story_render.py): momentum, strengthening, tightening, accelerating, DMI, SMI, allocation, doctrine, robust, leverage; `index/indexed` once max.
- User decisions (spec §2, verbatim): narrator sees yesterday's artifact + last 7 headlines; gate failure ×2 → fall back to Phase A assembler (logged `narrator: fellBack`); dedicated prompt pin, NO scored eval bar.
- Execution: worktree `.worktrees/f101b-narrator`, branch `f101b-narrator`. Suite green at every commit. Question-stop rule applies verbatim.
- A daily cycle may run concurrently on root main: never touch root `store/`; smoke tests against a COPY.

**Verified interface facts (2026-07-23):**
- Implication emit/accept pattern: `cli.py:1378` parser, `_implication` @cli.py:603 — `--emit-prompt` prints `{"system","schema","user"}`; `--recorded <answer.json>` validates → `gate_implication` @implication.py:184 (pure, no I/O; on violations prints `IMPLICATION GATE FAILED`, exit 1, writes nothing) → store write. Copy this shape exactly.
- Artifact-model precedents: `ImplicationLine/ImplicationAnswer/ImplicationArtifact` @implication.py:64-83, `ConfigDict(extra="forbid")`.
- `build_story_model(category_id, store_dir, today)` @story_model.py:231; resolves root-or-category dir itself via `resolve_store_root` @:215. Model keys: `category_id, as_of, revision, headline, deck, dateline, gap, callouts, kpis{anchored,picks}, evidence, scenes, archive, explore`.
- Day's doc pool: `work/<run-dir>/blobs.json` = `{"rounds","skipped","blobs":[{source,url,date,entity,content,...}]}` (assemble.py:54).
- F83: `EXPECTED_STEPS` @tests/test_run_cycle_conformance.py:159 (ordered `(step_id, title_head)` tuples; sub-steps parsed from `**(label) Title**` lines under `### 3.`); fingerprint = `sha256(repr(EXPECTED_STEPS))` mirrored in `.claude/skills/run-cycle/SKILL.md:52` comment; F98 precedent commit "feat(f98): run-cycle price-sync step + F83 fingerprint re-record".
- Series read: `agenda.read_series(series_dir, ids)`; implication lines: `brief_model.read_implication_lines`.

---

### Task 1: Artifact schema + story store (`narrator/schema.py`, `narrator/store.py`)

**Files:**
- Create: `gpu_agent/narrator/__init__.py` (empty), `gpu_agent/narrator/schema.py`, `gpu_agent/narrator/store.py`
- Test: `tests/narrator/test_schema.py`, `tests/narrator/test_store.py` (+ empty `tests/narrator/__init__.py` if the suite convention needs none, match `tests/dashboard/`)

**Interfaces:**
- Produces (pydantic, all `ConfigDict(extra="forbid")`):
  - `SceneVisual{kind: Literal["spark"], seriesId: str, label: str}`
  - `RelatedDoc{url: str, title: str, outlet: str, date: str}`
  - `StoryScene{n: int, title: str, paragraphs: list[str], visual: SceneVisual | None, claimFindingIds: list[str], sourceLine: str, relatedDocs: list[RelatedDoc]}`
  - `KpiPick{indicatorId: str, whyCaption: str, scene: int}`
  - `CalloutMonth{monthKey: str, text: str, scene: int}`
  - `NarratorMeta{model: str, promptHash: str, retries: int, fellBack: bool, wroteAt: str}`
  - `StoryArtifact{schemaVersion: Literal[1], categoryId: str, storyDate: str, headline: str, deck: str, scenes: list[StoryScene], kpiPicks: list[KpiPick], calloutMonths: list[CalloutMonth], narratorMeta: NarratorMeta}`
  - `NarratorAnswer` = `StoryArtifact` minus `narratorMeta`/`categoryId`/`storyDate`/`schemaVersion` (what the brain returns; the CLI wraps it). Export `NarratorAnswer.model_json_schema()` for the emit bundle.
- `StoryStore(root: Path)` with `write(artifact: StoryArtifact) -> Path` (to `<root>/<categoryId>/story/<storyDate>.json`, atomic tmp+rename, overwrite same date allowed), `read(category_id: str, story_date: str) -> StoryArtifact | None`, `recent_headlines(category_id: str, before: str, limit: int = 7) -> list[dict]` (`[{date, headline, fellBack}]`, newest first, from existing artifacts).

- [ ] **Step 1: Write the failing tests**

```python
# tests/narrator/test_schema.py
import pytest
from pydantic import ValidationError
from gpu_agent.narrator.schema import (NarratorAnswer, StoryArtifact,
                                       StoryScene, NarratorMeta)


def _scene(n=1, **kw):
    d = dict(n=n, title="What tightened", paragraphs=["Memory makers cut back."],
             visual={"kind": "spark", "seriesId": "hbmSupplyCapex",
                     "label": "Memory factory spending"},
             claimFindingIds=["f-1"], sourceLine="Source: Micron call",
             relatedDocs=[{"url": "https://x.example/a", "title": "t",
                            "outlet": "Reuters", "date": "2026-07-22"}])
    d.update(kw)
    return d


def _answer(**kw):
    d = dict(headline="The GPU shortage got worse.", deck="Why.",
             scenes=[_scene(), _scene(n=2, title="What would close the gap")],
             kpiPicks=[{"indicatorId": "hbmSupplyCapex",
                        "whyCaption": "the relief lever", "scene": 1}],
             calloutMonths=[{"monthKey": "2026-07", "text": "Jul: memory cut",
                              "scene": 1}])
    d.update(kw)
    return d


def test_answer_validates():
    a = NarratorAnswer.model_validate(_answer())
    assert a.scenes[0].visual.seriesId == "hbmSupplyCapex"


def test_extra_keys_forbidden():
    with pytest.raises(ValidationError):
        NarratorAnswer.model_validate({**_answer(), "mood": "spicy"})


def test_artifact_wraps_answer():
    art = StoryArtifact.model_validate({
        "schemaVersion": 1, "categoryId": "chips.merchant-gpu",
        "storyDate": "2026-07-23", **_answer(),
        "narratorMeta": {"model": "opus", "promptHash": "abc", "retries": 0,
                          "fellBack": False, "wroteAt": "2026-07-23T09:00:00"}})
    assert art.narratorMeta.fellBack is False


def test_answer_schema_exported():
    js = NarratorAnswer.model_json_schema()
    assert "scenes" in js["properties"] and "narratorMeta" not in js["properties"]
```

```python
# tests/narrator/test_store.py
from gpu_agent.narrator.schema import StoryArtifact
from gpu_agent.narrator.store import StoryStore
from tests.narrator.test_schema import _answer

CAT = "chips.merchant-gpu"


def _art(date, headline="H", fell_back=False):
    return StoryArtifact.model_validate({
        "schemaVersion": 1, "categoryId": CAT, "storyDate": date,
        **_answer(headline=headline),
        "narratorMeta": {"model": "opus", "promptHash": "x", "retries": 0,
                          "fellBack": fell_back, "wroteAt": f"{date}T09:00:00"}})


def test_write_read_roundtrip(tmp_path):
    st = StoryStore(tmp_path)
    p = st.write(_art("2026-07-23"))
    assert p == tmp_path / CAT / "story" / "2026-07-23.json"
    assert st.read(CAT, "2026-07-23").headline == "H"
    assert st.read(CAT, "2026-01-01") is None


def test_same_date_overwrites(tmp_path):
    st = StoryStore(tmp_path)
    st.write(_art("2026-07-23", headline="first"))
    st.write(_art("2026-07-23", headline="second"))
    assert st.read(CAT, "2026-07-23").headline == "second"


def test_recent_headlines_window(tmp_path):
    st = StoryStore(tmp_path)
    for d in ["2026-07-15", "2026-07-16", "2026-07-22", "2026-07-23"]:
        st.write(_art(d, headline=f"H {d}", fell_back=(d == "2026-07-16")))
    heads = st.recent_headlines(CAT, before="2026-07-23", limit=7)
    assert [h["date"] for h in heads] == ["2026-07-22", "2026-07-16", "2026-07-15"]
    assert heads[1]["fellBack"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `../../.venv/Scripts/python -m pytest tests/narrator/ -v`
Expected: FAIL — `ModuleNotFoundError: gpu_agent.narrator`

- [ ] **Step 3: Write the implementation**

`schema.py`: the pydantic models exactly as the Interfaces block defines (pattern: `implication.py:64-83`; `from typing import Literal, Optional`; every model `model_config = ConfigDict(extra="forbid")`). `NarratorAnswer` holds `headline, deck, scenes, kpiPicks, calloutMonths`; `StoryArtifact` extends it with `schemaVersion, categoryId, storyDate, narratorMeta` (compose via inheritance: `class StoryArtifact(NarratorAnswer)`).

`store.py`:

```python
# gpu_agent/narrator/store.py
"""Story artifacts: store/<category>/story/YYYY-MM-DD.json."""
from __future__ import annotations

import json
import os
from pathlib import Path

from gpu_agent.narrator.schema import StoryArtifact


class StoryStore:
    def __init__(self, root: Path):
        self.root = Path(root)

    def _path(self, category_id: str, story_date: str) -> Path:
        return self.root / category_id / "story" / f"{story_date}.json"

    def write(self, artifact: StoryArtifact) -> Path:
        p = self._path(artifact.categoryId, artifact.storyDate)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(artifact.model_dump_json(indent=2), encoding="utf-8")
        os.replace(tmp, p)
        return p

    def read(self, category_id: str, story_date: str) -> StoryArtifact | None:
        p = self._path(category_id, story_date)
        if not p.exists():
            return None
        try:
            return StoryArtifact.model_validate_json(
                p.read_text(encoding="utf-8"))
        except Exception:
            return None

    def recent_headlines(self, category_id: str, before: str,
                         limit: int = 7) -> list[dict]:
        d = self.root / category_id / "story"
        if not d.exists():
            return []
        out = []
        for p in sorted(d.glob("*.json"), reverse=True):
            date = p.stem
            if date >= before:
                continue
            art = self.read(category_id, date)
            if art:
                out.append({"date": date, "headline": art.headline,
                            "fellBack": art.narratorMeta.fellBack})
            if len(out) == limit:
                break
        return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `../../.venv/Scripts/python -m pytest tests/narrator/ -v` → 7 PASS

- [ ] **Step 5: Commit**

```bash
git add gpu_agent/narrator tests/narrator
git commit -m "feat(f101b): story artifact schema + story store"
```

---

### Task 2: Narrator inputs + prompt (`narrator/inputs.py`, `narrator/prompt.py`)

**Files:**
- Create: `gpu_agent/narrator/inputs.py`, `gpu_agent/narrator/prompt.py`
- Test: `tests/narrator/test_inputs.py`, `tests/narrator/test_prompt.py`

**Interfaces:**
- Consumes: `brief_model.latest_monthly`, `read_implication_lines`; `agenda.read_series`; `StoryStore.read/recent_headlines`; `work/<run-dir>/blobs.json`.
- Produces:
  - `build_narrator_inputs(category_id: str, store_dir: str | Path, today: datetime.date, run_dir: str | Path | None) -> dict` with keys `{"scorecard": {asOf, revision, categoryStatus, dimensionRatings}, "findings": [{id, statement, evidence:[{source,url,date,tier}]}], "implicationLines": [{text, findingIds}], "seriesPool": [{indicatorId, label, latestValue, unit, tail:[floats]}], "memory": {"yesterday": <artifact dict|None>, "recentHeadlines": [...]}, "docPool": [{url, source, date}], "gapMonths": [monthKey...], "storyDate": "YYYY-MM-DD"}`. `docPool` from `<run_dir>/blobs.json` (https urls only); empty list when `run_dir` is None/missing (gate 3 then rejects any relatedDocs — correct: no doc pool, no related coverage). `seriesPool` labels from the Phase A `_CHIP_DEFS` table (import it from `story_model`).
  - `build_narrator_system() -> str` — persona + the editorial rules verbatim (spec §4): answers only "why isn't supply catching up — and what would change that"; a scene that doesn't change understanding doesn't run; 2–5 scenes; last scene forward-looking; plain newspaper English + the banned-word list spelled out; every claim cites finding ids FROM THE PROVIDED LIST; relatedDocs only from the provided doc pool; carried-forward claims still cite today's findings; quiet days may run 2 scenes; NO tool use; answer = JSON matching the provided schema only.
  - `build_narrator_user_prompt(inputs: dict) -> str` — sections: TODAY'S DATA (scorecard/findings/implications/series pool), YOUR PREVIOUS ENTRIES (yesterday's artifact + recent headlines, or "none yet"), TODAY'S GATHERED DOCUMENTS, REQUIRED OUTPUT (the `NarratorAnswer` JSON schema inline).
  - `emit_narrator_bundle(inputs: dict) -> dict` — `{"system": build_narrator_system(), "schema": NarratorAnswer.model_json_schema(), "user": build_narrator_user_prompt(inputs)}` (same bundle shape as `evals/emit.py` seams — but lives in `narrator/`, NOT in `gpu_agent/evals/`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/narrator/test_inputs.py
import datetime as dt
import json
from gpu_agent.narrator.inputs import build_narrator_inputs
from gpu_agent.narrator.store import StoryStore
from tests.narrator.test_store import _art, CAT
from tests.dashboard.test_story_model import _store   # Phase A fixture builder


def test_inputs_assembled(tmp_path):
    store = _store(tmp_path)
    run = tmp_path / "run"
    run.mkdir()
    (run / "blobs.json").write_text(json.dumps({"rounds": 1, "skipped": [],
        "blobs": [{"source": "Reuters", "url": "https://r.example/hbm",
                    "date": "2026-07-23", "entity": "market", "content": "x"},
                   {"source": "sketch", "url": "http://insecure.example/x",
                    "date": "2026-07-23", "entity": "m", "content": "y"}]}),
        encoding="utf-8")
    StoryStore(store).write(_art("2026-07-22", headline="Yesterday's H"))
    inp = build_narrator_inputs(CAT, store, dt.date(2026, 7, 23), run)
    assert inp["storyDate"] == "2026-07-23"
    assert inp["scorecard"]["asOf"] == "2026-07"
    assert any(f["id"] == "f-1" for f in inp["findings"])
    assert any(s["indicatorId"] == "gpuRentalOnDemand" for s in inp["seriesPool"])
    assert inp["memory"]["yesterday"]["headline"] == "Yesterday's H"
    assert [d["url"] for d in inp["docPool"]] == ["https://r.example/hbm"]  # https only
    assert "2026-07" in inp["gapMonths"]


def test_inputs_no_run_dir_no_memory(tmp_path):
    inp = build_narrator_inputs(CAT, _store(tmp_path), dt.date(2026, 7, 23), None)
    assert inp["docPool"] == [] and inp["memory"]["yesterday"] is None
```

```python
# tests/narrator/test_prompt.py
import datetime as dt
from gpu_agent.narrator.inputs import build_narrator_inputs
from gpu_agent.narrator.prompt import (build_narrator_system,
                                       build_narrator_user_prompt,
                                       emit_narrator_bundle)
from tests.narrator.test_inputs import CAT
from tests.dashboard.test_story_model import _store


def test_system_carries_editorial_rules():
    s = build_narrator_system()
    for phrase in ["why isn", "catching up", "2", "5", "forward-looking",
                   "momentum", "no tool"]:
        assert phrase.lower() in s.lower()
    assert "doesn" in s and "run" in s      # the doesn't-run rule


def test_user_prompt_sections(tmp_path):
    inp = build_narrator_inputs(CAT, _store(tmp_path), dt.date(2026, 7, 23), None)
    u = build_narrator_user_prompt(inp)
    assert "TODAY'S DATA" in u and "PREVIOUS ENTRIES" in u
    assert "none yet" in u.lower()          # no memory case
    assert "f-1" in u                        # findings listed with ids


def test_bundle_shape(tmp_path):
    inp = build_narrator_inputs(CAT, _store(tmp_path), dt.date(2026, 7, 23), None)
    b = emit_narrator_bundle(inp)
    assert set(b) == {"system", "schema", "user"}
    assert "scenes" in b["schema"]["properties"]
```

- [ ] **Step 2: Run to verify failure** — `../../.venv/Scripts/python -m pytest tests/narrator/test_inputs.py tests/narrator/test_prompt.py -v` → module-not-found FAILs.

- [ ] **Step 3: Implement.** `inputs.py`: read latest monthly scorecard via `latest_monthly` (keep only `asOf/revision/categoryStatus/dimensionRatings` + embedded findings trimmed to `{id, statement, evidence[{source,url,date,tier}]}`); implication lines via `read_implication_lines` → `{text, findingIds}`; series pool from `agenda.read_series` over `story_model._SERIES_IDS` with labels from `story_model._CHIP_DEFS` (`{indicatorId, label, latestValue, unit, tail}`); memory via `StoryStore(store_root)` (`yesterday` = `read(cat, (today - 1 day).isoformat())` as `model_dump()` or None; `recent_headlines(cat, before=today.isoformat())`); docPool from `run_dir/blobs.json` blobs → `{url, source, date}` filtered to `url.startswith("https://")`; `gapMonths` from `gap_chart.build_gap_data` month keys (empty list if None). `prompt.py`: module constants `NARRATOR_SYSTEM` (persona: "You write a short daily market story for a non-technical executive..." + the rules; include the banned list verbatim: momentum, strengthening, tightening, accelerating, DMI, SMI, allocation, doctrine, robust, leverage) and the user-prompt builder rendering the four sections with `json.dumps` payloads; `emit_narrator_bundle` as specced. No imports from `gpu_agent/evals/`.

- [ ] **Step 4: Run** `../../.venv/Scripts/python -m pytest tests/narrator/ -v` → all PASS.

- [ ] **Step 5: Commit** — `git add gpu_agent/narrator tests/narrator && git commit -m "feat(f101b): narrator inputs + prompt builders"`

---

### Task 3: The gate (`narrator/gate.py`)

**Files:**
- Create: `gpu_agent/narrator/gate.py`
- Test: `tests/narrator/test_gate.py`

**Interfaces:**
- Consumes: `NarratorAnswer`; `story_render.lint_story_copy` (reused on prose); the inputs dict (Task 2) for membership checks.
- Produces: `gate_narrator(answer: NarratorAnswer, inputs: dict) -> list[str]` — pure, no I/O, empty list = pass. Checks (spec §5):
  1. (schema is upstream — pydantic validation happens at parse; the gate assumes a valid `NarratorAnswer`)
  2. every `claimFindingIds` id ∈ `{f["id"] for f in inputs["findings"]}`; a scene with empty `claimFindingIds` must have `sourceLine == "No new sourced evidence today."` (exact string; the renderer shows it as-is — Phase A review-finding-#1 precedent)
  3. every `relatedDocs.url` ∈ `{d["url"] for d in inputs["docPool"]}` (docPool is already https-only)
  4. `lint_story_copy` over all prose joined (`headline`, `deck`, scene titles+paragraphs+sourceLines, whyCaptions, callout texts) wrapped as `<p>...</p>` — reuse, don't reimplement
  5. `2 <= len(scenes) <= 5`; scene `n` values are 1..N contiguous; last scene title contains a forward-looking marker (accept: "close", "watch", "ahead", "next") — plus every scene `sourceLine` non-empty
  6. every `kpiPicks.indicatorId` ∈ `{s["indicatorId"] for s in inputs["seriesPool"]}` and its `scene` exists; every `calloutMonths.monthKey` ∈ `inputs["gapMonths"]`; `kpiPicks` scene values unique

- [ ] **Step 1: Failing tests**

```python
# tests/narrator/test_gate.py
import datetime as dt
from gpu_agent.narrator.gate import gate_narrator
from gpu_agent.narrator.schema import NarratorAnswer
from gpu_agent.narrator.inputs import build_narrator_inputs
from tests.narrator.test_schema import _answer, _scene
from tests.narrator.test_inputs import CAT
from tests.dashboard.test_story_model import _store


def _inp(tmp_path):
    return build_narrator_inputs(CAT, _store(tmp_path), dt.date(2026, 7, 23), None)


def _ok(tmp_path):
    # an answer aligned with the fixture store: finding f-1, series pool ids, month keys
    return NarratorAnswer.model_validate(_answer(
        scenes=[_scene(claimFindingIds=["f-1"], relatedDocs=[]),
                _scene(n=2, title="What would close the gap",
                       claimFindingIds=["f-2"], relatedDocs=[])],
        kpiPicks=[{"indicatorId": "hbmSupplyCapex", "whyCaption": "relief lever",
                    "scene": 1}],
        calloutMonths=[{"monthKey": "2026-07", "text": "Jul: memory cut",
                         "scene": 1}]))


def test_clean_answer_passes(tmp_path):
    assert gate_narrator(_ok(tmp_path), _inp(tmp_path)) == []


def test_unknown_finding_id_rejected(tmp_path):
    a = _ok(tmp_path)
    a.scenes[0].claimFindingIds = ["f-ghost"]
    assert any("f-ghost" in v for v in gate_narrator(a, _inp(tmp_path)))


def test_sourceless_scene_needs_exact_wording(tmp_path):
    a = _ok(tmp_path)
    a.scenes[0].claimFindingIds = []
    a.scenes[0].sourceLine = "Source: trust me"
    assert gate_narrator(a, _inp(tmp_path))
    a.scenes[0].sourceLine = "No new sourced evidence today."
    assert gate_narrator(a, _inp(tmp_path)) == []


def test_related_doc_outside_pool_rejected(tmp_path):
    a = _ok(tmp_path)
    a.scenes[0].relatedDocs = [{"url": "https://elsewhere.example/x",
                                 "title": "t", "outlet": "o", "date": "d"}]
    assert any("elsewhere" in v for v in gate_narrator(a, _inp(tmp_path)))


def test_banned_word_rejected(tmp_path):
    a = _ok(tmp_path)
    a.deck = "Demand momentum is strengthening."
    assert len(gate_narrator(a, _inp(tmp_path))) >= 1


def test_scene_bounds_and_forward_close(tmp_path):
    a = _ok(tmp_path)
    a.scenes = a.scenes[:1]                       # only 1 scene
    assert gate_narrator(a, _inp(tmp_path))
    b = _ok(tmp_path)
    b.scenes[-1].title = "Another grim chapter"   # not forward-looking
    assert gate_narrator(b, _inp(tmp_path))


def test_kpi_and_callout_membership(tmp_path):
    a = _ok(tmp_path)
    a.kpiPicks[0].indicatorId = "notASeries"
    assert gate_narrator(a, _inp(tmp_path))
    b = _ok(tmp_path)
    b.calloutMonths[0].monthKey = "1999-01"
    assert gate_narrator(b, _inp(tmp_path))
```

- [ ] **Step 2: Run to verify failure** — module-not-found.
- [ ] **Step 3: Implement** `gate_narrator` per the six checks; each violation a plain sentence naming the offending value. Reuse `lint_story_copy` by wrapping prose: `lint_story_copy("<p>" + " ".join(prose_bits) + "</p>")`.
- [ ] **Step 4: Run** `tests/narrator/ -v` → all PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat(f101b): narrator gate - six deterministic checks"`

---

### Task 4: CLI verb `narrator` (emit / accept / fallback)

**Files:**
- Modify: `gpu_agent/cli.py` (parser + handler + dispatch — mirror the implication trio @cli.py:1378/:603/:1542)
- Test: `tests/narrator/test_cli.py`

**Interfaces:**
- Produces three invocations (all take `--store <root>`, `--category <id>`, `--date YYYY-MM-DD`; emit/accept also `--run-dir <dir>` optional):
  - `narrator --emit-prompt` → prints `json.dumps(emit_narrator_bundle(build_narrator_inputs(...)))`; exit 0.
  - `narrator --recorded <answer.json>` → parse `NarratorAnswer` (pydantic errors → print `NARRATOR GATE FAILED\n<error>`, exit 1, write nothing) → `gate_narrator` (violations → same failure print, exit 1, write nothing) → wrap into `StoryArtifact` (`narratorMeta`: `model` from `--model` arg default "opus", `promptHash` = sha256 of the canonicalized emit bundle recomputed from the same inputs, `retries` from `--retries` int default 0, `fellBack=False`, `wroteAt` = ISO now) → `StoryStore(store).write` → print `wrote <path>`; exit 0.
  - `narrator --record-fallback --reasons <reasons.json>` → writes the `fellBack: True` artifact (empty scenes, headline/deck EMPTY strings — renderer never shows them; reasons stored in a sibling `<date>.fallback.json` for the log) → print `wrote fallback <path>`.
- Orchestration contract (run-cycle Task 6 depends on it): emit → dispatch tool-less Opus subagent → save answer → accept; on gate-fail re-dispatch ONCE with violations appended; second fail → `--record-fallback`.

- [ ] **Step 1: Failing tests** (pattern: invoke handlers via `cli.main([...])` the way existing CLI tests do — read one existing CLI test first, e.g. the implication one, and match its invocation style exactly; assert exit codes via `SystemExit` or return, artifact presence/absence, and the `NARRATOR GATE FAILED` marker on stdout via capsys)

```python
# tests/narrator/test_cli.py — representative cases (match repo CLI-test style)
def test_emit_prints_bundle(tmp_path, capsys): ...      # json with system/schema/user
def test_recorded_clean_writes_artifact(tmp_path): ...  # exit 0, file exists, meta filled
def test_recorded_gate_fail_writes_nothing(tmp_path, capsys): ...  # exit 1, marker, no file
def test_record_fallback_writes_fellback(tmp_path): ... # fellBack True, empty scenes
```

Write the four bodies concretely against the fixture store (`tests/dashboard/test_story_model._store` + a hand-written good/bad answer json in `tmp_path`); the good answer = Task 3's `_ok` shape dumped.

- [ ] **Step 2: Run to verify failure.**
- [ ] **Step 3: Implement** the parser/handler/dispatch mirroring `_implication` exactly (including the exit-2 category/scorecard mismatch guard where applicable). Handler lives in `cli.py` like the others; heavy lifting stays in `narrator/` modules.
- [ ] **Step 4: Run** `tests/narrator/ -v` → all PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat(f101b): narrator CLI verb - emit/accept/fallback"`

---

### Task 5: Renderer switch — artifact-first `build_story_model`

**Files:**
- Modify: `gpu_agent/dashboard/story_model.py`
- Test: `tests/dashboard/test_story_model.py` (append), `tests/narrator/test_contract.py`

**Interfaces:**
- Produces: `read_story_artifact(category_id: str, store_root: Path, today: dt.date) -> dict | None` — loads today's artifact via `StoryStore`; returns None if absent or `fellBack`. Maps artifact → the EXACT model dict shape (`category_id, as_of, revision, headline, deck, dateline, gap, callouts, kpis, evidence, scenes, archive, explore`): gap/archive/explore/anchored-chip/evidence-series still computed from store data (same helpers as the assembler — factor the shared tail of `build_story_model` into `_base_model(...)` used by both paths); narrated fields override: headline, deck, scenes (paragraphs/title/sourceLine/related from the artifact; visual series resolved from `seriesId` via the series read; `evidence["scene:N"]` findings resolved from `claimFindingIds` against the scorecard findings — empty claims render the no-source wording), `kpis.picks` = artifact `kpiPicks` mapped through the Phase A `_CHIP_DEFS` chip builder with `caption = whyCaption`, callouts from `calloutMonths`.
- `build_story_model(category_id, store_dir, today)` — signature UNCHANGED; body becomes: resolve root → `read_story_artifact(...)` → if not None return it, else run the existing assembler unchanged.
- Contract invariant (the spec §8 test): both paths return dicts with identical key sets, and `render_story_page` + `lint_story_copy` accept both.

- [ ] **Step 1: Failing tests**

```python
# tests/narrator/test_contract.py
import datetime as dt
from gpu_agent.dashboard.story_model import build_story_model
from gpu_agent.dashboard.story_render import render_story_page, lint_story_copy
from gpu_agent.narrator.store import StoryStore
from gpu_agent.narrator.schema import StoryArtifact
from tests.narrator.test_schema import _answer, _scene
from tests.dashboard.test_story_model import _store, CAT

TODAY = dt.date(2026, 7, 23)


def _narrated(tmp_path, **meta):
    st = _store(tmp_path)
    m = {"model": "opus", "promptHash": "x", "retries": 0,
         "fellBack": False, "wroteAt": "2026-07-23T09:00:00"}
    m.update(meta)
    StoryStore(st).write(StoryArtifact.model_validate({
        "schemaVersion": 1, "categoryId": CAT, "storyDate": "2026-07-23",
        **_answer(headline="A narrated headline.",
                  scenes=[_scene(claimFindingIds=["f-1"], relatedDocs=[]),
                          _scene(n=2, title="What would close the gap",
                                 claimFindingIds=[], relatedDocs=[],
                                 sourceLine="No new sourced evidence today.")]),
        "narratorMeta": m}))
    return st


def test_artifact_drives_the_page(tmp_path):
    st = _narrated(tmp_path)
    model = build_story_model(CAT, st, TODAY)
    assert model["headline"] == "A narrated headline."
    assert model["kpis"]["picks"][0]["caption"] == "the relief lever"
    html = render_story_page(model)
    assert "A narrated headline." in html
    assert lint_story_copy(html) == []


def test_fellback_artifact_falls_back_to_assembler(tmp_path):
    st = _narrated(tmp_path, fellBack=True)
    model = build_story_model(CAT, st, TODAY)
    assert model["headline"] != "A narrated headline."   # assembler ran


def test_no_artifact_same_as_phase_a(tmp_path):
    st = _store(tmp_path)
    model = build_story_model(CAT, st, TODAY)
    assert model["headline"] == "The GPU shortage got worse this month."


def test_both_paths_same_shape(tmp_path):
    st = _narrated(tmp_path)
    narrated = build_story_model(CAT, st, TODAY)
    assembled = build_story_model(CAT, _store(tmp_path / "b"), TODAY)
    assert set(narrated) == set(assembled)
    assert set(narrated["kpis"]) == set(assembled["kpis"])
```

- [ ] **Step 2: Run to verify failure.**
- [ ] **Step 3: Implement** per the Interfaces block (factor `_base_model`, add the mapper; no `story_render` changes). The evidence entries for narrated scenes resolve `claimFindingIds` with the existing `_resolve_findings`/`_finding_rows` helpers.
- [ ] **Step 4: Run** `tests/narrator/ tests/dashboard/ -v` → all PASS (Phase A tests must stay green untouched except any that assert the assembler runs when an artifact exists — none should; if one does, question-stop).
- [ ] **Step 5: Commit** — `git commit -m "feat(f101b): story page renders from the narrator artifact, assembler as fallback"`

---

### Task 6: Narrator prompt pin (dedicated tripwire; F6 baseline untouched)

**Files:**
- Create: `fixtures/narrator/hash-input.json`, `fixtures/narrator/prompt-pin.json`, `gpu_agent/narrator/pin.py`, `tests/narrator/test_prompt_pin.py`
- Create: `scripts/narrator-pin-record.py` (tiny re-record helper)

**Interfaces:**
- `pin.py`: `compute_narrator_prompt_hash(hash_input: dict) -> str` — builds inputs from the CHECKED-IN fixture `fixtures/narrator/hash-input.json` (a frozen minimal inputs dict — NOT live store data), runs `emit_narrator_bundle`, canonicalizes `json.dumps(bundle, sort_keys=True, ensure_ascii=False)`, SHA-256 (same recipe as `evals/prompt_hash.py:12`, reimplemented locally — no import from `gpu_agent/evals/`).
- `prompt-pin.json`: `{"schemaVersion": 1, "promptHash": "<hex>", "recordedAt": "...", "note": "re-record ONLY deliberately: .venv/Scripts/python scripts/narrator-pin-record.py"}`.
- Test: recompute == pinned; plus `test_pin_is_deliberate` asserting the fixture file exists and the hash is 64 hex chars. Semantics identical to F6: any narrator prompt edit → RED → deliberate re-record commit.

- [ ] **Step 1: Failing test** (hash mismatch against a placeholder pin, then record):

```python
# tests/narrator/test_prompt_pin.py
import json, re
from pathlib import Path
from gpu_agent.narrator.pin import compute_narrator_prompt_hash

PIN = Path("fixtures/narrator/prompt-pin.json")
HASH_INPUT = Path("fixtures/narrator/hash-input.json")


def test_narrator_prompt_hash_matches_pin():
    pin = json.loads(PIN.read_text(encoding="utf-8"))
    got = compute_narrator_prompt_hash(
        json.loads(HASH_INPUT.read_text(encoding="utf-8")))
    assert got == pin["promptHash"], (
        "Narrator prompt changed. If DELIBERATE, re-record via "
        "scripts/narrator-pin-record.py and commit the new pin with the "
        "prompt change in the SAME commit.")


def test_pin_is_deliberate():
    pin = json.loads(PIN.read_text(encoding="utf-8"))
    assert re.fullmatch(r"[0-9a-f]{64}", pin["promptHash"])
    assert pin["schemaVersion"] == 1
```

- [ ] **Step 2:** write `hash-input.json` (a frozen minimal-but-complete inputs dict: 2 findings, 1 implication line, 2 series-pool entries, memory None/empty, 1 docPool entry, 2 gapMonths, storyDate "2026-07-23"); implement `pin.py` + `scripts/narrator-pin-record.py` (compute + rewrite `prompt-pin.json`); run the recorder ONCE to mint the pin. Run tests → PASS.
- [ ] **Step 3: Prove the F6 baseline untouched**: `git diff --stat fixtures/evals gpu_agent/evals tests/test_evals_baseline_pin.py` → EMPTY. Run `../../.venv/Scripts/python -m pytest tests/test_evals_baseline_pin.py -v` → green.
- [ ] **Step 4: Commit** — `git add fixtures/narrator gpu_agent/narrator/pin.py scripts/narrator-pin-record.py tests/narrator/test_prompt_pin.py && git commit -m "feat(f101b): dedicated narrator prompt pin (F6 baseline untouched)"`

---

### Task 7: Run-cycle step 3(e3) + F83 lockstep re-record

**Files:**
- Modify: `.claude/skills/run-cycle/SKILL.md` (new sub-step `**(e3) narrator**` between `(e2) implication` and `(f) render the executive report`, + fingerprint comment @:52)
- Modify: `tests/test_run_cycle_conformance.py` (`EXPECTED_STEPS` @:159 — insert `("3e3", "narrator")` matching the parser's id scheme; verify the exact id format by reading `_parse_procedure_steps` @:139 FIRST and matching how `3e2` is keyed)
- Test: `tests/test_run_cycle_conformance.py` (existing tests enforce the lockstep)

SKILL.md sub-step text (concise, mirroring (e2)'s structure): emit via `narrator --emit-prompt --store store --category <id> --date <today> --run-dir <run-dir>` → dispatch ONE tool-less Opus subagent (no-tool prompt; `model: opus`) → save `<work>/narrator-answer.json` → accept via `narrator --recorded ...`. On `NARRATOR GATE FAILED`: re-dispatch ONCE with the violation text appended; on second failure run `narrator --record-fallback --reasons <file>` and record `narrator: fellBack` in the cycle log. **This step never blocks the cycle** (price-sync precedent); the site build then renders artifact-first automatically. Cycle-log: fold `narrator: done|fellBack|skipped` into stageStatuses (step 6 wording updated in the same edit).

- [ ] **Step 1:** read `_parse_procedure_steps` + the current `(e2)` block; draft the `(e3)` block; run `../../.venv/Scripts/python -m pytest tests/test_run_cycle_conformance.py -v` → the two lockstep tests FAIL (drift detected — the tripwire working).
- [ ] **Step 2:** update `EXPECTED_STEPS` + regenerate the SKILL.md fingerprint comment (`python - <<'EOF'` computing `sha256(repr(EXPECTED_STEPS))` — or the repo's documented helper if one exists; check the F98 commit for the exact mechanism first).
- [ ] **Step 3: Run** the conformance file → ALL PASS. Full suite spot: `tests/ -q -x --ignore=tests/dashboard` quick pass.
- [ ] **Step 4: Commit** — `git commit -m "feat(f101b): run-cycle narrator step 3(e3) + F83 fingerprint re-record"` (one commit, lockstep — F98 precedent).

---

### Task 8: Close-out — stub-brain dry run, smoke on store copy, full suite, sentinel

**Files:**
- Create: `.superpowers/handoffs/f101b-narrator-DONE.md` (end)
- Test: `tests/narrator/test_e2e_stub.py`

- [ ] **Step 1: Stub-brain end-to-end test** — using the fixture store: `narrator --emit-prompt` (capture bundle) → write a VALID answer json by hand (the Task 3 `_ok` shape) → `narrator --recorded` → `build_site(...)` into `tmp_path` → assert index.html contains the narrated headline + `lint_story_copy` clean + the dynamic pick caption renders. Second case: two invalid answers → `--record-fallback` → `build_site` → assembler headline renders. Commit.
- [ ] **Step 2: Real-store smoke (COPY only):** `mkdir -p ../../work/f101b-smoke && cp -r ../../store ../../work/f101b-smoke/store`; run `narrator --emit-prompt` against the copy (assert bundle prints, includes real finding ids); do NOT dispatch a live brain in-lane — the live narrated cycle is the post-merge criterion (spec §8). Build the site from the copy WITHOUT an artifact → assembler page renders (Phase A behavior intact on real data).
- [ ] **Step 3: Full suite** `../../.venv/Scripts/python -m pytest -q` → green (expect ~1830+/6-7 skips). Verify: `git diff --stat fixtures/evals gpu_agent/evals registry/` EMPTY across the whole branch; F6 pin + scoring replay pin + F83 conformance + narrator pin all green.
- [ ] **Step 4: Sentinel** `.superpowers/handoffs/f101b-narrator-DONE.md`: lane summary, commits, smoke observations, the spec §7 amendment note (dedicated pin), live-cycle criterion reminder, "STOP before merge — only the user merges".
- [ ] **Step 5: Final commit** — explicit paths only (a daily cycle may have dirtied root `store/`).

---

## Self-Review

1. **Spec coverage:** §3 artifact → T1; §4 step+prompt+memory → T2 (inputs/memory/docPool), T4 (CLI), T7 (orchestration); §5 gates 1-6 → T3 (+schema at parse, T4); §6 fallback → T4 (`--record-fallback`), T5 (fellBack → assembler), T7 (orchestrator wording), T8 (e2e case); §7 pin → T6 (as amended), F83 → T7, replay-pin/MUST-NOT-TOUCH → global constraint + T6/T8 verification steps; §8 tests → T1-T6 units, T8 stub e2e + contract T5; live criterion explicitly post-merge (T8 step 2 note). §9 out-of-scope respected (no archive pages, no F96/F102 work, no deploy).
2. **Placeholders:** T4 step 1 lists four test names with `...` bodies BUT instructs writing them concretely against named fixtures with specified assertions — acceptable? No: tightened to name the exact fixtures, exit codes, and stdout marker per case (done above). No TBDs remain.
3. **Type consistency:** `NarratorAnswer`/`StoryArtifact` names consistent T1→T3→T4→T5→T6; `gate_narrator(answer, inputs)` T3→T4; `build_narrator_inputs(category_id, store_dir, today, run_dir)` T2→T4→T6; `read_story_artifact(category_id, store_root, today)` T5 only; `StoryStore(root).write/read/recent_headlines` T1→T2→T4→T5; the exact no-source string `"No new sourced evidence today."` appears identically in T3 gate and T5 mapper.
