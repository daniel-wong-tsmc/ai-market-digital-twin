"""tests/test_narrator_bullets_gate.py — F114 Task 2: gate checks for narrator bullets.

`gate_narrator` gains mechanical checks over `answer.bullets`: presence and
count, per-bullet word budget, a required digit, a banned-opener-word rule,
the existing banned-word/outlet-string sweep reused over bullet text, and
`claimFindingIds` membership against `inputs["findings"]`. `bullets` stays
legal as `None` at the schema layer (pre-F114 v1 artifacts must keep
validating), but the narrator prompt now demands them, so a `None` answer is
still a gate failure here.
"""
import pytest

from gpu_agent.narrator.gate import gate_narrator
from gpu_agent.narrator.schema import StoryBullet
from tests.narrator.test_gate import _inp, _ok


def _bullets(overrides=None):
    b = [
        {"text": "SK Hynix shifted HBM output on June 24, 2026, citing a "
                 "one-year lag before new capacity comes online.",
         "claimFindingIds": ["f-1"]},
        {"text": "Oracle raised capital spending 162% versus last year, per "
                 "its June 10 filing.",
         "claimFindingIds": ["f-2"]},
        {"text": "Buyers now face both a memory squeeze and a capex surge, "
                 "with SK Hynix and Oracle both moving in June 2026.",
         "claimFindingIds": ["f-1", "f-2"]},
    ]
    for i, kw in (overrides or {}).items():
        b[i] = {**b[i], **kw}
    return [StoryBullet.model_validate(x) for x in b]


def _with_bullets(tmp_path, overrides=None):
    a = _ok(tmp_path)
    a.bullets = _bullets(overrides)
    return a


def test_bullets_none_is_rejected(tmp_path):
    a = _ok(tmp_path)
    a.bullets = None
    violations = gate_narrator(a, _inp(tmp_path))
    assert "narrator answer has no bullets" in violations


def test_all_clean_bullets_pass(tmp_path):
    a = _with_bullets(tmp_path)
    assert gate_narrator(a, _inp(tmp_path)) == []


def test_wrong_bullet_count_rejected(tmp_path):
    a = _with_bullets(tmp_path)
    a.bullets = a.bullets[:2]
    violations = gate_narrator(a, _inp(tmp_path))
    assert any("exactly 3" in v and "2" in v for v in violations)


def test_bullet_over_28_words_rejected(tmp_path):
    long_text = "word " * 29 + "in 2026."
    a = _with_bullets(tmp_path, {0: {"text": long_text.strip()}})
    violations = gate_narrator(a, _inp(tmp_path))
    assert any("28 words" in v for v in violations)


def test_bullet_without_digit_rejected(tmp_path):
    a = _with_bullets(tmp_path, {
        0: {"text": "SK Hynix shifted HBM output, citing a supply lag "
                    "before new capacity comes online."}})
    violations = gate_narrator(a, _inp(tmp_path))
    assert any("digit" in v for v in violations)


@pytest.mark.parametrize("opener", ["They", "It", "These", "Those", "That"])
def test_bullet_banned_opener_rejected(tmp_path, opener):
    a = _with_bullets(tmp_path, {
        0: {"text": f"{opener} shifted HBM output on June 24, 2026, citing "
                    f"a one-year capacity lag."}})
    violations = gate_narrator(a, _inp(tmp_path))
    assert any(opener in v for v in violations)


@pytest.mark.parametrize("opener", ["It's", "They've", "That's", "They,"])
def test_bullet_banned_opener_contraction_rejected(tmp_path, opener):
    a = _with_bullets(tmp_path, {
        0: {"text": f"{opener} shifted HBM output on June 24, 2026, citing "
                    f"a one-year capacity lag."}})
    violations = gate_narrator(a, _inp(tmp_path))
    assert any("must not open with" in v for v in violations)


def test_bullet_lowercase_opener_not_rejected(tmp_path):
    # Case-sensitive: a lowercase "they" mid-sentence-style opener (e.g. the
    # bullet legitimately starts with a lowercase word) must not trip the
    # banned-opener rule -- only the five capitalized forms are banned.
    a = _with_bullets(tmp_path, {
        0: {"text": "they shifted HBM output on June 24, 2026, citing a "
                    "one-year capacity lag."}})
    violations = gate_narrator(a, _inp(tmp_path))
    assert not any("must not open with" in v for v in violations)


def test_bullet_banned_word_rejected(tmp_path):
    a = _with_bullets(tmp_path, {
        0: {"text": "SK Hynix supply momentum shifted output in June 2026."}})
    violations = gate_narrator(a, _inp(tmp_path))
    assert any("momentum" in v for v in violations)


def test_bullet_empty_claim_ids_rejected(tmp_path):
    a = _with_bullets(tmp_path, {0: {"claimFindingIds": []}})
    violations = gate_narrator(a, _inp(tmp_path))
    assert any("claimFindingIds" in v and "empty" in v for v in violations)


def test_bullet_unknown_finding_id_rejected(tmp_path):
    a = _with_bullets(tmp_path, {0: {"claimFindingIds": ["f-ghost"]}})
    violations = gate_narrator(a, _inp(tmp_path))
    assert any("f-ghost" in v for v in violations)
