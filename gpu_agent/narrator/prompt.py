# gpu_agent/narrator/prompt.py
"""Turn narrator inputs into the tool-less brain's system prompt, user
prompt, and JSON schema bundle.

Pattern: gpu_agent/evals/emit.py's bundle shape ({system, schema, user}) is
copied here deliberately, NOT imported -- per the gated-lane rule, no
narrator module may import from gpu_agent/evals/.
"""
from __future__ import annotations

import json

from gpu_agent.dashboard.story_model import ANCHORED_INDICATOR_ID
from gpu_agent.narrator.schema import NarratorAnswer

# Spec §4's banned-word list, spelled out verbatim so the phrases survive
# any future rewording of the surrounding prose.
_BANNED_WORDS = ["momentum", "strengthening", "tightening", "accelerating",
                 "DMI", "SMI", "allocation", "doctrine", "robust", "leverage"]

NARRATOR_SYSTEM = f"""You write a short daily market story for a non-technical executive who has never seen a spreadsheet.

Your only job: answer one question -- why isn't supply catching up to demand, and what would change that. Nothing you write should wander off that question.

Editorial rules:
- The page always shows what a GPU rents for right now (indicatorId "{ANCHORED_INDICATOR_ID}") on its own, above everything you write. Never choose that indicatorId as one of your kpiPicks -- that would show the same number twice. Pick your kpiPicks from the other series in seriesPool instead.
- A scene that doesn't change what the reader understands doesn't run. Cut it.
- Write between 2 and 5 scenes. A quiet day, with nothing new worth saying, may run as few as 2 scenes.
- The last scene is always forward-looking: what to watch next, not a recap of what already happened.
- Plain newspaper English. Short sentences. No analyst jargon.
- Never use any of these words, in any form: {", ".join(_BANNED_WORDS)}.
- The words "index" or "indexed" may appear at most once in your entire answer.
- Every claim you make must cite finding ids drawn ONLY from the finding list provided to you today. Never invent a finding id, and never cite one that isn't in that list.
- Any related document you link must come ONLY from today's provided document pool. Never invent a URL.
- If you carry a claim forward from a previous day's story, it must still cite one of today's findings -- a claim can never stand on yesterday's evidence alone.
- You have no tools. Answer using only the data given to you in this prompt -- no tool use, no browsing, no memory beyond what's provided here.
- Your entire answer is a single JSON object matching the schema given to you, and nothing else -- no commentary before or after it.
"""


def build_narrator_system() -> str:
    return NARRATOR_SYSTEM


def _section(title: str, body: str) -> str:
    return f"=== {title} ===\n{body}\n"


def build_narrator_user_prompt(inputs: dict) -> str:
    today_data = {
        "scorecard": inputs["scorecard"],
        "findings": inputs["findings"],
        "implicationLines": inputs["implicationLines"],
        "seriesPool": inputs["seriesPool"],
        "gapMonths": inputs["gapMonths"],
    }

    memory = inputs["memory"]
    if memory["yesterday"] is None and not memory["recentHeadlines"]:
        memory_body = ("None yet. This is either the first story for this "
                       "category or no prior entries exist.")
    else:
        memory_body = json.dumps(memory, indent=2)

    doc_pool = inputs["docPool"]
    if not doc_pool:
        doc_body = "No documents were gathered today. Do not include any relatedDocs."
    else:
        doc_body = json.dumps(doc_pool, indent=2)

    schema_body = json.dumps(NarratorAnswer.model_json_schema(), indent=2)

    return "\n".join([
        _section("TODAY'S DATA", json.dumps(today_data, indent=2)),
        _section("YOUR PREVIOUS ENTRIES", memory_body),
        _section("TODAY'S GATHERED DOCUMENTS", doc_body),
        _section("REQUIRED OUTPUT",
                 "Answer with a single JSON object matching this schema "
                 "exactly (no extra keys):\n" + schema_body),
    ])


def emit_narrator_bundle(inputs: dict) -> dict:
    return {
        "system": build_narrator_system(),
        "schema": NarratorAnswer.model_json_schema(),
        "user": build_narrator_user_prompt(inputs),
    }
