# F66 — Post-hoc Citation Audit (deterministic half) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every number in the day's story scenes and implication lines traces to a finding that
claim actually cites — checked after the prose is written, not just at write time.

**Architecture:** One new leaf module (`gpu_agent/citation_audit.py`) that reads finished artifacts
(`store/<cat>/story/<date>.json`, `store/implications/<cat>/<asOf>.json`) plus `store/findings/`,
and writes `store/<cat>/audit/<date>.json`. It reuses the F14 wiki gate's tokenizer — factored out,
not copied — and adds rounding tolerance on top. No frozen-core file, no brain prompt, and no
existing gate changes behaviour. The only shared-surface edit is the F83 lockstep (Task 4), which
is isolated in its own task per the F98 precedent.

**Tech Stack:** Python 3 (`.venv/Scripts/python` from root; `../../.venv/Scripts/python` from the
worktree), pydantic v2, stdlib `decimal`, pytest.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-28-f66-post-hoc-citation-audit-design.md`. Read it first;
  D1–D4 are user-approved, D5a/b/c and D2′ are agent-recommended (spec §7/§8).
- **Frozen core, brains, prompts byte-untouched:** `git diff --stat fixtures/ registry/
  gpu_agent/evals gpu_agent/judgment gpu_agent/extraction gpu_agent/narrator/prompt.py` EMPTY at
  every commit. This lane touches **no brain prompt**, so the F6 pin must stay green untouched —
  if `tests/test_evals_baseline_pin.py` goes red, something is wrong with the change, not the pin.
- **All four pins green at every commit** (F6, narrator prompt pin, scoring-v1 replay, F83). F83 is
  legitimately red *only* between the start and end of Task 4, and green at Task 4's commit.
- **`gpu_agent/wiki/ingest.py` behaviour must not change.** Task 1 moves a private helper; the wiki
  gate keeps exact-token matching. `tests/` for wiki ingest must pass unmodified.
- Worktree `.worktrees/f66-citation-audit`, branch `f66-citation-audit`. Never touch root `store/`
  or root main (a live daily cycle runs there). Do not edit `docs/fix-backlog.md` or
  `docs/superpowers/HANDOFF.md` — the orchestrator owns both.
- **Question-stop rule (verbatim):** a lane agent that hits a question or design fork while
  producing its brainstorm, spec, or implementation plan — or a mid-build discovery that reopens a
  design decision — STOPS instead of picking: it writes the question(s) plus its recommendation to
  `.superpowers/handoffs/<lane>-QUESTIONS.md` and ends its turn so the orchestrator can relay them
  to the user; it resumes only with the user's answers. Proceeding on AFK-precedent picks at the
  design stages is NOT permitted. Trivial mechanical choices that don't shape design may proceed,
  but every one still lands in the spec's decision-provenance section.
- Suite green at every commit (expect 3–4 skips). `git log --oneline -1` immediately before each
  commit (concurrent-instance guard).

**Verified facts (2026-07-28, from the lane's own investigation):**

- `_numeric_tokens(text) -> set[str]` @ `gpu_agent/wiki/ingest.py:97-105`; regex `_NUMERIC_RE =
  r"\d[\d,]*(?:\.\d+)?"` @:90; strips thousands commas, drops tokens with <2 digits.
- `_allowed_numeric_tokens` @ `wiki/ingest.py:108-136` — the four `value.number` renderings are
  `str(v)`, `repr(v)`, `f"{v:g}"`, and `str(int(v))` when `v.is_integer()` (@:126-131), plus
  `e.excerpt` and `e.date` (@:132-134). `_validate_enrichment_gate` @:139-152 emits
  `"{pageId}: uncited number {token}"`.
- `StoryArtifact` / `StoryScene` @ `gpu_agent/narrator/schema.py:29-37` — scene fields `n`,
  `title`, `paragraphs: list[str]`, `visual`, `claimFindingIds: list[str]`, `sourceLine`,
  `relatedDocs`. `extra="forbid"`.
- `StoryStore` @ `gpu_agent/narrator/store.py:15-45` — `_path = root/<cat>/story/<date>.json`,
  atomic `write` via `.json.tmp` + `os.replace`, `read` returns `None` on unreadable artifacts.
  Sidecars `<date>.fallback.json` live in the same dir and must be skipped by stem regex (@:52-60).
- `ImplicationLine` @ `gpu_agent/implication.py:64-69` — `watchItem`, `dimensions`, `thesisIds`,
  `findingIds`. `ImplicationStore` @:222-240 — `root/<asOf>.json`, root is
  `<store>/implications/<categoryId>`.
- Findings on disk: `store/findings/<findingId>.json`, one file per finding, full `Finding` schema
  (`gpu_agent/schema/finding.py:31-53`; `Evidence` @:20-25 has `source,url,date,excerpt,tier`).
- `narrator` CLI verb shape @ `gpu_agent/cli.py:1483-1496`.
- F83: `EXPECTED_STEPS` @ `tests/test_run_cycle_conformance.py:158-179` (20 entries today, ending
  `("e3","narrator"), ("f","render the executive report"), ("4","layer stage"), ("5","main stage"),
  ("6","finalize the cycle log"), ("7","price-sync"), ("8","report")`); fingerprint =
  `sha256(repr(EXPECTED_STEPS))` @:184-185; sub-step regex `^\*\*\(([a-z0-9-]+)\)\s+(.*)$` @:136;
  title normalized by `_title_head` @:125-132 (truncate at the first of `" — "`, `" - "`, `"."`,
  `"("`, `"**"`, `":"`, then lowercase); fingerprint comment @ `.claude/skills/run-cycle/SKILL.md:52`.
- Narrator run-cycle step `(e3)` @ `SKILL.md:259-291`; it explicitly "never blocks the cycle" and
  ends in `narrator --record-fallback --reasons <file> --retries 2`.
- Baseline measurement to reproduce in Task 3: 80 numeric tokens across the three live story
  artifacts 2026-07-25/26/27; exactly one flag (`7.09` vs `7.0931`), which rounding tolerance clears.

---

### Task 1: Factor out the tokenizer, add rounding tolerance

**Files:**
- New: `gpu_agent/numeric_tokens.py`
- Modify: `gpu_agent/wiki/ingest.py` (import the moved helper; **no behaviour change**)
- Test: `tests/test_numeric_tokens.py` (new)

**Interfaces:**
- `numeric_tokens(text: str) -> set[str]` — moved verbatim from `wiki/ingest.py:97-105` including
  the `_NUMERIC_RE` pattern and the ≥2-digit rule. Public name (no leading underscore) since it now
  has two call sites.
- `value_renderings(v: float) -> list[str]` — the four renderings from `ingest.py:126-131`, factored
  out so both the wiki gate and the audit produce identical pools.
- `supported(token: str, allowed: set[str]) -> bool` — `True` if `token in allowed`, **or** if any
  member of `allowed` rounds to `token` at `token`'s own decimal precision. Use `decimal.Decimal`
  with `ROUND_HALF_UP`, never binary float rounding. A token with no decimal point has precision 0
  (so `7` is supported by `7.09`? **No** — see the test matrix: integer-precision rounding is
  allowed only when the allowed value's integer part matches, i.e. `7.0931 → "7"` rounds to `7`,
  which IS supported; this is deliberate and tested).
- `wiki/ingest.py` keeps exact matching: it calls `numeric_tokens` and `value_renderings` but
  **not** `supported`. Its `_numeric_tokens` / inline rendering code is deleted, not duplicated.

- [ ] **Step 0:** confirm `_numeric_tokens` and the rendering block have no other callers:
  `grep -rn "_numeric_tokens\|_allowed_numeric_tokens" gpu_agent/ tests/`. Any hit outside
  `wiki/ingest.py` and its tests = question-stop.
- [ ] **Step 1: Write the failing tests**

```python
# tests/test_numeric_tokens.py
from gpu_agent.numeric_tokens import numeric_tokens, value_renderings, supported


