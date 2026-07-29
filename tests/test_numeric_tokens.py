"""F66 Task 1: the shared numeric tokenizer + the rounding-tolerant matcher.

`numeric_tokens` and `value_renderings` are moved verbatim out of the F14 wiki
enrichment gate (`gpu_agent/wiki/ingest.py`), which keeps EXACT token matching.
`supported` is new and is used only by the citation audit: story prose is
written for a non-technical reader and rounds by policy, so "7.09" must be
supported by a finding that says "7.0931" without laundering a wrong number.
"""
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
