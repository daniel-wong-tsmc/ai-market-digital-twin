import json, re
from pathlib import Path
from gpu_agent.narrator.pin import compute_narrator_prompt_hash

PIN = Path("fixtures/narrator/prompt-pin.json")
HASH_INPUT = Path("fixtures/narrator/hash-input.json")


def test_narrator_prompt_hash_matches_pin():
    pin = json.loads(PIN.read_text(encoding="utf-8"))
    got = compute_narrator_prompt_hash(
        json.loads(HASH_INPUT.read_text(encoding="utf-8")))
    assert got == pin["promptHash"], (
        "Narrator prompt changed. If DELIBERATE, re-record via "
        "scripts/narrator-pin-record.py and commit the new pin with the "
        "prompt change in the SAME commit.")


def test_pin_is_deliberate():
    pin = json.loads(PIN.read_text(encoding="utf-8"))
    assert re.fullmatch(r"[0-9a-f]{64}", pin["promptHash"])
    assert pin["schemaVersion"] == 1


def test_hash_input_fixture_exists():
    assert HASH_INPUT.exists()


def test_bundle_deterministic():
    """Same fixture inputs -> byte-identical emitted bundle, twice in a row."""
    import gpu_agent.narrator.pin as pin_mod
    inputs = json.loads(HASH_INPUT.read_text(encoding="utf-8"))
    bundle_1 = pin_mod._canonical_json(pin_mod._emit(inputs))
    bundle_2 = pin_mod._canonical_json(pin_mod._emit(inputs))
    assert bundle_1 == bundle_2
