"""F127 — the excerpt length cap.

Posture doc §2, DECIDED 2026-08-22: an excerpt is "at most two sentences or about
50 words". The "or" is read literally — an excerpt is rejected only when it breaks
BOTH limits — with a 100-word absolute backstop so a run-on cannot walk past the
gate by counting as one sentence.
"""
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
    ("First one. Second one. Third one.", 3),
    ("Is it? It is! Indeed it is.", 3),
    ("Trailing space after the full stop. ", 1),
    ("Ellipsis is one terminator... still one sentence", 1),
])
def test_count_sentences_basics(text, expected):
    assert _count_sentences(text) == expected


@pytest.mark.parametrize("text", [
    "The U.S. government export control cut margins that year.",
    "Revenue rose to $6.7B in the quarter, up from $4.1B a year earlier.",
    "Gross margin was 54.3% versus 40.0% a year earlier.",
    "Advanced Micro Devices, Inc. reported a record quarter.",
    "Shipments rose vs. the prior year for No. 1 supplier Foo Corp.",
    "Analysts at Foo Co. said e.g. HBM4 yields improved.",
])
def test_abbreviations_and_decimals_do_not_end_sentences(text):
    assert _count_sentences(text) == 1


@pytest.mark.parametrize("text,expected", [
    # Quarter and half-year labels are abbreviations, not sentence ends. Getting
    # these wrong over-counts, which is the unsafe direction: it rejects real work.
    ("Q3. was strong. Q4. was better.", 2),
    ("H1. shipments rose. H2. should follow.", 2),
    ("FY26. guidance was raised again this week.", 1),
    ("Revenue in 1H. tracked ahead of plan.", 1),
])
def test_quarter_labels_do_not_end_sentences(text, expected):
    assert _count_sentences(text) == expected


@pytest.mark.parametrize("text,expected", [
    # Dotted acronyms and initials. These are the shape of "U.S." but are not on
    # (and cannot all be on) the abbreviation list.
    ("A.I. spending rose. Chips followed.", 2),
    ("Ph.D. hires rose. Attrition fell.", 2),
    ("R.O.E. improved. Debt fell.", 2),
    ("The co-founder, J.H. Lee, spoke. He left.", 2),
    # Numbered labels.
    ("Section 2.1. covers this. See below.", 2),
    # Abbreviations that are not on the list.
    ("The Fed. raised rates. Chips fell.", 2),
    ("Shipments to Calif. rose. Texas fell.", 2),
    ("Rev. was up. Costs held.", 2),
    ("Volume rose 3 mn. units. Prices held.", 2),
])
def test_dotted_acronyms_and_unlisted_abbreviations_do_not_over_count(text, expected):
    """Over-counting is the UNSAFE direction — it rejects honest work.

    Found in code review: every one of these counted 3 instead of 2, and a
    realistic 58-word two-sentence passage opening on "Ph.D." was rejected by the
    real gate. Fixed by requiring a real sentence end to be followed by a capital
    (or end of text), and by never treating a token with an internal period as a
    sentence end.
    """
    assert _count_sentences(text) == expected


def test_the_review_false_rejection_passes_the_gate():
    """The exact passage code review used to demonstrate the bug: 58 words, two
    sentences, ordinary financial prose. It must NOT be rejected."""
    text = (
        "Ph.D. hires rose 12% year over year as the company expanded its research "
        "organization across three continents, adding engineering staff in Santa "
        "Clara, Austin, Bangalore and Munich during the quarter in order to support "
        "the next generation of accelerator design work that is now underway across "
        "the portfolio. Rev. per employee held roughly flat against the prior year."
    )
    assert _count_words(text) == 58
    assert _count_sentences(text) == 2
    assert excerpt_length_violations("f", text) == []


@pytest.mark.parametrize("text,counted,really", [
    # Terminator inside a closing quote or bracket.
    ("He said 'it is done.' Then he left.", 1, 2),
    ('She said "we are sold out." Demand held.', 1, 2),
    # Sentence ending on a single-letter word. The same rule is what makes the
    # trailing "S." of "U.S." harmless, so the two cannot be separated cheaply.
    ("The answer is A. The next is B.", 1, 2),
    ("They ship Model X. Margins improved.", 1, 2),
    # Sentence ending on a quarter label.
    ("Shipments rose in Q3. Margins held.", 1, 2),
])
def test_known_undercounts_are_all_in_the_safe_direction(text, counted, really):
    """These are wrong on purpose.

    Under-counting makes a long excerpt more likely to PASS; over-counting would
    reject honest work. Every known inaccuracy in _count_sentences errs the first
    way. If a future edit makes one of these accurate, that is fine — but re-run
    the store audit first.
    """
    assert counted < really
    assert _count_sentences(text) == counted


