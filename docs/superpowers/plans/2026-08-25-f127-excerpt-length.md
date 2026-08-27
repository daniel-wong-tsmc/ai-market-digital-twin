# F127 Excerpt Length Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reject an over-long evidence excerpt in the shared finding gate, the same way an invented one is already rejected.

**Architecture:** Two counting helpers plus one check added to the existing `for e in f.evidence` loop in `gpu_agent/gate.py::check_finding`. That function is the single point both the extractor and `check_scorecard` route through, so one edit covers every path an excerpt travels. Stdlib only; no new module, no new dependency, no prompt bytes.

**Tech Stack:** Python 3, stdlib `re`, pytest.

**Spec:** `docs/superpowers/specs/2026-08-25-f127-excerpt-length-design.md`

## Global Constraints

- **F6 pin:** `tests/test_evals_baseline_pin.py` must stay green and its inputs byte-identical. Do not touch prompt files, cli vocab glue, or registry vocab data. If it goes red, STOP — do not re-record any baseline, do not hand-edit `fixtures/evals/baseline.json`.
- **Store is append-only.** Do not edit or delete anything under `store/`. Do not touch `work/eval-2026-08-24/`.
- **Limits, exact values:** `EXCERPT_MAX_WORDS = 50`, `EXCERPT_MAX_SENTENCES = 2`, `EXCERPT_ABSOLUTE_MAX_WORDS = 100`.
- **Rejection rule:** reject when `words > 50 AND sentences > 2`; separately reject when `words > 100` regardless of sentences.
- **Message wording, exact:**
  - `f"{f.id}: excerpt too long ({w} words > 50 and {s} sentences > 2)"`
  - `f"{f.id}: excerpt too long ({w} words > 100 absolute cap)"`
- **Test command:** from the worktree root, `../../.venv/Scripts/python -m pytest -q`. Never `python3`, never a new venv.
- **Staging:** `git add <explicit paths>` only, never `git add -A`. Run `git log --oneline -1` immediately before every commit.

---

### Task 1: Sentence and word counters in the gate

**Files:**
- Modify: `gpu_agent/gate.py` (top of file, beside `_ISO_PREFIX`)
- Test: `tests/test_gate_excerpt_length.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: `gpu_agent.gate._count_words(text: str) -> int`, `gpu_agent.gate._count_sentences(text: str) -> int`, and module constants `EXCERPT_MAX_WORDS`, `EXCERPT_MAX_SENTENCES`, `EXCERPT_ABSOLUTE_MAX_WORDS`. Task 2 uses all five.

- [ ] **Step 1: Write the failing test**

Create `tests/test_gate_excerpt_length.py`:

```python
import pytest
from gpu_agent.gate import (
    _count_words,
    _count_sentences,
    EXCERPT_MAX_WORDS,
    EXCERPT_MAX_SENTENCES,
    EXCERPT_ABSOLUTE_MAX_WORDS,
)


def test_limits_are_the_decided_numbers():
    assert EXCERPT_MAX_WORDS == 50
    assert EXCERPT_MAX_SENTENCES == 2
    assert EXCERPT_ABSOLUTE_MAX_WORDS == 100


def test_count_words_is_whitespace_split():
    assert _count_words("one two three") == 3
    assert _count_words("  padded   out  ") == 2
    assert _count_words("") == 0


@pytest.mark.parametrize("text,expected", [
    ("One sentence.", 1),
    ("No terminal punctuation at all", 1),
    ("", 1),
    ("First one. Second one.", 2),
    ("First. Second. Third.", 3),
    ("Is it? It is! Indeed.", 3),
    ("Trailing space after full stop. ", 1),
    ("Ellipsis is one terminator... still one sentence", 1),
])
def test_count_sentences_basics(text, expected):
    assert _count_sentences(text) == expected


@pytest.mark.parametrize("text", [
    "The U.S. government export control cut margins that year.",
    "Revenue rose to $6.7B in the quarter, up from $4.1B.",
    "Gross margin was 54.3% versus 40.0% a year earlier.",
    "Advanced Micro Devices, Inc. reported a record quarter.",
    "Shipments rose vs. the prior year for No. 1 supplier Corp.",
    "Analysts at Foo Co. said e.g. HBM4 yields improved.",
])
def test_abbreviations_and_decimals_do_not_end_sentences(text):
    assert _count_sentences(text) == 1


