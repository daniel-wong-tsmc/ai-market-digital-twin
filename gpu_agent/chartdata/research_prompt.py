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

_NO_SERIES_TOKEN = "NO-SERIES-FOUND"

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
5. If you cannot find a real published series that honestly supports or
   contextualizes this story, say so. Give up honestly: reply with
   exactly the single line {_NO_SERIES_TOKEN} and nothing else. That is
   a correct, complete answer -- a chart that overstates what we know is
   worse than no chart at all.
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
    """
    bullet_text = (bullet.get("text") or "").strip()
    findings_block = _findings_block(findings)

    return f"""\
You are researching a chart for today's GPU market dashboard.

Today's bullet:
{bullet_text}

What we already have on this (for context -- you are not limited to these):
{findings_block}

Your job: search the web for a real, published, numeric series that
directly supports or usefully contextualizes this bullet, and report it
back as the candidate series requested below.

{_RULES}

If you find a usable series, describe it as:
- seriesName: a short plain-English name for what the numbers measure
- unit: the plain-English unit (e.g. "US$ billions", "units shipped")
- form: one of columns, bars, or line
- sourceName: the publication or organization that published the numbers
- points: a list of {{label, value, sourceUrl, publishedAt}} -- one entry
  per data point, each with its own source URL
- pair: true only for a labelled two-series comparison (e.g. supply vs.
  demand); false otherwise
- notes: anything a reader should know about how honest or complete this
  series is

If nothing published and honest supports this bullet, reply with exactly:
{_NO_SERIES_TOKEN}
"""
