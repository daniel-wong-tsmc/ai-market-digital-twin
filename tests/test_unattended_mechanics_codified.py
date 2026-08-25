"""F128 - rot-lint over the codified unattended-run mechanics.

The user ruled on 2026-08-22 that four standing per-cycle deviations are accepted
practice. This lint keeps them written down: without it, a later prose edit can
delete a clause and cycles silently start re-flagging accepted practice as a
deviation again. Pure stdlib, no product imports (the compliance-matrix lint's
pattern) - it pins ANCHORS and cross-references, never whole paragraphs, so
ordinary prose editing stays possible.
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
SKILL = ROOT / ".claude" / "skills" / "run-cycle" / "SKILL.md"
GATHER = ROOT / ".claude" / "skills" / "gather-category" / "SKILL.md"
AGENT = ROOT / ".claude" / "agents" / "web-gatherer.md"

SECTION_HEADER = "## Unattended-run mechanics"


def _text(path):
    return path.read_text(encoding="utf-8")


def _section(text, header):
    """The lines from `header` up to (not including) the next top-level `## `."""
    lines = text.splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith(header))
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")),
               len(lines))
    return "\n".join(lines[start:end])


def _procedure_text():
    return _section(_text(SKILL), "## Procedure")


def test_mechanics_section_exists_and_sits_outside_procedure():
    text = _text(SKILL)
    assert SECTION_HEADER in text, (
        f"{SKILL} lost the '{SECTION_HEADER}' section - the four accepted-practice "
        "mechanics have no home and cycles will re-flag them as deviations (F128)")
    assert text.index(SECTION_HEADER) < text.index("## Procedure"), (
        "the mechanics section must sit BEFORE '## Procedure': the F83 parser bounds "
        "the Procedure section at the next '## ' header, so a section inside it would "
        "silently truncate the pinned step list")


def test_procedure_section_contains_no_top_level_header():
    """Tripwire for the placement rule above (F83 parser guard)."""
    body = _procedure_text().splitlines()[1:]
    assert not [l for l in body if l.startswith("## ")], (
        "a '## ' header appeared inside '## Procedure' - this truncates the F83 "
        "pinned step list silently")


def test_all_four_mechanics_are_named():
    sec = _section(_text(SKILL), SECTION_HEADER)
    for anchor in ("web-gatherer", "byte-exact", "rejoin", "above-fold", "F67",
                   "answer file"):
        assert anchor in sec, f"mechanics section does not mention {anchor!r} (F128)"


def test_brain_dispatch_keeps_the_no_reach_property():
    sec = _section(_text(SKILL), SECTION_HEADER)
    for forbidden in ("WebSearch", "WebFetch", "Bash"):
        assert forbidden in sec, (
            f"the brain-dispatch clause must name {forbidden} as forbidden - "
            "Read-own-prompt + one-Write only preserves the no-reach property if the "
            "tool set excludes the reaching tools (F128)")
    assert re.search(r"exactly ONE Write|exactly one Write", sec), (
        "the brain-dispatch clause must state the one-Write cap verbatim (F128)")


def test_gatherer_dispatch_names_the_restricted_agent_type():
    for path in (SKILL, GATHER):
        text = _text(path)
        assert "subagent_type: web-gatherer" in text or '"web-gatherer"' in text, (
            f"{path} does not name the restricted web-gatherer agent type - the F88 "
            "wall is back to being merely instructed (F128)")


def test_web_gatherer_agent_definition_holds_exactly_the_walled_tool_set():
    line = next(l for l in _text(AGENT).splitlines() if l.startswith("tools:"))
    assert line.strip() == "tools: Read, Write, WebSearch, WebFetch", (
        f"web-gatherer tool set drifted: {line!r} - the F88 injection wall requires "
        "exactly Read, Write, WebSearch, WebFetch (no Bash, ever)")


def test_step_six_carries_the_deviation_rule():
    step6 = _section(_procedure_text(), "### 6.")
    assert "deviation" in step6.lower(), (
        "Step 6 (finalize the cycle log) carries no deviation guidance - this is why "
        "every cycle re-flagged accepted practice (F128)")
    assert "NOT deviations" in step6 or "not deviations" in step6, (
        "Step 6 must say explicitly that the four codified mechanics are NOT "
        "deviations, or cycles keep logging them (F128)")


def test_tool_less_absolutes_survive_only_where_the_ruling_allows():
    """extraction stays genuinely tool-less; the 7(d2) contrast note still refers to
    the tool-less brain pattern. Every OTHER seam must point at the mechanics section
    instead of asserting an absolute the harness cannot honour."""
    hits = [l for l in _procedure_text().splitlines()
            if re.search(r"tool-?less", l, re.I)]
    for line in hits:
        assert ("Extraction" in line or "extraction" in line
                or "NOT the tool-less" in line), (
            f"stale tool-less absolute still prescribed: {line.strip()!r} - "
            "judge/thesis/implication/narrator dispatch Read-own-prompt + one Write "
            "(F128 mechanic 1)")