def test_real_store_excerpt_is_one_sentence():
    # Verbatim from store/findings/ir-amd-com-cfa508a5-2026-08-3.json: 70 words,
    # one sentence. The longest excerpt ever committed.
    excerpt = (
        "Gross margin for the three months ended June 27, 2026 was 54% compared to "
        "gross margin of 40% for the prior year period, a 14% increase primarily "
        "driven by the absence of inventory and related charges associated with the "
        "U.S. government export control on AMD Instinct MI308 Data Center GPU "
        "products that was recorded in the prior year period and a favorable product "
        "mix, including higher Data Center segment revenue."
    )
    assert _count_words(excerpt) == 70
    assert _count_sentences(excerpt) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `../../.venv/Scripts/python -m pytest tests/test_gate_excerpt_length.py -q`
Expected: FAIL — `ImportError: cannot import name '_count_words' from 'gpu_agent.gate'`.

- [ ] **Step 3: Write minimal implementation**

In `gpu_agent/gate.py`, directly below the `_ISO_PREFIX` line, add:

```python
# F127 — excerpt length cap. Posture doc §2, DECIDED 2026-08-22: an excerpt is
# "at most two sentences or about 50 words". That "or" is literal: an excerpt is
# rejected only when it breaks BOTH limits. Measured over all 644 committed
# excerpts, nothing breaks both; a hard 50-word cap alone would have rejected a
# real 70-word one-sentence 10-Q quote. The absolute cap is the backstop that
# stops a run-on (which counts as one sentence) from bypassing the gate entirely.
EXCERPT_MAX_WORDS = 50
EXCERPT_MAX_SENTENCES = 2
EXCERPT_ABSOLUTE_MAX_WORDS = 100

_SENTENCE_END = re.compile(r"[.!?]+(?=\s|$)")

# Tokens that end in "." without ending a sentence. Financial prose only needs a
# short list; anything missed makes the counter count HIGH, so keep it current.
_ABBREVIATIONS = frozenset({
    "u.s.", "u.k.", "e.u.", "u.s.a.",
    "inc.", "corp.", "co.", "ltd.", "llc.", "plc.", "gmbh.",
    "mr.", "mrs.", "ms.", "dr.", "prof.", "sr.", "jr.", "st.",
    "vs.", "etc.", "e.g.", "i.e.", "cf.", "al.",
    "no.", "fig.", "approx.", "est.", "avg.", "yr.", "qtr.",
    "jan.", "feb.", "mar.", "apr.", "jun.", "jul.", "aug.",
    "sept.", "sep.", "oct.", "nov.", "dec.",
})


def _count_words(text: str) -> int:
    """Word count the way the posture doc measured it: whitespace split."""
    return len(text.split())


def _count_sentences(text: str) -> int:
    """Count sentences, biased to UNDER-count.

    Under-counting lets a long excerpt through; over-counting rejects a real one.
    The count is only ever consulted for an excerpt already over EXCERPT_MAX_WORDS,
    and EXCERPT_ABSOLUTE_MAX_WORDS backstops genuine bulk, so leniency is safe.
    """
    folded = " ".join(text.split())
    count = 0
    for match in _SENTENCE_END.finditer(folded):
        head = folded[:match.end()]
        tokens = head.split()
        if not tokens:
            continue
        last = tokens[-1].lower().strip("\"'([{<")
        if last in _ABBREVIATIONS:
            continue
        # A single letter before the dot: an initial, or the tail of "U.S.".
        if len(last.rstrip(".!?")) <= 1:
            continue
        count += 1
    return max(count, 1)
```

`re` is already imported at the top of `gate.py`; do not add a second import.

- [ ] **Step 4: Run test to verify it passes**

Run: `../../.venv/Scripts/python -m pytest tests/test_gate_excerpt_length.py -q`
Expected: PASS, 18 tests.

