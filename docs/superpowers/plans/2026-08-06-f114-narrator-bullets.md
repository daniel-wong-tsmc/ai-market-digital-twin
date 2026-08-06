# F114 Narrator-Authored Bullets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The narrator brain writes the three "What changed" bullets itself — self-contained, concrete, ≤ 28 words each — replacing the mechanical scene-chopping, with the gate, citation audit, and prompt pin extended in lockstep.

**Architecture:** `StoryBullet` joins the narrator answer schema (artifact schemaVersion 2); the gate gains mechanical bullet checks; the prompt gains one section and the narrator pin is re-recorded in the same commit; `citation_audit` collects bullet numbers as claims; `gpu_agent/dashboard/bullets.py` prefers artifact bullets and keeps the mechanical condenser as the only fallback.

**Tech Stack:** Python (repo venv), pydantic v2 models, pytest. No web/ changes (bullet payload shape to the dashboard is unchanged).

**Spec:** `docs/superpowers/specs/2026-08-06-f114-narrator-bullets-design.md`.

## Global Constraints

- **GATED LANE — exclusive prompt lane.** Worktree `.worktrees/f114-narrator-bullets`, branch `f114-narrator-bullets`; python `../../.venv/Scripts/python`. No other prompt-affecting lane may run while this is open.
- MUST NOT TOUCH: `fixtures/evals/` (F6 stays byte-untouched — this lane cannot redden F6), `gpu_agent/evals/`, `gpu_agent/extraction/`, `gpu_agent/judgment/`, `gpu_agent/scoring.py`, `gpu_agent/report.py`, `registry/indicators.json`, `registry/series-indicators.json`, `registry/freshness.json`, `web/`.
- The ONLY pin that moves: `fixtures/narrator/prompt-pin.json`, re-recorded in the SAME commit as the prompt change (Task 3 only). NO run-cycle step change is expected; if one becomes necessary, QUESTION-STOP.
- Quality mechanism stays gate + pin — NO scored eval bar (F101b user decision).
- Bullet copy rules (enforced by gate, stated in prompt): ≤ 28 words; self-contained; ≥ 1 digit; must not open with They/It/These/Those/That; plain English, no acronyms; existing banned-word and outlet-string checks apply.
- Question-stop rule verbatim (CLAUDE.md) in every task brief. Commit per task; `git log --oneline -1` before each commit.

## File Structure

```
gpu_agent/narrator/schema.py     MOD  StoryBullet model; bullets on NarratorAnswer; schemaVersion 1|2
gpu_agent/narrator/gate.py       MOD  bullet checks appended to gate_narrator failures
gpu_agent/narrator/prompt.py     MOD  bullet section (Task 3 ONLY, with pin re-record)
fixtures/narrator/prompt-pin.json MOD Task 3 ONLY, same commit
gpu_agent/citation_audit.py      MOD  bullets contribute claims
gpu_agent/dashboard/bullets.py   MOD  artifact-bullets-first + fallback
tests/test_narrator_bullets_schema.py  NEW
tests/test_narrator_bullets_gate.py    NEW
tests/test_citation_audit_bullets.py   NEW
tests/test_dashboard_bullets.py        MOD  add artifact-preference cases
```

---

### Task 1: Schema — `StoryBullet`, artifact v2

**Files:** Modify `gpu_agent/narrator/schema.py`; Test `tests/test_narrator_bullets_schema.py`.

**Interfaces — Produces:**

```python
class StoryBullet(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str
    claimFindingIds: list[str]

class NarratorAnswer(BaseModel):
    ...existing fields...
    bullets: Optional[list[StoryBullet]] = None   # None = pre-F114 answer (v1)

class StoryArtifact(NarratorAnswer):
    schemaVersion: Literal[1, 2]                   # was Literal[1]
```

