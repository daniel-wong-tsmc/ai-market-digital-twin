# F103 — Evidence Freshness Decay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Half-life freshness decay (news 3d / filings 5d / structural 45d, user-set) applied to page evidence rows, the Explore findings page, narrator inputs + prose-dating rules, and gather cadence for official IR domains — judge untouched.

**Architecture:** New `gpu_agent/freshness.py` engine + validated `registry/freshness.json`. Renderer layers consume `weight` per evidence row (sort, always-date, dim, publisher cap). The narrator gains a deterministic aged-claim gate check (prompt-neutral) early, and the prompt/input changes land in ONE final task with a single narrator-pin re-record. Gather cadence = new manifest model fields + a pure helper + gather-skill wording.

**Tech Stack:** Python 3 (`.venv/Scripts/python`; worktree `../../.venv/Scripts/python`), pydantic, stdlib, pytest.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-24-f103-freshness-decay-design.md`. Judge briefing/prompt + all scored-eval seams byte-untouched; `git diff --stat fixtures/evals gpu_agent/evals gpu_agent/judgment registry/indicators.json` EMPTY at every commit. F6 / scoring replay / F83 pins green throughout; the narrator pin goes red ONLY in Task 7 and is re-recorded in that same commit.
- Half-life values, domain patterns, structural indicator ids live ONLY in `registry/freshness.json`.
- Decay anchors on published date (evidence `date` / finding `observedAt`/`asOf` / blob `date` / series `publishedAt`); NEVER `capturedAt`. Missing/unparseable date → age 30 days (`_DEFAULT_AGE_DAYS = 30`).
- Weight threshold for the dim/"aging" treatment: `0.25` (module constant `AGING_THRESHOLD` in `freshness.py`, imported everywhere — never re-declared).
- Worktree `.worktrees/f103-freshness`, branch `f103-freshness`. Suite green at every commit; question-stop rule verbatim; never touch root `store/`; smoke on a COPY. Wall-clock isolation: `today` threaded.

**Verified current-main facts (2026-07-24):** evidence-row builders `_series_evidence` @story_model.py:274 / `_finding_rows` @:524 / `_related` @:540 (all URL-dedup, cap 3/3/2, emit `date`, NO date sort); narrated related rows @:452; KPI evidence @:342-348; scene evidence assembler @:622 + narrated @:456. Panel row renders `source · date` client-side @story_render.py:38-42 from the `ev-data` blob. Explore findings card `_find_card` @explore_render.py:172 (`data-date` = `observedAt or asOf`), groups don't re-sort (docstring @:199). Narrator: `build_narrator_inputs` @inputs.py:37 (findings via `_finding_trim` @:25, docPool @:81); rules = hyphen bullets in `NARRATOR_SYSTEM` @prompt.py:21-38; `gate_narrator(answer, inputs)` @gate.py:33 (append-a-block pattern); pin re-record = `scripts/narrator-pin-record.py` writing `fixtures/narrator/prompt-pin.json`. Manifest: `load_manifest` @manifest.py:99 (pydantic; UNKNOWN KEYS DROPPED — `primaryDomains` not exposed), `ExpectedSource` @:32 has `refresh` (read by nothing) and NO cadence field; nvda-earnings @manifests/chips.merchant-gpu.json:116, amd-earnings @:127. Gather is planned by `.claude/skills/gather-category/SKILL.md` (daily caps @:370-372; NOT fingerprint-pinned — verify in Task 6). No dim CSS exists yet (only `.stalestrip` @brief_render.py:32). Date helpers: `agenda._days_old` @agenda.py:210.

---

### Task 1: The engine (`gpu_agent/freshness.py` + `registry/freshness.json`)

**Files:**
- Create: `gpu_agent/freshness.py`, `registry/freshness.json`
- Test: `tests/test_freshness.py`

**Interfaces:**
- `registry/freshness.json`:

```json
{
  "schemaVersion": 1,
  "halfLivesDays": {"news": 3, "filings": 5, "structural": 45},
  "filingsDomains": ["investor.", "ir.", "sec.gov", "nvidianews.nvidia.com",
                      "blogs.nvidia.com", "intc.com", "q4cdn.com",
                      "federalregister.gov", "bis.doc.gov", "mopsov.twse.com.tw"],
  "structuralIndicators": ["leadTimes", "upstreamLeadTimes",
                            "pkgCapacityOrderSpread", "hbmSupplyCapex"]
}
```

- `freshness.py`:
  - `AGING_THRESHOLD = 0.25`, `_DEFAULT_AGE_DAYS = 30`
  - `FreshnessConfig` (pydantic, `extra="forbid"`): the three keys above + `schemaVersion: Literal[1]`; loader `load_freshness(path="registry/freshness.json") -> FreshnessConfig` — validated, raises `FreshnessLoadError` on missing/invalid (copy the `manifest.py:99` trust-boundary pattern, NOT the unvalidated `load_benchmarks`).
  - `classify(url: str, indicator_id: str | None, cfg: FreshnessConfig) -> str` — precedence: filingsDomain substring match on the URL's netloc+path → `"filings"`; else indicator_id ∈ structuralIndicators → `"structural"`; else `"news"`.
  - `parse_date(raw: str | None) -> datetime.date | None` — accepts `YYYY-MM-DD`, `YYYY-MM` (→ day 1); else None.
  - `weight(published: str | None, today: datetime.date, kind: str, cfg: FreshnessConfig) -> float` — `0.5 ** (age_days / halfLivesDays[kind])`, age via `parse_date` (None → `_DEFAULT_AGE_DAYS`; future dates clamp to age 0), result rounded to 4 places, clamped [0,1].

- [ ] **Step 1: Failing tests**

```python
# tests/test_freshness.py
import datetime as dt
import json
import pytest
from gpu_agent.freshness import (AGING_THRESHOLD, FreshnessLoadError,
                                 classify, load_freshness, parse_date, weight)