def test_tokenizer_matches_wiki_behaviour():
    assert numeric_tokens("a 7.0931 trillion won ($4.83 billion) deal") == {"7.0931", "4.83"}
    assert numeric_tokens("1,250 units in 2026") == {"1250", "2026"}
    assert numeric_tokens("item 1. and 5 things") == set()          # <2 digits dropped
    assert numeric_tokens("2026-06-15") == {"2026", "06", "15"}     # dates tokenize honestly


def test_value_renderings():
    assert "4.83" in value_renderings(4.83)
    r = value_renderings(75.0)
    assert "75" in r                                                # integral form present
    assert "7.52e+10" in value_renderings(7.52e10)                  # :g form present


def test_supported_exact():
    assert supported("4.83", {"4.83"})
    assert not supported("4.84", {"4.83"})


def test_supported_rounding_the_real_false_positive():
    # story said "7.09 trillion won"; the finding says 7.0931
    assert supported("7.09", {"7.0931"})
    assert supported("7.1", {"7.0931"})
    assert supported("7", {"7.0931"})


def test_supported_rounding_does_not_launder_a_wrong_number():
    assert not supported("7.19", {"7.0931"})
    assert not supported("8", {"7.0931"})
    assert not supported("70.9", {"7.0931"})    # no magnitude slop


