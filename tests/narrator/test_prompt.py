import datetime as dt
from gpu_agent.narrator.inputs import build_narrator_inputs
from gpu_agent.narrator.prompt import (build_narrator_system,
                                       build_narrator_user_prompt,
                                       emit_narrator_bundle)
from tests.narrator.test_inputs import CAT
from tests.dashboard.test_story_model import _store


def test_system_carries_editorial_rules():
    s = build_narrator_system()
    # NOTE (controller instruction): the brief's original test asserted bare
    # "2" and "5" substrings, which any prose containing a digit satisfies.
    # Asserting the actual scene-count rule wording keeps this test meaningful.
    for phrase in ["why isn", "catching up", "between 2 and 5 scenes",
                   "forward-looking", "momentum", "no tool"]:
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