TODAY = dt.date(2026, 7, 24)
CFG = load_freshness()


def test_registry_loads_user_values():
    assert CFG.halfLivesDays == {"news": 3, "filings": 5, "structural": 45}


def test_weight_half_life_points():
    assert weight("2026-07-24", TODAY, "news", CFG) == 1.0
    assert weight("2026-07-21", TODAY, "news", CFG) == pytest.approx(0.5)
    assert weight("2026-07-18", TODAY, "news", CFG) == pytest.approx(0.25)
    assert weight("2026-07-19", TODAY, "filings", CFG) == pytest.approx(0.5)
    assert weight("2026-06-09", TODAY, "structural", CFG) == pytest.approx(0.5)


def test_may_earnings_is_negligible_now():
    # the complaint that started F103: late-May filings in late July
    assert weight("2026-05-28", TODAY, "filings", CFG) < 0.001


def test_missing_date_treated_as_30_days_old():
    got = weight(None, TODAY, "news", CFG)
    assert got == pytest.approx(0.5 ** (30 / 3), rel=1e-3)
    assert weight("garbage", TODAY, "news", CFG) == got


def test_future_date_clamps_to_full_weight():
    assert weight("2026-08-01", TODAY, "news", CFG) == 1.0


def test_parse_date_forms():
    assert parse_date("2026-07-24") == dt.date(2026, 7, 24)
    assert parse_date("2026-07") == dt.date(2026, 7, 1)
    assert parse_date("") is None and parse_date(None) is None


def test_classify_precedence():
    assert classify("https://investor.nvidia.com/x", None, CFG) == "filings"
    assert classify("https://nvidianews.nvidia.com/y", "leadTimes", CFG) == "filings"
    assert classify("https://reuters.com/z", "upstreamLeadTimes", CFG) == "structural"
    assert classify("https://reuters.com/z", None, CFG) == "news"


def test_loader_is_a_trust_boundary(tmp_path):
    bad = tmp_path / "f.json"
    bad.write_text(json.dumps({"schemaVersion": 1,
                                "halfLivesDays": {"news": 3},
                                "filingsDomains": [], "structuralIndicators": [],
                                "surprise": True}), encoding="utf-8")
    with pytest.raises(FreshnessLoadError):
        load_freshness(bad)
    with pytest.raises(FreshnessLoadError):
        load_freshness(tmp_path / "missing.json")
