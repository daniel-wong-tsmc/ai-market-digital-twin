"""F95 drill-down arithmetic — mirrors gpu_agent/scoring.py (FROZEN CORE, never edited here).

Same grouping, same latest-finding rule, same weight x polarity x magnitude / 3, and the same
per-category weight_overrides precedence (assignment.weights beats the registry default). The
parity test (tests/dashboard/test_contributions.py) pins the sums to dmi_smi_contribution -
including the overridden-weight case - so this mirror can never silently drift from the real
scoring."""
from __future__ import annotations


def _latest(findings):
    return max(findings, key=lambda f: (f.capturedAt, f.observedAt, f.magnitude))


def contribution_rows(findings, registry, category_id, weight_overrides=None) -> list[dict]:
    # F95 item 2: mirror scoring.py's dmi_smi_contribution exactly — per-category weight
    # overrides (from the assignment) win over the registry default when present, so this
    # mirror can't silently drift from production if a weight is ever retuned.
    weight_overrides = weight_overrides or {}
    by_key: dict[tuple, list] = {}
    for f in findings:
        spec = registry.resolve(f.indicatorId, category_id)
        if not spec.scoring or spec.side in ("price", "structural"):
            continue
        by_key.setdefault((f.entity, f.indicatorId), []).append(f)
    rows = []
    for (entity, ind_id), fs in by_key.items():
        spec = registry.resolve(ind_id, category_id)
        weight = weight_overrides.get(ind_id, spec.weight)
        chosen = _latest(fs)
        dc = weight * chosen.polarityDemand * chosen.magnitude / 3
        sc_ = weight * chosen.polaritySupply * chosen.magnitude / 3
        rows.append({
            "entity": entity,
            "indicator_id": ind_id,
            "label": getattr(spec, "label", ind_id) or ind_id,
            "weight": weight,
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