- [ ] **Step 1: Failing tests** — a v2 artifact dict with 3 bullets validates and round-trips; a v1 artifact dict WITHOUT `bullets` (copy the shape of `store/chips.merchant-gpu/story/2026-08-05.json`) still validates (back-compat is the point); `extra="forbid"` still rejects unknown bullet keys.

```python
def test_v1_artifact_still_validates():
    art = json.loads(Path("store/chips.merchant-gpu/story/2026-08-05.json").read_text(encoding="utf-8"))
    StoryArtifact.model_validate(art)   # no bullets key, schemaVersion 1

def test_v2_bullets_roundtrip():
    b = {"text": "AMD's data-center sales hit $6.7 billion last quarter, nearly triple two years ago.",
         "claimFindingIds": ["abc-1"]}
    a = _minimal_answer(); a["bullets"] = [b, b, b]
    assert NarratorAnswer.model_validate(a).bullets[0].text.startswith("AMD")
```

- [ ] **Step 2: FAIL. Step 3: Implement. Step 4: PASS + full suite (proves nothing downstream chokes on the widened Literal). Step 5: Commit** `feat(f114): StoryBullet schema, artifact v2`.

---

### Task 2: Gate — mechanical bullet checks

**Files:** Modify `gpu_agent/narrator/gate.py`; Test `tests/test_narrator_bullets_gate.py`.

**Interfaces:** `gate_narrator(answer, inputs, cfg)` already returns `list[str]` failure messages; bullet failures append to it. Read the existing checks first and reuse their helpers (banned words, outlet strings) — do not duplicate detection logic.

Checks (each its own message, all mechanical):
1. `bullets` present and exactly 3 (when `answer.bullets is not None`; a None stays legal at the schema layer — the PROMPT demands them, so also fail here when None: "narrator answer has no bullets").
2. Each ≤ 28 words (`len(text.split())`).
3. Each contains ≥ 1 digit.
4. First word not in `{"They","It","These","Those","That"}` (case-sensitive on the capitalized forms).
5. Existing banned-word + outlet-string checks run over bullet texts.
6. Every `claimFindingIds` non-empty and every id resolves in `inputs` findings (same lookup the scene check uses).

- [ ] **Step 1: Failing tests** — one test per check with a minimal valid answer mutated one way each; plus the all-clean case returns no bullet-related failures.
- [ ] **Step 2: FAIL. Step 3: Implement. Step 4: PASS. Step 5: Commit** `feat(f114): narrator gate bullet checks`.

---

### Task 3: Prompt section + pin re-record (SAME COMMIT — the only pin touch)

**Files:** Modify `gpu_agent/narrator/prompt.py`; Modify `fixtures/narrator/prompt-pin.json`; Test: the existing pin test (`tests/` narrator pin tripwire) goes red on the prompt change and green after the re-record — that sequence IS the verification.

Prompt addition (place alongside the existing output-shape instructions; wording may be tuned to fit house style, meaning may not):

> Also write `bullets`: the day's three takeaways, for an executive who reads nothing else.
> Each is one sentence of at most 28 words, understandable entirely on its own — name the
> actor, the number or date that matters, and why it matters. Never open with "They", "It",
> "These", "Those" or "That". Every number must come from the findings you cite in that
> bullet's `claimFindingIds`. Plain English only.

- [ ] **Step 1: Run the narrator pin test — GREEN before (baseline).**
- [ ] **Step 2: Add the prompt section + `bullets` to the answer-shape description. Run pin test — RED (proves the pin sees it).**
- [ ] **Step 3: Re-record the pin the same way F103 did** (regenerate via the recorded recipe in `gpu_agent/narrator/pin.py` — `compute_narrator_prompt_hash` over the emitted hash input; never hand-edit the hash).
- [ ] **Step 4: Pin test GREEN; full suite; `git status` shows ONLY `prompt.py` + `prompt-pin.json` changed.**
- [ ] **Step 5: ONE commit** `feat(f114): narrator writes the three takeaway bullets (pin re-recorded in lockstep)`.

---

