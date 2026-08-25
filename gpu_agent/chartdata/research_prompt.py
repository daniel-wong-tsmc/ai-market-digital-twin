"""gpu_agent/chartdata/research_prompt.py -- F113 Task 3: the chart
researcher's prompt.

This prompt is NEW and deliberately UNPINNED (spec §3): its quality
mechanism is Task 4's deterministic verifier -- every point it returns
gets re-checked against its own cited URL -- not a fixed-text pin the way
the extraction/judgment/thesis/narrator prompts are. It must not import
from, resemble by copying, or modify any of those pinned prompts, and it
is never added to a pin fixture.

The agent this prompt is handed to is a tool-USING research agent (the
same dispatch pattern as `gather`, not a tool-less brain) -- it is
expected to actually search the web and read pages, not recall numbers
from memory.
"""
from __future__ import annotations

import json
from pathlib import Path

from gpu_agent.fetch_policy import (
    KIND_BLOCKS_READERS, KIND_OBJECTION, load_do_not_fetch)

_NO_SERIES_TOKEN = "NO-SERIES-FOUND"

# The desk's registered licensed publishers (`registry/licensed-sources.json`,
# the same file the gather step's webreach path consults). Read from disk at
# prompt-build time rather than hard-coded, so the list the researcher is
# warned about and the list the desk treats as licensed cannot drift apart.
_LICENSED_REGISTRY = Path("registry/licensed-sources.json")