def test_a_bare_year_still_ends_a_sentence():
    """The period-label regex must not swallow "in 2026." — it is anchored to the
    FY/CY/Q/H forms precisely so bare years keep working."""
    assert _count_sentences("Revenue reached a record in 2026. Margins held.") == 2


def test_real_store_excerpt_is_one_sentence():
    # Verbatim from store/findings/ir-amd-com-cfa508a5-2026-08-3.json: 70 words in
    # a single sentence. The longest excerpt ever committed to this store.
    excerpt = (
        "Gross margin for the three months ended June 27, 2026 was 54% compared to "
        "gross margin of 40% for the prior year period, a 14% increase primarily "
        "driven by the absence of inventory and related charges associated with the "
        "U.S. government export control on AMD Instinct MI308 Data Center GPU "
        "products that was recorded in the prior year period and a favorable "
        "product mix, including higher Data Center segment revenue."
    )
    assert _count_words(excerpt) == 70
    assert _count_sentences(excerpt) == 1


# --- the gate itself -------------------------------------------------------

from gpu_agent.gate import check_finding, excerpt_length_violations   # noqa: E402
from tests.test_gate_finding import _base         # noqa: E402


def _sentences(count, words_each):
    """`count` capitalised sentences of `words_each` words each.

    Capitalised because a sentence end is only counted when a capital follows it —
    that rule is what stops an unlisted abbreviation being read as a full stop.
    """
    return " ".join("Word " + " ".join(["word"] * (words_each - 2)) + " end."
                    for _ in range(count))


def _long_errors(text):
    """Violations mentioning excerpt length, for a finding carrying `text`."""
    f = _base(evidence=[{"source": "S", "url": "u", "date": "2026-05-01",
                         "excerpt": text, "tier": "primary"}])
    return [e for e in check_finding(f) if "excerpt too long" in e]


def test_short_excerpt_passes():
    assert _long_errors("Gross margin was 54% in the quarter.") == []


def test_over_words_only_passes():
    # 60 words in one sentence: over the word limit, inside the sentence limit.
    text = " ".join(["word"] * 59) + " end."
    assert _count_words(text) == 60
    assert _count_sentences(text) == 1
    assert _long_errors(text) == []


def test_over_sentences_only_passes():
    # Four sentences, well under 50 words.
    text = "One here. Two here. Three here. Four here."
    assert _count_sentences(text) == 4
    assert _count_words(text) <= EXCERPT_MAX_WORDS
    assert _long_errors(text) == []


def test_over_both_limits_is_rejected():
    text = _sentences(4, 15)
    assert _count_words(text) == 60
    assert _count_sentences(text) == 4
    assert _long_errors(text) == ["f: excerpt too long (60 words > 50 and 4 sentences > 2)"]


def test_over_absolute_cap_is_rejected_even_as_one_sentence():
    text = " ".join(["word"] * 119) + " end."
    assert _count_words(text) == 120
    assert _count_sentences(text) == 1
    assert _long_errors(text) == ["f: excerpt too long (120 words > 100 absolute cap)"]


def test_over_both_and_over_absolute_reports_only_the_absolute_cap():
    text = _sentences(3, 40)
    assert _count_words(text) == 120
    assert _count_sentences(text) == 3
    assert _long_errors(text) == ["f: excerpt too long (120 words > 100 absolute cap)"]


def test_every_committed_store_excerpt_survives_the_gate():
    """F127 must not be retroactively destructive: nothing already committed
    under store/ may be rejected by the rule this lane adds."""
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "store"
    checked = 0
    offenders = []
    for path in sorted(root.rglob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            continue
        for item in (data if isinstance(data, list) else [data]):
            if not isinstance(item, dict):
                continue
            for ev in item.get("evidence") or []:
                if not isinstance(ev, dict):
                    continue
                excerpt = ev.get("excerpt")
                if not isinstance(excerpt, str):
                    continue
                checked += 1
                # The real rule, not a second copy of it that could drift.
                if excerpt_length_violations(path.name, excerpt):
                    offenders.append(f"{path.name}: {_count_words(excerpt)}w/"
                                     f"{_count_sentences(excerpt)}s")
    assert checked > 500, f"only {checked} excerpts scanned - store path wrong?"
    assert offenders == []