- [ ] **Step 5: Commit**

```bash
git log --oneline -1   # must be your own last commit, or e6b9de3 for the first
git add gpu_agent/gate.py tests/test_gate_excerpt_length.py
git commit -F - <<'EOF'
feat(F127): word and sentence counters for the excerpt length cap

Counters only, no gate wiring yet. Sentence counting is deliberately
biased to under-count: abbreviations, initials and decimals do not end
a sentence, and the minimum returned is 1.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Q49JnexG5T4QhRBSawovVy
EOF
```

---

### Task 2: Wire the length check into `check_finding`

**Files:**
- Modify: `gpu_agent/gate.py` — the `for e in f.evidence:` loop inside `check_finding` (currently the F17 vintage-honesty loop, ~line 50)
- Test: `tests/test_gate_excerpt_length.py` (append)

**Interfaces:**
- Consumes: `_count_words`, `_count_sentences`, `EXCERPT_MAX_WORDS`, `EXCERPT_MAX_SENTENCES`, `EXCERPT_ABSOLUTE_MAX_WORDS` from Task 1.
- Produces: two new violation strings from `check_finding`. Task 3 asserts on them through the extraction path.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_gate_excerpt_length.py`. Build findings with the same helper shape the existing `tests/test_gate_finding.py::_base` uses — read that file and copy its constructor, then override the excerpt:

```python
from gpu_agent.gate import check_finding
from tests.test_gate_finding import _base


def _with_excerpt(text):
    f = _base()
    f.evidence[0].excerpt = text
    return f


def _long_errors(text):
    return [e for e in check_finding(_with_excerpt(text)) if "excerpt too long" in e]


def test_short_excerpt_passes():
    assert _long_errors("Gross margin was 54% in the quarter.") == []


def test_over_words_only_passes():
    # 60 words, one sentence: over the word limit, inside the sentence limit.
    text = " ".join(["word"] * 59) + " end."
    assert _count_words(text) == 60
    assert _count_sentences(text) == 1
    assert _long_errors(text) == []


def test_over_sentences_only_passes():
    # Four sentences, well under 50 words.
    text = "One here. Two here. Three here. Four here."
    assert _count_sentences(text) == 4
    assert _count_words(text) <= 50
    assert _long_errors(text) == []


def test_over_both_limits_is_rejected():
    # 60 words across four sentences.
    text = " ".join(["word"] * 14 + ["one."] + ["word"] * 14 + ["two."]
                    + ["word"] * 14 + ["three."] + ["word"] * 14 + ["four."])
    assert _count_words(text) == 60
    assert _count_sentences(text) == 4
    errs = _long_errors(text)
    assert errs == ["F1: excerpt too long (60 words > 50 and 4 sentences > 2)"]


def test_over_absolute_cap_is_rejected_even_as_one_sentence():
    text = " ".join(["word"] * 119) + " end."
    assert _count_words(text) == 120
    assert _count_sentences(text) == 1
    errs = _long_errors(text)
    assert errs == ["F1: excerpt too long (120 words > 100 absolute cap)"]


def test_over_both_and_over_absolute_reports_only_the_absolute_cap():
    text = " ".join(["word"] * 39 + ["one."] + ["word"] * 39 + ["two."]
                    + ["word"] * 39 + ["three."])
    assert _count_words(text) == 120
    assert _count_sentences(text) == 3
    assert _long_errors(text) == ["F1: excerpt too long (120 words > 100 absolute cap)"]


def test_every_committed_store_excerpt_survives_the_gate():
    """F127 must not be retroactively destructive: nothing already committed
    would be rejected by the rule this lane adds."""
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "store"
    checked = 0
    offenders = []
    for path in root.rglob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        for item in (data if isinstance(data, list) else [data]):
            if not isinstance(item, dict):
                continue
            for ev in item.get("evidence") or []:
                excerpt = ev.get("excerpt")
                if not isinstance(excerpt, str):
                    continue
                checked += 1
                words = _count_words(excerpt)
                sentences = _count_sentences(excerpt)
                if words > EXCERPT_ABSOLUTE_MAX_WORDS or (
                        words > EXCERPT_MAX_WORDS and sentences > EXCERPT_MAX_SENTENCES):
                    offenders.append(f"{path.name}: {words}w/{sentences}s")
    assert checked > 500, f"only {checked} excerpts scanned — store path wrong?"
    assert offenders == []