```

- [ ] **Step 2:** run `../../.venv/Scripts/python -m pytest tests/test_freshness.py -v` → module-not-found FAIL.
- [ ] **Step 3:** implement both files per the Interfaces block (halfLivesDays must require exactly the three kind keys — validator).
- [ ] **Step 4:** run → 9 PASS. **Step 5:** commit `feat(f103): freshness engine + registry (news 3d / filings 5d / structural 45d)`.

---

### Task 2: Story-page evidence rows — weight sort, always-date, publisher cap, dim

**Files:**
- Modify: `gpu_agent/dashboard/story_model.py` (`_series_evidence`, `_finding_rows`, `_related`, + narrated related @:452)
- Modify: `gpu_agent/dashboard/story_render.py` (panel JS row: dim class + "aging" mark; CSS)
- Test: `tests/dashboard/test_story_model.py`, `tests/dashboard/test_story_render.py` (append)

**Interfaces:**
- All three builders gain params `(…, today: dt.date, cfg: FreshnessConfig)` (threaded from `build_story_model`, which loads the config ONCE; a `cfg=None` default loads lazily so external callers keep working). Each row gains `"weight": float` and keeps `"date"` (now REQUIRED in the dict even when empty-string — the renderer prints `undated` for empty).
- New ordering: candidate rows collected first (dedup by URL as today), then **one row per registrable domain** (netloc minus a leading `www.`; keep the highest-weight row per domain), then sort descending by weight, then cap (3/3/2 as today).
- Narrated related rows (@:452) gain computed `weight` the same way (kind via `classify(url, None, cfg)`).
- `story_render._PANEL` row render: append the date as today, plus `if(f.weight!=null&&f.weight<0.25){row.className+=' ev-aging';}` and an `· aging` suffix span; `f.date||'undated'` replaces bare `f.date`. CSS: `.ev-aging{opacity:.55}` `.ev-aging .ev-take::after{content:" · aging";color:#a33;font-size:10px}` (author fresh — no dim class exists on main). Scene related rows: same dim via a server-side `st-aging` class when `weight < AGING_THRESHOLD`.

- [ ] **Step 1: Failing tests** (fixture stores: give `f-1` two evidence entries on the SAME domain with different dates + one old `investor.nvidia.com` entry dated `2026-05-28`):

```python
def test_evidence_rows_sorted_by_weight_and_dated(tmp_path): ...
    # rows: weights descending; every row has "date" key; each dict has "weight"
def test_one_row_per_publisher_keeps_freshest(tmp_path): ...
    # same-domain duplicate collapsed to the newer entry
def test_may_filing_ranks_last_and_flags_aging(tmp_path): ...
    # the 2026-05-28 investor.nvidia.com row: weight < 0.25, sorted last
def test_panel_js_dim_contract(): ...
    # _PANEL contains "ev-aging", "undated", "f.weight"
def test_scene_related_aging_class(tmp_path): ...
```

Write full bodies against the extended `_store` fixture; exact asserts per the Interfaces block.

- [ ] **Step 2:** run → FAIL. **Step 3:** implement. **Step 4:** dashboard suite green (existing tests updated ONLY where they assert the old ordering — enumerate each in the task report; anything else red = question-stop). **Step 5:** commit `feat(f103): evidence rows decay-sorted, dated, publisher-capped, aging-dimmed`.

---

### Task 3: Explore findings page — weight sort + aging mark

**Files:**
- Modify: `gpu_agent/dashboard/explore_render.py` (`_find_card`, `render_findings_page`)
- Test: `tests/dashboard/test_explore_findings.py` (append)

**Interfaces:** `_find_card(f, today, cfg)` computes the finding's weight (date = `observedAt or asOf`; kind via `classify` on its first evidence URL + `indicatorId`), adds `data-weight`, an `xp-aging` class + visible "aging" chip when `< AGING_THRESHOLD`; `render_findings_page` sorts WITHIN each side-group descending by weight (group order unchanged). CSS `.xp-aging{opacity:.55}`.

- [ ] **Steps 1–5:** failing tests (within-group weight order; the aging chip on an old fixture finding; `data-weight` present; filter script untouched byte-wise) → implement → green → commit `feat(f103): explore findings decay-sorted with aging marks`.

---

### Task 4: Narrator aged-claim gate check (prompt-neutral)

**Files:**
- Modify: `gpu_agent/narrator/gate.py` (append Check 7)
- Test: `tests/narrator/test_gate.py` (append)

**Interfaces:** Check 7 in `gate_narrator`: for each scene, compute each cited finding's weight (evidence dates from `inputs["findings"]`; kind via `classify`; `today` from `inputs["storyDate"]`; cfg loaded once at gate top). If a scene has claims and ALL cited findings weigh `< AGING_THRESHOLD`, the scene's paragraphs must contain a date token (regex: a four-digit year OR a month name) — else violation `"scene N leans only on aged evidence and must date its claims in prose"`. Prompt files untouched — **narrator pin must stay GREEN this task** (`pytest tests/narrator/test_prompt_pin.py` in Step 4).

- [ ] **Steps 1–5:** failing tests (aged-only scene without a date token → violation; same scene with "in late May 2026" → passes; fresh-evidence scene unaffected; pin green) → implement → green → commit `feat(f103): narrator gate check 7 - aged claims must be dated in prose`.

---

### Task 5: Manifest cadence model + helper

**Files:**
- Modify: `gpu_agent/manifest.py` (`ExpectedSource.cadence`, `CoverageManifest.earningsDates`, helper), `manifests/chips.merchant-gpu.json`
- Test: `tests/test_manifest.py` (append; read the existing test file's style first)

**Interfaces:**
- `ExpectedSource` gains `cadence: Optional[Literal["earnings-window", "weekly"]] = None`.
- `CoverageManifest` gains `earningsDates: dict[str, str] = {}` (entity → next-earnings `YYYY-MM-DD`, user-maintained) and now EXPOSES `primaryDomains: list[str] = []` (closing the known model gap — additive, nothing breaks).
- `gather_priority(source: ExpectedSource, manifest: CoverageManifest, today: dt.date) -> str` — pure: `"heavy"` if `cadence == "earnings-window"` and any `earningsDates` value is within ±7 days of `today`; `"light"` if `cadence` set and outside every window; `"normal"` when `cadence is None`.
- Manifest JSON edits: `nvda-earnings` (@:116) + `amd-earnings` (@:127) + `nvda-10k-risk-factors` (@:229) gain `"cadence": "earnings-window"`; top-level `"earningsDates": {"nvidia": "2026-08-26", "amd": "2026-08-04"}` (VERIFY the actual next announced dates with a quick web check at build time; if unverifiable, use these placeholders and flag in the task report).

- [ ] **Steps 1–5:** failing tests (round-trip load exposes cadence/earningsDates/primaryDomains; `gather_priority` heavy inside ±7d, light outside, normal without cadence; unknown cadence value rejected) → implement → green (`load_manifest` on the real manifest still validates) → commit `feat(f103): manifest earnings-window cadence + gather_priority helper`.

---

### Task 6: Gather-skill budget wording

**Files:**
- Modify: `.claude/skills/gather-category/SKILL.md`
- Test: none automated beyond Step 1's verification (skill files are prose); full suite guards regressions.

- [ ] **Step 1:** verify this skill file is NOT fingerprint-pinned: `grep -rn "gather-category" tests/ | grep -i "fingerprint\|conformance"` → expect EMPTY. Non-empty → question-stop (a lockstep re-record would be needed).
- [ ] **Step 2:** add to the round-building section: before allocating the daily doc budget, compute `gather_priority` per manifest source (`python -m gpu_agent.cli` has no verb for this — the skill computes it by reading the manifest via a 3-line inline python snippet documented in the skill, or simply instructs the orchestrator: "official-IR sources with `cadence: earnings-window` outside their ±7-day window rank LAST for the doc budget and are fetched at most weekly; inside the window they are fetched every cycle"). Keep the wording ≤10 lines, matching the skill's existing voice.
- [ ] **Step 3:** full suite spot-check + commit `feat(f103): gather skill respects earnings-window cadence`.

---

### Task 7: Narrator inputs annotation + prompt rules + pin re-record (ONE commit)

**Files:**
- Modify: `gpu_agent/narrator/inputs.py`, `gpu_agent/narrator/prompt.py`, `fixtures/narrator/prompt-pin.json` (via the recorder), `fixtures/narrator/hash-input.json` ONLY if its shape must gain the new keys
- Test: `tests/narrator/test_inputs.py`, `tests/narrator/test_prompt.py`, `tests/narrator/test_prompt_pin.py`

**Interfaces:**
- `inputs.py`: every findings entry gains `"freshnessWeight": float` (finding-level: max over its evidence entries' weights — the finding is as fresh as its freshest evidence); every docPool entry gains `"freshnessWeight"`. Computed with the engine; `today` = the storyDate.
- `prompt.py` `NARRATOR_SYSTEM` gains three bullets (exact text, then adjust only for voice consistency with neighbors):
  - `- Prefer the freshest evidence for every claim; each finding and document carries a freshnessWeight from 1.0 (today) toward 0 (old).`
  - `- If you cite evidence older than about three weeks, say its age in the prose ("at their late-May earnings call ..."). Never present old news as new.`
  - `- On a quiet day, say plainly that little changed; do not dress aged evidence (freshnessWeight under 0.25) up as today's news.`
- Pin: run `scripts/narrator-pin-record.py`; the new pin lands IN THIS COMMIT with the prompt/input changes (Phase B convention). `tests/narrator/test_prompt_pin.py` green after re-record.

- [ ] **Step 1:** failing tests (findings + docPool entries carry `freshnessWeight`; the freshest-evidence-wins rule; system prompt contains `freshnessWeight` and the never-present-old-as-new rule; pin test RED before re-record). **Step 2:** implement + re-record. **Step 3:** all narrator tests green; `git diff --stat fixtures/evals gpu_agent/evals` EMPTY. **Step 4:** commit `feat(f103): narrator freshness annotations + prose-dating rules + pin re-record`.

---

### Task 8: Close-out — smoke on store copy, full suite, sentinel

- [ ] **Step 1:** copy store → `../../work/f103-smoke/store`; build the site from the copy; verify by grep/eye: the May-vintage `investor.nvidia.com` evidence (if still cited by the current scorecard) now renders dated, weight-sorted to the bottom, with the aging mark; no scene shows an undated official-IR row; Explore findings groups are weight-ordered. Record observations.
- [ ] **Step 2:** `narrator --emit-prompt` against the copy: bundle includes `freshnessWeight` on real findings.
- [ ] **Step 3:** full suite → green; forbidden-diff check EMPTY (Global Constraints); all four pins green (narrator pin at its NEW recorded hash).
- [ ] **Step 4:** sentinel `.superpowers/handoffs/f103-freshness-DONE.md` (summary, commits, smoke observations, the earnings-dates verification status from Task 5, "STOP before merge — only the user merges").
- [ ] **Step 5:** final commit, explicit paths.

---

## Self-Review

1. **Spec coverage:** §2 engine+registry → T1 (incl. the never-capturedAt anchor and missing-date fallback); §3.1 page → T2 (rows) + T3 (Explore) — dates-always, weight sort, dim <0.25, publisher cap all tested; §3.2 narrator → T4 (gate, prompt-neutral) + T7 (annotations + rules + pin, one commit); §3.3 gather → T5 (model+helper+JSON) + T6 (skill wording, with the not-pinned verification); §4 constraints → Global Constraints + per-task pin checks; §5 tests → per-task; §6 sequencing → T7 last, deploy left to the user post-merge. Judge untouched: no task lists a judgment file.
2. **Placeholders:** T2/T3 Step-1 test names carry `...` bodies BUT each is bound to exact asserts in its Interfaces block and the instruction to write full bodies; T5's earnings dates are explicitly flagged as verify-or-placeholder with a report requirement. No TBDs.
3. **Type consistency:** `FreshnessConfig`/`load_freshness`/`classify`/`weight`/`parse_date`/`AGING_THRESHOLD` (T1) used in T2/T3/T4/T7 with the same signatures; `gather_priority(source, manifest, today)` T5→T6; `freshnessWeight` key name identical in T7 inputs and prompt bullets; threshold 0.25 always via `AGING_THRESHOLD`.
