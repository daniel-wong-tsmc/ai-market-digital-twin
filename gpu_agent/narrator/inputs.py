# gpu_agent/narrator/inputs.py
"""Assemble everything the daily narrator needs from committed store data.

Deterministic by construction: every list here preserves the order it reads
from disk (JSON list order, or the fixed `_SERIES_IDS` order) so the same
store state always produces byte-identical narrator inputs -- Task 4's CLI
verb and Task 6's prompt-hash pin both depend on that.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from gpu_agent.dashboard.agenda import read_series
from gpu_agent.dashboard.brief_model import latest_monthly, read_implication_lines
from gpu_agent.dashboard.gap_chart import build_gap_data
from gpu_agent.dashboard.story_model import _CHIP_DEFS, _SERIES_IDS, resolve_store_root
from gpu_agent.freshness import FreshnessConfig, classify, load_freshness, weight
from gpu_agent.issues import read_history_tail, read_register
from gpu_agent.narrator.store import StoryStore

# Matches story_model's own sparkline window (_chip() there slices series[-8:]).
_TAIL_LEN = 8

# How many past assessments of an open issue the narrator gets to see.
_ISSUE_HISTORY_TAIL = 8


def _finding_trim(f: dict, today: dt.date, cfg: FreshnessConfig) -> dict:
    evidence = [
        {"source": e.get("source") or "", "url": e.get("url") or "",
         "date": e.get("date") or "", "tier": e.get("tier") or ""}
        for e in (f.get("evidence") or [])
    ]
    if evidence:
        freshness_weight = max(
            weight(e["date"], today, classify(e["url"], None, cfg), cfg)
            for e in evidence
        )
    else:
        freshness_weight = weight(None, today, "news", cfg)
    return {
        "id": f.get("id"),
        "statement": f.get("statement") or "",
        "evidence": evidence,
        "freshnessWeight": freshness_weight,
    }


def build_narrator_inputs(category_id: str, store_dir: str | Path,
                          today: dt.date, run_dir: str | Path | None) -> dict:
    cfg = load_freshness()
    store_root = resolve_store_root(category_id, store_dir)
    cat_dir = store_root / category_id
    latest, _prior, as_of, rev = latest_monthly(cat_dir)
    latest = latest or {}

    scorecard = {
        "asOf": as_of,
        "revision": rev,
        "categoryStatus": latest.get("categoryStatus") or {},
        "dimensionRatings": latest.get("dimensionRatings") or {},
    }
    findings = [_finding_trim(f, today, cfg) for f in (latest.get("findings") or [])
                if isinstance(f, dict)]

    impl_lines = read_implication_lines(store_root, category_id, as_of) or []
    implication_lines = [{"text": ln["text"], "findingIds": ln["finding_ids"]}
                          for ln in impl_lines]

    series = read_series(store_root / "series", _SERIES_IDS)
    series_pool = []
    for ind in _SERIES_IDS:
        rows = series.get(ind) or []
        if not rows:
            continue
        latest_row = rows[-1]
        series_pool.append({
            "indicatorId": ind,
            "label": _CHIP_DEFS[ind]["label"],
            "latestValue": float(latest_row["value"]),
            "unit": latest_row.get("unit") or "",
            "tail": [float(r["value"]) for r in rows[-_TAIL_LEN:]],
        })

    story_store = StoryStore(store_root)
    yesterday_date = (today - dt.timedelta(days=1)).isoformat()
    yesterday_art = story_store.read(category_id, yesterday_date)
    memory = {
        "yesterday": yesterday_art.model_dump() if yesterday_art else None,
        "recentHeadlines": story_store.recent_headlines(
            category_id, before=today.isoformat()),
    }

    doc_pool = []
    if run_dir is not None:
        blobs_path = Path(run_dir) / "blobs.json"
        if blobs_path.exists():
            try:
                data = json.loads(blobs_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                data = {}
            for b in data.get("blobs") or []:
                url = b.get("url") or ""
                if url.startswith("https://"):
                    date = b.get("date") or ""
                    doc_pool.append({
                        "url": url, "source": b.get("source") or "", "date": date,
                        "freshnessWeight": weight(date, today, classify(url, None, cfg), cfg),
                    })

    gap = build_gap_data(cat_dir)
    gap_months = [m["key"] for m in gap["months"]] if gap else []

    # Open issues, in the order the register lists them. Clock-free: nothing
    # here depends on `today`, so the same store always yields the same list.
    open_issues = [
        {
            "id": issue.id,
            "title": issue.title,
            "trigger": {"kind": issue.trigger.kind, "label": issue.trigger.label},
            "recent": [
                {"asOf": h["asOf"], "status": h["status"]}
                for h in read_history_tail(cat_dir, issue.id, _ISSUE_HISTORY_TAIL)
            ],
        }
        for issue in read_register(cat_dir, category_id).issues
        if issue.state == "open"
    ]

    return {
        "scorecard": scorecard,
        "findings": findings,
        "implicationLines": implication_lines,
        "seriesPool": series_pool,
        "memory": memory,
        "docPool": doc_pool,
        "gapMonths": gap_months,
        "openIssues": open_issues,
        "storyDate": today.isoformat(),
    }
