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