def _licensed_domains() -> list[str]:
    """Registered licensed publisher domains, or [] if the registry is not
    where the cwd expects it (a worktree, an odd cwd, a stripped-down
    machine). Missing means a generic warning, never a crashed emit."""
    try:
        data = json.loads(_LICENSED_REGISTRY.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    domains = data.get("domains") if isinstance(data, dict) else None
    if not isinstance(domains, list):
        return []
    return [d for d in domains if isinstance(d, str) and d.strip()]


def _do_not_fetch_lists() -> tuple[list[str], list[str]]:
    """(publishers who objected, sites that turn the plain reader away), read
    from `registry/do-not-fetch.json` at prompt-build time. Missing means two
    empty lists and a generic warning, never a crashed emit -- the same rule
    the licensed registry follows, and the same reason: this builder runs from
    worktrees and odd working directories too."""
    reg = load_do_not_fetch()
    return reg.domains(KIND_OBJECTION), reg.domains(KIND_BLOCKS_READERS)


def _listed(domains: list[str]) -> str:
    return "\n".join(f"     - {d}" for d in domains)


def _reachability_rule(licensed: list[str], objections: list[str],
                       blocked: list[str]) -> str:
    """Rule 8: the verifier re-reads every cited page with a plain automated
    reader, so a publisher that turns such readers away can never verify.

    Three live cycles (2026-08-10/11) lost every candidate to gaps this rule
    and rule 9 now close. The 2026-08-19 cycle then lost one to a publisher on
    no list at all, whose page opened cleanly for the researcher's own reader
    three times while the verifier got 403 five times (F117) -- so the rule now
    says plainly that checking a page yourself proves nothing, and names both
    do-not-fetch lists as well as the licensed one.
    """
    base = (
        "8. After you answer, a machine re-opens every URL you cite with a\n"
        "   plain automated reader (no login, no cookies, no browser) and\n"
        "   looks for each number on the page. That machine is a DIFFERENT\n"
        "   reader from the one you use, with different access: a page that\n"
        "   opens cleanly for you can still turn it away, so checking a page\n"
        "   yourself proves nothing about whether its numbers will verify.\n"
        "   A site that turns automated readers away (a paywall, a login\n"
        "   wall, a \"403 Forbidden\" or \"access denied\" page, a bot check)\n"
        "   can NEVER pass that verification, however real its numbers are,\n"
        "   and the whole series is rejected. Prefer a publisher whose page\n"
        "   opens plainly."
    )
    if licensed:
        base += (
            "\n   Known licensed publishers that fail this check -- do not cite\n"
            "   them as a point's source:\n"
            f"{_listed(licensed)}\n"
            "   If the only home for a number is one of these, treat it as\n"
            "   unavailable."
        )
    if objections:
        base += (
            "\n   Publishers who have asked us not to use their material at all.\n"
            "   NEVER cite these, whatever they publish and however well their\n"
            "   pages open:\n"
            f"{_listed(objections)}"
        )
    if blocked:
        base += (
            "\n   Sites already known to turn the plain reader away. Treat\n"
            "   anything they publish as unavailable, however well the page\n"
            "   opens for you:\n"
            f"{_listed(blocked)}"
        )
    return base


_RULES = f"""\
Rules for the series you hand back (all of them, no exceptions):

1. Only PUBLISHED numbers count. A figure a company, analyst firm, or
   news outlet has actually put in print. Never invent a number, and
   never round or interpolate one to fill a gap.
2. Every point needs the exact URL of the page it came from. A point
   with no source URL is not a point -- leave it out.
3. Give at least 3 points, OR, if the honest shape of this story is a
   comparison between two things (for example supply vs. demand), give a
   clearly labelled comparison pair instead. Two unrelated numbers are
   not a pair and are not enough on their own.
4. Never present an estimate, a forecast, a rumor, or your own guess as
   if it were a published fact. If a source hedges ("expected to",
   "could reach"), that is not a published number.
5. Every point must come from the SAME site. The chart is captioned as
   resting on one source, so a series stitched together from several
   sites would make that caption untrue and will be rejected whole. If
   the numbers you want live on two different sites, follow one of them
   and drop the other.
6. The source must be a page anyone can open on the public web. Never a
   local address, an internal or company-private host, or anything only
   reachable from inside a network -- the reader is handed this URL as a
   link and has to be able to read it.
7. If you cannot find a real published series that honestly supports or
   contextualizes this story, say so. Give up honestly: reply with
   exactly the single line {_NO_SERIES_TOKEN} and nothing else. That is
   a correct, complete answer -- a chart that overstates what we know is
   worse than no chart at all.
{{reachability_rule}}
9. Every point's value is a BARE NUMBER in the stated unit -- 35.6, not
   "$35.6 billion"; 80, not "about 80%". The unit lives once, in the
   `unit` field; the value carries no currency sign, no words, no unit,
   no date. A value with words in it is thrown out unread. If the source
   only gives a hedge or a range ("close to 80%", "below 60%", "in the
   80% range", "over $1.3 trillion"), that is NOT a number you may use:
   do not turn it into one. Leave that point out, and if the series
   cannot stand without it, reply {_NO_SERIES_TOKEN}.
"""


def _findings_block(findings: list[dict]) -> str:
    if not findings:
        return "(No findings are attached to this story beyond the text above.)"
    lines = []
    for f in findings:
        statement = (f.get("statement") or "").strip()
        url = f.get("url") or ""
        if statement and url:
            lines.append(f"- {statement} (source: {url})")
        elif statement:
            lines.append(f"- {statement}")
        elif url:
            lines.append(f"- source: {url}")
    return "\n".join(lines) if lines else "(No findings are attached to this story beyond the text above.)"


def build_research_prompt(bullet: dict, findings: list[dict]) -> str:
    """The prompt handed to a tool-USING research agent for ONE chartless
    dashboard bullet: today's story text for this bullet, the findings
    already cited for it (statement + URL, for context and as a starting
    point -- not the only sources the agent may use), and the rules a
    returned series must follow (spec §3, verbatim in substance: published
    numbers only, a URL per point, a real density floor or a labelled
    comparison pair, no estimates presented as fact, and an honest give-up
    token when nothing qualifies).

    Four of the rules exist because the verifier or the schema enforces
    them: every point must come from one site; that site must be publicly
    reachable; it must also answer a plain automated re-fetch (rule 8,
    which names three lists -- the registered licensed publishers, the
    publishers who asked not to be used, and the sites already known to
    turn the plain reader away -- and states the thing no list can cover:
    the re-fetch is done by a DIFFERENT reader, so the researcher checking
    a page itself proves nothing); and `value`
    must be a bare number, never prose or a hedge (rule 9 -- the same
    cycles lost the rest to "$35.6 billion" and "close to 80%"). A gate
    that rejects something its own prompt never asked for just burns
    dispatches producing candidates that are thrown away, so the
    instruction and the enforcement are stated together and tested
    together (`tests/test_chart_research.py`).
    """
    bullet_text = (bullet.get("text") or "").strip()
    findings_block = _findings_block(findings)
    objections, blocked = _do_not_fetch_lists()
    rules = _RULES.replace("{reachability_rule}",
                           _reachability_rule(_licensed_domains(), objections,
                                              blocked))

    return f"""\
You are researching a chart for today's GPU market dashboard.

Today's bullet:
{bullet_text}

What we already have on this (for context -- you are not limited to these):
{findings_block}

Your job: search the web for a real, published, numeric series that
directly supports or usefully contextualizes this bullet, and report it
back as the candidate series requested below.

{rules}

If you find a usable series, describe it as:
- seriesName: a short plain-English name for what the numbers measure
- unit: the plain-English unit (e.g. "US$ billions", "units shipped")
- form: one of columns, bars, or line
- sourceName: the publication or organization that published the numbers
- points: a list of {{label, value, sourceUrl, publishedAt}} -- one entry
  per data point, each with its own source URL; `value` is a bare number
  (e.g. 35.6, not "$35.6 billion" -- see rule 9), `publishedAt` an
  ISO date (YYYY-MM-DD)
- pair: true only for a labelled two-series comparison (e.g. supply vs.
  demand); false otherwise
- notes: anything a reader should know about how honest or complete this
  series is

If nothing published and honest supports this bullet, reply with exactly:
{_NO_SERIES_TOKEN}
"""