def test_supported_rounds_half_up_not_bankers():
    assert supported("2.5", {"2.45"})
    assert supported("3", {"2.5"})              # ROUND_HALF_UP, not banker's rounding to 2


def test_supported_handles_non_numeric_gracefully():
    assert not supported("2026", {"not-a-number"})
```

- [ ] **Step 2:** run `../../.venv/Scripts/python -m pytest tests/test_numeric_tokens.py -v` → FAIL
  (`ModuleNotFoundError: gpu_agent.numeric_tokens`).
- [ ] **Step 3:** implement `gpu_agent/numeric_tokens.py`; rewire `wiki/ingest.py` to import
  `numeric_tokens` and `value_renderings`, deleting its private copies. Keep the wiki gate's
  `token not in allowed` comparison **exactly as it is** — do not introduce `supported` there.
- [ ] **Step 4:** new file green (7 tests), then `../../.venv/Scripts/python -m pytest -k "wiki or
  ingest" -q` → green **with zero test-file edits**. If any wiki test needs changing, that is a
  behaviour change and a question-stop.
- [ ] **Step 5:** commit `refactor(f66): factor numeric tokenizer out of wiki gate; add rounding-tolerant match`.

---

### Task 2: The audit core — claims, pools, verdicts, artifact

**Files:**
- New: `gpu_agent/citation_audit.py`
- Modify: `.gitignore` (whitelist `store/*/audit/` beside the existing `store/implications/` entry)
- Test: `tests/test_citation_audit.py` (new)

**Interfaces:**
- `@dataclass(frozen=True) class Claim: claimKey: str; text: str; findingIds: tuple[str, ...]`
- `claims_from_story(art: StoryArtifact) -> list[Claim]` — one per scene,
  `claimKey=f"scene:{sc.n}"`, `text=" ".join(sc.paragraphs)`, ids from `sc.claimFindingIds`.
- `claims_from_implication(art: ImplicationArtifact) -> list[Claim]` — one per line,
  `claimKey=f"impl:{i}"` (0-based, dispatch order), `text=line.watchItem`, ids from
  `line.findingIds`.
- `class FindingsReader` — wraps `store/findings/`; `get(fid) -> Finding | None`. Reuse the repo's
  existing findings-store reader if one exists (**Step 0 checks**: `grep -rn "store/findings\|
  findings.exists\|FindingStore" gpu_agent/ | head -20`); only write a new reader if none is usable
  from a leaf module without an import cycle.
- `allowed_tokens(claim, reader, extra_texts: Sequence[str]) -> tuple[set[str], list[str]]` —
  returns (pool, unresolved ids). Pool = union over resolved findings of
  `numeric_tokens` over `statement`, `why`, `value_renderings(value.number)`, each `evidence.excerpt`
  and `evidence.date`; plus `numeric_tokens` over `extra_texts` (D5b: story KPI/series values).
- `audit_claim(claim, reader, extra_texts) -> ClaimResult` where
  `ClaimResult(claimKey, verdict: Literal["clean","flagged","skipped"], flaggedTokens: list[str],
  unresolvedIds: list[str], citedFindingIds: list[str])`.
  - `findingIds == []` → `verdict="skipped"`, no flags (spec §6 honest-empty).
  - unresolved id → always `verdict="flagged"` with that id in `unresolvedIds`.
  - every prose token must satisfy `supported(token, pool)`; failures land in `flaggedTokens`,
    sorted, deduped.
- `run_audit(store_root, category_id, date) -> AuditArtifact` — reads both artifacts (a missing
  implication artifact is normal and contributes zero claims; a missing story artifact means
  nothing to audit → an empty clean result, not a crash), returns the pydantic
  `AuditArtifact(schemaVersion, categoryId, asOf, claims, summary)` with
  `summary={"claimsAudited": int, "flagged": int, "skipped": int}`.