```

If `_base()` in `tests/test_gate_finding.py` builds a finding whose id is not `F1`, or whose
`evidence` list is empty, adjust the two expected strings and add an evidence entry rather than
editing that shared helper.

- [ ] **Step 2: Run test to verify it fails**

Run: `../../.venv/Scripts/python -m pytest tests/test_gate_excerpt_length.py -q`
Expected: FAIL on `test_over_both_limits_is_rejected` — `assert [] == ['F1: excerpt too long ...']`. The three "passes" tests and the store test should already be green (nothing rejects anything yet).

- [ ] **Step 3: Write minimal implementation**

In `check_finding`, inside the existing `for e in f.evidence:` loop, after the date checks and before the loop ends, add:

```python
        # F127 — excerpt length cap (posture doc §2, DECIDED 2026-08-22).
        words = _count_words(e.excerpt)
        if words > EXCERPT_ABSOLUTE_MAX_WORDS:
            errors.append(f"{f.id}: excerpt too long ({words} words > "
                          f"{EXCERPT_ABSOLUTE_MAX_WORDS} absolute cap)")
        else:
            sentences = _count_sentences(e.excerpt)
            if words > EXCERPT_MAX_WORDS and sentences > EXCERPT_MAX_SENTENCES:
                errors.append(f"{f.id}: excerpt too long ({words} words > "
                              f"{EXCERPT_MAX_WORDS} and {sentences} sentences > "
                              f"{EXCERPT_MAX_SENTENCES})")
```

The `else` is what makes an over-absolute excerpt report one message, not two.

- [ ] **Step 4: Run test to verify it passes**

Run: `../../.venv/Scripts/python -m pytest tests/test_gate_excerpt_length.py -q`
Expected: PASS, all tests.

- [ ] **Step 5: Commit**

```bash
git log --oneline -1
git add gpu_agent/gate.py tests/test_gate_excerpt_length.py
git commit -F - <<'EOF'
feat(F127): reject over-long excerpts in check_finding

An excerpt is rejected when it breaks both decided limits (over 50 words
AND over 2 sentences), or when it exceeds the 100-word absolute backstop.
Placed in the shared gate so every path an excerpt travels is covered, not
just extraction.

Includes a test asserting no excerpt already committed under store/ would
be rejected.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Q49JnexG5T4QhRBSawovVy
EOF
```

---

### Task 3: Prove the extraction path drops an over-long excerpt

**Files:**
- Test: `tests/test_extractor_v12.py` (append) — the file that already asserts on `"excerpt not found in source document"` at line 58

**Interfaces:**
- Consumes: the violations from Task 2.
- Produces: nothing.

- [ ] **Step 1: Write the failing test**

Read `tests/test_extractor_v12.py` and copy the fixture setup used by the test at line ~58 (the one asserting the verbatim violation). Add a sibling test that feeds a document whose text contains a long passage, and a draft quoting that whole passage verbatim, so the verbatim check passes and only the length check fires:

```python
def test_over_long_excerpt_is_dropped_like_an_invented_one():
    # Same shape as the verbatim-check test above, but the excerpt IS in the
    # document — it is simply too long: over 50 words across more than two
    # sentences.
    passage = " ".join(["word"] * 19 + ["one."] + ["word"] * 19 + ["two."]
                       + ["word"] * 19 + ["three."])
    # ... build doc whose text contains `passage`, and a draft whose evidence
    # excerpt is `passage`, using this file's existing helpers ...
    out = extract(...)
    assert out.findings == []
    assert any("excerpt too long" in v for v in out.dropped[0].violations)
    assert not any("excerpt not found" in v for v in out.dropped[0].violations)
