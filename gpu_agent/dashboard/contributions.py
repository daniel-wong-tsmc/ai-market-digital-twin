"""F95 drill-down arithmetic — mirrors gpu_agent/scoring.py (FROZEN CORE, never edited here).

Same grouping, same latest-finding rule, same weight x polarity x magnitude / 3. The parity
test (tests/dashboard/test_contributions.py) pins the sums to dmi_smi_contribution so this
mirror can never silently drift from the real scoring."""
from __future__ import annotations


def _latest(findings):
    return max(findings, key=lambda f: (f.capturedAt, f.observedAt, f.magnitude))


def contribution_rows(findings, registry, category_id) -> list[dict]:
    by_key: dict[tuple, list] = {}
    for f in findings:
        spec = registry.resolve(f.indicatorId, category_id)
        if not spec.scoring or spec.side in ("price", "structural"):
            continue
        by_key.setdefault((f.entity, f.indicatorId), []).append(f)
    rows = []
    for (entity, ind_id), fs in by_key.items():
        spec = registry.resolve(ind_id, category_id)
        chosen = _latest(fs)
        dc = spec.weight * chosen.polarityDemand * chosen.magnitude / 3
        sc_ = spec.weight * chosen.polaritySupply * chosen.magnitude / 3
        rows.append({
            "entity": entity,
            "indicator_id": ind_id,
            "label": getattr(spec, "label", ind_id) or ind_id,
            "weight": spec.weight,
            "magnitude": chosen.magnitude,
            "polarity_demand": chosen.polarityDemand,
            "polarity_supply": chosen.polaritySupply,
            "demand_contribution": dc,
            "supply_contribution": sc_,
            "finding_id": chosen.id,
            "statement": chosen.statement,
            "observed_at": chosen.observedAt,
            "evidence": [{"source": e.source, "url": e.url, "date": e.date, "tier": e.tier}
                         for e in chosen.evidence],
        })
    rows.sort(key=lambda r: (-(abs(r["demand_contribution"]) + abs(r["supply_contribution"])),
                             r["indicator_id"], r["entity"]))
    return rows