- `class AuditStore` — `root/<categoryId>/audit/<date>.json`, atomic write mirroring
  `narrator/store.py:22-28` (`.json.tmp` + `os.replace`), `model_dump_json(indent=2)`.

**D5b sourcing note:** `extra_texts` for the story is the artifact's own computed display values.
**Step 0 must determine exactly where those live** — candidates are `StoryArtifact.kpiPicks`
(`narrator/schema.py:40-45`) and the series/KPI values assembled in
`gpu_agent/dashboard/story_model.py`. If the computed medians are produced only at render time in
`story_model` and are not present in the artifact, importing `story_model` from `citation_audit`
would couple a leaf module to the dashboard — **that is a design fork: question-stop** with the
options (a) pass the values in from the CLI layer, (b) recompute from `store/series/`, (c) accept
the false positives.

- [ ] **Step 0:** the findings-reader check and the D5b sourcing check above.
- [ ] **Step 1: Write the failing tests.** Build small in-memory/tmp_path fixtures — a two-scene
  story artifact, a two-line implication artifact, and three finding JSONs — rather than reading
  live `store/`. Cover:

```python
# tests/test_citation_audit.py  (assert-level contract; fill bodies with the fixtures from Step 0)
def test_clean_claim_passes():
    # scene prose quotes 4.83 and 2026; the cited finding's value.number is 4.83 and evidence date 2026-07-23
    # -> verdict "clean", flaggedTokens == []

def test_rounded_number_passes():
    # prose "7.09", finding statement "7.0931 trillion won" -> "clean"

def test_fabricated_number_is_flagged():
    # prose "$9.99", no cited finding contains it -> verdict "flagged", flaggedTokens == ["9.99"]

def test_number_from_an_uncited_finding_is_flagged():
    # the number exists in the store but in a finding this claim does NOT cite -> flagged
    # (this is the mis-attribution case, and the reason the pool is per-claim not per-cycle)

def test_unresolved_finding_id_is_flagged():
    # claimFindingIds references an id with no file -> flagged, unresolvedIds == [that id]

def test_zero_citation_scene_is_skipped_not_flagged():
    # claimFindingIds == [] -> verdict "skipped" even with numbers in the prose

def test_evidence_date_tokens_are_allowed():
    # prose "on 23 July" with evidence date 2026-07-23 -> "clean" (the statement-only pool would flag 23)

def test_implication_lines_are_audited():
    # claimKey "impl:0"/"impl:1", watchItem text, per-line findingIds

def test_missing_implication_artifact_is_not_an_error():
    # story-only cycle -> audit runs, claims are scenes only

def test_artifact_roundtrips_and_summary_counts():
    # AuditStore.write then read; summary claimsAudited/flagged/skipped match the claim list
```

- [ ] **Step 2:** run → FAIL (module missing).
- [ ] **Step 3:** implement `gpu_agent/citation_audit.py` per the Interfaces block; add the
  `.gitignore` whitelist line.
- [ ] **Step 4:** new file green (10 tests); full suite green.
- [ ] **Step 5:** commit `feat(f66): deterministic citation audit over story scenes + implication lines`.

---

### Task 3: CLI verb + the live-artifact replay proof

**Files:**
- Modify: `gpu_agent/cli.py` (new `audit-citations` subparser + handler)
- Test: `tests/test_cli_audit_citations.py` (new)
- Test: `tests/test_f66_live_replay.py` (new)
- New fixtures: `tests/fixtures/f66/` — copies of the three live story artifacts and the findings
  they cite (**copied into the repo, not read from `store/`** — the suite must not depend on
  mutable live state)

**Interfaces:**
- `gpu-agent audit-citations --store store --category <id> --date YYYY-MM-DD [--out <path>]`,
  modelled on the `narrator` verb (`cli.py:1483-1496`). Reuse `_narrator_date` for `--date`.
- Exit **0** when no claim is flagged; exit **1** with a `CITATION AUDIT FAILED:` block listing
  `<claimKey>: uncited number <token>` / `<claimKey>: unresolved finding <id>` lines on stderr —
  wording deliberately echoing the wiki gate's `uncited number` so the two read the same.
- The artifact is written **on both paths** (clean and flagged): the audit record is evidence, and
  a cycle that flagged something must leave a trace. This differs from the gates that write nothing
  on rejection, and is intentional — note it in the task report.