```

Fill the elided lines from the neighbouring test's helpers — do not invent new fixture builders.

- [ ] **Step 2: Run test to verify it fails**

Run: `../../.venv/Scripts/python -m pytest tests/test_extractor_v12.py -q`
Expected: it should PASS immediately, because Task 2 already implemented the rule. That is fine — this task is a path-coverage proof, not a new behaviour. To confirm it is really testing the new code, temporarily raise `EXCERPT_MAX_WORDS` to 500 in `gpu_agent/gate.py`, re-run, watch this test go RED, then restore 50.

- [ ] **Step 3: Restore the constant**

Confirm `EXCERPT_MAX_WORDS = 50` in `gpu_agent/gate.py`.

- [ ] **Step 4: Run the full suite**

Run: `../../.venv/Scripts/python -m pytest -q`
Expected: the baseline 2720 passed / 6 skipped, plus the new tests. **If `tests/test_evals_baseline_pin.py` or any other pin test is RED, STOP.** Do not re-record a baseline, do not edit `fixtures/evals/baseline.json`; report which test and why.

- [ ] **Step 5: Verify F6 byte-untouched**

Run: `git diff --name-only main` and confirm no prompt file, no cli vocab glue, and no registry vocab data appears. Run `../../.venv/Scripts/python -m pytest tests/test_evals_baseline_pin.py -q` on its own and record the count.

- [ ] **Step 6: Commit**

```bash
git log --oneline -1
git add tests/test_extractor_v12.py
git commit -F - <<'EOF'
test(F127): extraction path drops an over-long excerpt

Sits beside the existing verbatim-check test: the excerpt is genuinely in
the document, so only the new length check fires.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Q49JnexG5T4QhRBSawovVy
EOF
```

---

### Task 4: Documentation

**Files:**
- Modify: `docs/fix-backlog.md` — the F127 entry at line ~1191
- Modify: `docs/publishing-posture.md` — §2, the "Length norm" bullet

**Interfaces:** none.

- [ ] **Step 1: Tick the backlog entry**

Change `- [ ] **F127 —` to `- [x] **F127 —` and append a STATUS line in the style the
neighbouring done items use (see F126 and F128): lane name, what was built, the AFK-defaults
named in `.superpowers/sdd/2026-08-25-f127-excerpt-length/QUESTIONS.md`.

- [ ] **Step 2: Add one line to posture §2**

Under the "Length norm" bullet's "Follow-up if approved" sub-bullet, add a plain-English line
noting the cap is now enforced in code, naming `gpu_agent/gate.py`, and saying plainly that
the rule rejects an excerpt only when it is both over 50 words and over two sentences (with
a 100-word absolute ceiling). Do NOT alter the `[DECIDED …]` clause text itself — F126 set
that precedent: update the bracketed follow-up note, leave the decision wording alone.

- [ ] **Step 3: Verify no test pins these doc files**

Run: `../../.venv/Scripts/python -m pytest -q`
Expected: same counts as Task 3 Step 4.

- [ ] **Step 4: Commit**

```bash
git log --oneline -1
git add docs/fix-backlog.md docs/publishing-posture.md docs/superpowers/specs/2026-08-25-f127-excerpt-length-design.md docs/superpowers/plans/2026-08-25-f127-excerpt-length.md
git commit -F - <<'EOF'
docs(F127): tick the excerpt-length item and record the enforced cap

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Q49JnexG5T4QhRBSawovVy
EOF
```

---

### Task 5: Code review, then handoff

- [ ] **Step 1: Dispatch a reviewer** via `superpowers:requesting-code-review` against the full branch diff.
- [ ] **Step 2: Work the feedback** via `superpowers:receiving-code-review` — verify each point technically before acting; push back where the reviewer is wrong.
- [ ] **Step 3: Re-run the full suite** and re-confirm the F6 pin.
- [ ] **Step 4: Write** `.superpowers/handoffs/f127-excerpt-length-DONE.md` using
  `.superpowers/handoffs/f124-footer-disclaimer-DONE.md` in the root checkout as the template.
  `.superpowers/` is gitignored, so this needs `git add -f`.
- [ ] **Step 5: Commit the handoff.** Do NOT merge to main. Do NOT push.
