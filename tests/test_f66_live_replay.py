"""F66 Task 3: the frozen live-artifact replay.

The measured baseline from spec section 4, pinned. Fixtures under
tests/fixtures/f66/ are COPIES of three live story artifacts (2026-07-25/26/27)
and the 37 findings they cite -- committed into the repo on purpose, so the suite
never depends on mutable live `store/` state.

The second test is the one that earns its keep: it pins WHY the rounding
tolerance exists. Without it the audit raises a false alarm on a perfectly good
sentence, and a false alarm here costs a day's story.
"""
import pathlib

from gpu_agent.citation_audit import (FindingsReader, allowed_tokens,
                                      claims_from_story, run_audit)
from gpu_agent.narrator.store import StoryStore
from gpu_agent.numeric_tokens import numeric_tokens

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "f66"
CAT = "chips.merchant-gpu"
DAYS = ["2026-07-25", "2026-07-26", "2026-07-27"]


def test_fixtures_are_present_and_self_contained():
    """Every finding the three stories cite is committed alongside them -- an
    unresolved id here would make the clean baseline below meaningless."""
    reader = FindingsReader(FIXTURES / "findings")
    seen = 0
    for day in DAYS:
        art = StoryStore(FIXTURES).read(CAT, day)
        assert art is not None, f"missing fixture story for {day}"
        for claim in claims_from_story(art):
            for fid in claim.findingIds:
                assert reader.get(fid) is not None, f"{day}: unresolved {fid}"
                seen += 1
    assert seen > 0
    assert len(list((FIXTURES / "findings").glob("*.json"))) == 37


def test_three_live_days_audit_clean():
    """80 numeric tokens across 2026-07-25/26/27; zero flags under rounding tolerance.

    The single exact-match false positive (7.09 vs 7.0931) is the reason
    `supported` exists -- if this test ever goes red, either the matcher regressed
    or a real citation defect entered the fixtures.
    """
    total_tokens = 0
    for day in DAYS:
        art = run_audit(FIXTURES, CAT, day)
        assert art.summary["flagged"] == 0, f"{day}: {art.claims}"
        assert art.summary["claimsAudited"] > 0
        story = StoryStore(FIXTURES).read(CAT, day)
        for claim in claims_from_story(story):
            total_tokens += len(numeric_tokens(claim.text))
    # Guards the tokenizer too: a tokenizer change moves this number.
    assert total_tokens == 80


def test_exact_matching_would_have_flagged_the_rounded_token():
    """Same fixtures, exact set membership instead of `supported`: exactly one
    flag, "7.09", on 2026-07-26 scene 2. Story says "7.09 trillion won"; finding
    www-ad-hoc-news-de-94ca546c-2026-07-1 says "7.0931 trillion won". This is the
    false alarm the tolerance is for, and this test is what stops someone
    "simplifying" `supported` back to `in`.
    """
    reader = FindingsReader(FIXTURES / "findings")
    exact_flags = []
    for day in DAYS:
        art = StoryStore(FIXTURES).read(CAT, day)
        for claim in claims_from_story(art):
            if not claim.findingIds:
                continue
            pool, _unresolved = allowed_tokens(claim, reader)
            for token in sorted(numeric_tokens(claim.text)):
                if token not in pool:           # the wiki gate's exact rule
                    exact_flags.append((day, claim.claimKey, token))
    assert exact_flags == [("2026-07-26", "scene:2", "7.09")]