- [ ] **Step 0:** copy the three story artifacts (`store/chips.merchant-gpu/story/2026-07-2{5,6,7}.json`)
  and every finding they cite into `tests/fixtures/f66/`. Record the file count in the task report.
- [ ] **Step 1: Write the failing tests**

```python
# tests/test_cli_audit_citations.py
def test_clean_run_exits_zero_and_writes_artifact(tmp_path): ...
def test_flagged_run_exits_one_and_still_writes_artifact(tmp_path): ...
def test_stderr_names_the_claim_and_the_token(tmp_path): ...
def test_missing_story_artifact_exits_zero_with_empty_audit(tmp_path): ...

# tests/test_f66_live_replay.py  — the measured baseline from spec §4, frozen
def test_three_live_days_audit_clean():
    """80 numeric tokens across 2026-07-25/26/27; zero flags under rounding tolerance.
    The single exact-match false positive (7.09 vs 7.0931) is the reason `supported`
    exists -- if this test ever goes red, either the matcher regressed or a real
    citation defect entered the fixtures."""
    # per-day: assert result.summary["flagged"] == 0
    # and assert the total numeric-token count audited == 80 (guards the tokenizer too)

def test_exact_matching_would_have_flagged_the_rounded_token():
    # same fixtures, comparing with `token in allowed` instead of `supported`
    # -> exactly one flag, "7.09", on 2026-07-26 scene 2. Pins WHY rounding tolerance is there.
```

- [ ] **Step 2:** run → FAIL (no such verb).
- [ ] **Step 3:** implement the subparser + handler.
- [ ] **Step 4:** both files green; full suite green.
- [ ] **Step 5:** commit `feat(f66): audit-citations CLI verb + live-artifact replay proof`.

---

### Task 4: F83 lockstep — the `(e4)` run-cycle sub-step

Isolated per the F98 precedent: this is the only task touching a shared, pinned surface, so it
lands in one commit that is green on both sides of the lockstep.

**Files:**
- Modify: `.claude/skills/run-cycle/SKILL.md` (new `**(e4)` block + regenerated fingerprint @:52)
- Modify: `tests/test_run_cycle_conformance.py` (`EXPECTED_STEPS` @:158-179)

**Interfaces:**
- New sub-step inserted **after** `(e3) Narrator` (`SKILL.md:259-291`) and **before**
  `(f) Render the executive report` (@:292). First line must be exactly parseable by
  `^\*\*\(([a-z0-9-]+)\)\s+(.*)$` and `_title_head` must normalize to **`citation audit`**:

  `**(e4) Citation audit — post-hoc, deterministic (no LLM).** ...`

  (`_title_head` truncates at the first `" — "`, so the pinned head is `citation audit`.)
- Body prescribes:
  ```
  .venv/Scripts/python -m gpu_agent.cli audit-citations --store store \
    --category <id> --date <today>
  ```
  On a non-zero exit: **re-dispatch the narrator ONCE** with the flagged-token lines appended to
  the prompt (same shape as the `(e3)` gate-rejection path), re-run the audit; if it fails a
  **second** time, record the narrator honest-gap fallback
  (`narrator --record-fallback --reasons <file> --retries 2`) and mark **`citation-audit: failed`**
  in the cycle log. **This step never blocks the cycle** — it blocks the story artifact only
  (spec D2′). Flagged implication lines are logged, not re-dispatched (the implication step is
  already two-attempt-then-`failed`).
- `EXPECTED_STEPS` gains `("e4", "citation audit")` between `("e3", "narrator")` and
  `("f", "render the executive report")` — 21 entries.
- Fingerprint: regenerate with
  `../../.venv/Scripts/python -c "import hashlib;from tests.test_run_cycle_conformance import EXPECTED_STEPS;print(hashlib.sha256(repr(EXPECTED_STEPS).encode()).hexdigest())"`
  and paste into the `run-cycle-step-fingerprint: sha256=` comment at `SKILL.md:52`. **Never
  hand-compute it.**

- [ ] **Step 1:** edit `EXPECTED_STEPS` first; run `../../.venv/Scripts/python -m pytest
  tests/test_run_cycle_conformance.py -v` → RED on both
  `test_procedure_step_list_matches_pinned_constant` and `test_skill_fingerprint_in_sync`. Record
  both failures in the task report — that red is the proof the pin is doing its job.