### Task 4: Citation audit covers bullets

**Files:** Modify `gpu_agent/citation_audit.py`; Test `tests/test_citation_audit_bullets.py`.

**Interfaces:** Read how scene paragraphs become `Claim` objects (`audit_claim(claim, reader, ...)`) and mirror it: every number in each `bullets[i].text` becomes a claim whose candidate findings are that bullet's `claimFindingIds`, labeled `bullet:<i>` in the audit artifact (scenes use their own labels; follow the existing naming pattern exactly).

- [ ] **Step 1: Failing tests** — an artifact with a bullet whose number matches its cited finding → audited, not flagged; a bullet number tracing to nothing → flagged with label `bullet:0`; a v1 artifact (no bullets) audits exactly as before (regression case pinned with a golden count).
- [ ] **Step 2: FAIL. Step 3: Implement. Step 4: PASS. Step 5: Commit** `feat(f114): citation audit covers narrator bullets`.

---

### Task 5: Exporter prefers artifact bullets

**Files:** Modify `gpu_agent/dashboard/bullets.py`; Test: extend `tests/test_dashboard_bullets.py`.

**Interfaces — the decision rule inside `build_bullets(story, scorecard, series_reg, store_dir)` (signature unchanged, callers untouched):**

```python
use_artifact = bool(story.get("bullets")) and len(story["bullets"]) == 3
# fellBack days write the assembler story with no bullets -> mechanical path
```

- Artifact path: `text` = bullet text verbatim; `sources` = `refs_for_finding_ids(bullet["claimFindingIds"], findings_by_id)`; chart matching (curated → fallback → reason) now derives tags/indicator ids from the BULLET's `claimFindingIds` instead of the scene's — reuse `_scene_tags`/`_scene_indicator_ids` by passing a synthetic `{"claimFindingIds": [...]}` dict (their only consumed key; verify when reading).
- Mechanical path: existing behavior, byte-identical output (pin it with a golden test before touching anything).

- [ ] **Step 1: Failing tests** — golden test freezing today's mechanical output on the 2026-08-05 fixture FIRST (regression pin); then: story with 3 artifact bullets → texts verbatim, sources from bullet ids; story with `bullets: None` → mechanical output identical to the golden; artifact bullet whose ids hit the AMD series still gets the curated chart.
- [ ] **Step 2: FAIL. Step 3: Implement. Step 4: PASS + full suite. Step 5: Commit** `feat(f114): dashboard prefers narrator bullets, mechanical fallback kept`.

---

### Task 6: Lane gates + DONE sentinel

- [ ] **Step 1:** Full suite green; the four pins: F6 green AND `git diff main --name-only -- fixtures/evals` EMPTY; narrator pin green at its NEW hash; scoring replay green; F83 green and UNCHANGED (no step edits happened — verify `git diff main --name-only -- tests/test_run_cycle_conformance.py` empty).
- [ ] **Step 2:** Forbidden diff empty across `gpu_agent/evals gpu_agent/extraction gpu_agent/judgment gpu_agent/scoring.py gpu_agent/report.py registry/ web/`.
- [ ] **Step 3:** Write `.superpowers/handoffs/f114-narrator-bullets-DONE.md` — state, the golden-pinned fallback guarantee, live criteria (spec §5: next live cycle produces 3 gate-passing bullets; audit covers them; a fellBack day still renders). Commit. **STOP — only the user merges.**

## Self-Review Notes

- Spec §2 → Tasks 1 (schema), 2 (gate), 3 (prompt+pin), 4 (audit), 5 (exporter). §3 guardrails → Global Constraints + Task 6 checks. §5 criteria → sentinel.
- The 28-word cap, digit rule, and pronoun list appear identically in Task 2 (gate) and Task 3 (prompt) — single source of truth for the build is the spec §2 wording; implementers must keep them in sync.
- No web/ change: the dashboard bullet payload shape is unchanged, so F113's render work stays cleanly out of this lane.