- [ ] **Step 2:** add the `(e4)` block to SKILL.md → `test_procedure_step_list_matches_pinned_constant`
  goes green, `test_skill_fingerprint_in_sync` still red.
- [ ] **Step 3:** regenerate + paste the fingerprint → both green. Also confirm
  `test_gate_order_in_prescription` (@:281) is still green (`extraction < judgment < thesis < render`).
- [ ] **Step 4:** full suite green. Confirm the other three pins are untouched-green by name (F6,
  narrator prompt pin, scoring-v1 replay) — F6 especially: this lane changed no brain prompt, so a
  red F6 here means an accidental prompt edit, **not** a legitimate rebaseline. Never rebaseline
  from this lane.
- [ ] **Step 5:** commit `feat(f66): run-cycle sub-step (e4) citation audit + F83 lockstep re-record`.

---

### Task 5: Close-out

- [ ] **Step 1:** full suite `../../.venv/Scripts/python -m pytest -q` → green (expect 3–4 skips);
  record the pass/skip counts. Forbidden-diff check EMPTY:
  `git diff --stat main...HEAD -- fixtures/ registry/ gpu_agent/evals gpu_agent/judgment
  gpu_agent/extraction gpu_agent/narrator/prompt.py`.
- [ ] **Step 2:** end-to-end smoke against a **read-only copy** of live data — copy
  `store/chips.merchant-gpu/story/2026-07-27.json` plus its findings into `tmp_path`, run the CLI
  verb, confirm exit 0 and an artifact at `<tmp>/chips.merchant-gpu/audit/2026-07-27.json`. Never
  write into the real `store/`.
- [ ] **Step 3:** sentinel `.superpowers/handoffs/f66-citation-audit-DONE.md` — summary, commit
  hashes, suite counts, the four pins named green, the Step-0 findings from Tasks 2 and 3, any
  question-stops raised, the D5a/b/c + D2′ provenance caveat restated, the live criterion below,
  and **"STOP before merge — only the user merges"**.
- [ ] **Step 4:** live criterion (record, do not force): the next live cycle runs `(e4)` and writes
  `store/chips.merchant-gpu/audit/<date>.json` with `summary.flagged == 0`.
- [ ] **Step 5:** final commit, explicit paths. Do **not** edit `docs/fix-backlog.md` or
  `docs/superpowers/HANDOFF.md` — the orchestrator owns both; put the backlog wording the
  orchestrator should paste into the sentinel instead.

---

## Self-Review

1. **Spec coverage:** §6 module + `Claim` shape → T2; tokenizer reuse + D5a rounding → T1; D5b
   extra_texts → T2 Step 0 (with an explicit question-stop if the values are render-only); D1 scope
   (scenes + implication lines, nothing else) → T2 `claims_from_*` and no third builder; honest-empty
   skip → T2; artifact + `.gitignore` whitelist → T2; CLI + exit codes → T3; §4 measured baseline →
   T3's replay test, which also pins *why* rounding tolerance exists; D3 placement + F83 cost → T4;
   D2/D2′ severity ladder → T4's SKILL.md body; D4 Phase 2 deferred → no task builds it, and T2's
   `verdict` field leaves room for it; §3 out-of-scope items → no task touches them.
2. **Placeholders:** T2 Step 1 and T3 Step 1 give test *names and assert-level contracts* with
   bodies to be filled from fixtures located in their Step 0. That is deliberate — the arrange
   machinery depends on a findings-reader and a KPI-value source that must be read first — and every
   assertion is enumerated. T1's tests are complete and runnable as written. No other `...`/TBD.
3. **Type consistency:** `numeric_tokens` / `value_renderings` / `supported` signatures identical in
   T1 and T2; `Claim.findingIds` is a tuple throughout; `claimKey` format `scene:<n>` / `impl:<i>`
   used identically in T2 and T3; artifact path `store/<cat>/audit/<date>.json` identical in T2, T3,
   T5; branch/sentinel name `f66-citation-audit` consistent.
4. **Risk the plan carries on purpose:** the replay test in T3 freezes a *zero-flag* baseline. If a
   future genuine defect appears in fixtures it goes red, which is correct; but it also means the
   suite cannot demonstrate a true positive from live data, because none exists (spec §4). T2's
   `test_fabricated_number_is_flagged` and `test_number_from_an_uncited_finding_is_flagged` carry
   that burden on synthetic data instead.
