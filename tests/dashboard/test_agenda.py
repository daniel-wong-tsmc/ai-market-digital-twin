import json
from gpu_agent.dashboard.agenda import AGENDA_REGISTRY_PATH, format_value, load_slots
from gpu_agent.dashboard.agenda import Candidate, candidates_for_slot, read_series


def test_load_slots_real_registry():
    slots = load_slots()
    assert [s["id"] for s in slots] == [
        "demand-durability", "binding-constraint", "customer-mix",
        "end-market-economics", "demand-quality"]
    for s in slots:
        assert s["label"] and s["question"] and s["indicators"]


def test_load_slots_custom_path(tmp_path):
    p = tmp_path / "slots.json"
    p.write_text(json.dumps({"slots": [
        {"id": "x", "label": "X", "question": "q?", "indicators": ["a"]}]}),
        encoding="utf-8")
    assert load_slots(str(p))[0]["id"] == "x"


def test_format_value_units():
    assert format_value(75.2, "USD_B") == "$75.2B"
    assert format_value(75.0, "pct") == "75%"
    assert format_value(68.8, "pct_yoy") == "+68.8% YoY"
    assert format_value(-50.0, "pct_yoy") == "-50% YoY"
    assert format_value(6.69, "USD_per_hr") == "$6.69/hr"
    assert format_value(210000, "units") == "210,000 units"
    assert format_value(3.0, "widgets") == "3 widgets"   # unknown unit: honest fallback


SLOT = {"id": "demand-durability", "label": "Demand durability",
        "question": "q?", "indicators": ["D2", "odmMonthlyAiRevenue"]}

F_MEASURED = {"indicatorId": "D2", "kind": "measured",
              "value": {"number": 75.2, "unit": "USD_B"}, "trend": "rising",
              "observedAt": "2026-07-01", "magnitude": 3,
              "statement": "NVIDIA Q1 FY2027 Data Center revenue was a record $75.2 billion.",
              "evidence": [{"tier": "primary", "source": "NVIDIA IR"}]}
F_OBSERVED = {"indicatorId": "D2", "kind": "observed", "value": None,
              "trend": "rising", "observedAt": "2026-07-02", "magnitude": 2,
              "statement": "prose only", "evidence": []}
F_OTHER_IND = dict(F_MEASURED, indicatorId="S10")

SERIES_ROW = {"indicatorId": "odmMonthlyAiRevenue", "period": "2026-06",
              "value": 68.788, "unit": "pct_yoy", "publishedAt": "2026-07-10",
              "source": {"title": "TWSE MOPS monthly revenue summary"},
              "estimateGrade": False}
SERIES_PRIOR = dict(SERIES_ROW, period="2026-05", value=50.0, publishedAt="2026-06-10")


def test_candidates_measured_finding_only():
    got = candidates_for_slot(SLOT, [F_MEASURED, F_OBSERVED, F_OTHER_IND], {})
    assert len(got) == 1
    c = got[0]
    assert (c.indicator_id, c.display, c.trend_word, c.tier, c.magnitude) == \
        ("D2", "$75.2B", "rising", "primary", 3)
    assert c.observed_at == "2026-07-01" and c.source_name == "NVIDIA IR"


def test_candidates_series_newest_row_with_trend_from_prior():
    got = candidates_for_slot(SLOT, [], {"odmMonthlyAiRevenue": [SERIES_PRIOR, SERIES_ROW]})
    assert len(got) == 1
    c = got[0]
    assert c.display == "+68.788% YoY" and c.trend_word == "rising"
    assert c.observed_at == "2026-07-10" and c.tier == "secondary"


def test_series_candidate_skips_non_numeric_value():
    # a malformed newest series row (non-numeric value) is skipped, not crashed
    got = candidates_for_slot(SLOT, [], {"odmMonthlyAiRevenue": [
        {"indicatorId": "odmMonthlyAiRevenue", "value": "n/a", "unit": "pct_yoy"}]})
    assert got == []


def test_read_series_reads_only_requested_files(tmp_path):
    import json
    d = tmp_path / "series"
    d.mkdir()
    (d / "a.jsonl").write_text(json.dumps({"indicatorId": "a", "value": 1}) + "\n",
                               encoding="utf-8")
    (d / "b.jsonl").write_text("{}\n", encoding="utf-8")
    rows = read_series(d, {"a", "missing"})
    assert set(rows) == {"a"} and rows["a"][0]["value"] == 1


import datetime as dt
from gpu_agent.dashboard.agenda import Occupant, score, select_occupants

TODAY = dt.date(2026, 7, 16)


def _cand(ind="D2", observed="2026-07-01", mag=3, tier="primary"):
    return Candidate(indicator_id=ind, label=ind, display="$1B",
                     trend_word="rising", observed_at=observed, tier=tier,
                     source_name="s", magnitude=mag, statement="st")


def test_score_prefers_fresh_high_magnitude_primary():
    fresh = _cand(observed="2026-07-14")
    stale = _cand(observed="2026-04-01")
    assert score(fresh, TODAY, None) > score(stale, TODAY, None)
    weak = _cand(mag=1)
    assert score(_cand(mag=3), TODAY, None) > score(weak, TODAY, None)
    sec = _cand(tier="secondary")
    assert score(_cand(), TODAY, None) > score(sec, TODAY, None)


def test_score_stickiness_bonus():
    c = _cand(ind="D2")
    assert score(c, TODAY, "D2") > score(c, TODAY, None)


def test_select_occupants_stickiness_holds_and_continuity_on_disappearance():
    slot = {"id": "binding-constraint", "label": "Binding constraint",
            "question": "q?", "indicators": ["S9", "S10"]}
    cowos = {"indicatorId": "S9", "kind": "measured",
             "value": {"number": 20.0, "unit": "pct"}, "trend": "falling",
             "observedAt": "2026-06-20", "magnitude": 3,
             "statement": "CoWoS gap.", "evidence": [{"tier": "primary", "source": "x"}]}
    hbm = {"indicatorId": "S10", "kind": "measured",
           "value": {"number": 2027.0, "unit": "sold_out_through"}, "trend": "rising",
           "observedAt": "2026-07-10", "magnitude": 3,
           "statement": "HBM sold out.", "evidence": [{"tier": "primary", "source": "y"}]}
    # Prior revision had CoWoS; current has both, HBM fresher. Stickiness (0.75) HOLDS the
    # slot on CoWoS/S9 -> no occupant change, no continuity note. (Code governs, per the
    # user's pre-flight decision 2026-07-16.)
    occ = select_occupants([slot], [cowos, hbm], {}, [cowos], TODAY)
    assert len(occ) == 1 and occ[0].candidate.indicator_id == "S9"
    assert occ[0].was_label is None
    # When the sticky prior reading disappears from the candidate set, the slot moves to
    # the fresher HBM/S10 and the continuity note fires.
    occ2 = select_occupants([slot], [hbm], {}, [cowos], TODAY)
    assert occ2[0].candidate.indicator_id == "S10" and occ2[0].was_label == "S9"


def test_select_occupants_skips_empty_slot():
    slot = {"id": "customer-mix", "label": "Customer mix", "question": "q?",
            "indicators": ["market-share-pct"]}
    assert select_occupants([slot], [], {}, [], TODAY) == []


def test_format_value_aliases_and_new_units():
    assert format_value(500.0, "USD billion") == "$500B"
    assert format_value(29999.0, "USD") == "$29,999"
    assert format_value(2.09e11, "flops_per_USD") == "209 GFLOPS/$"
    assert format_value(1.0, "credit_condition_index") == "loosening"
    assert format_value(-1.0, "revision_direction") == "cut"
    assert format_value(7.0, "credit_condition_index") == "7 credit_condition_index"


def test_series_candidate_label_and_delta(tmp_path):
    # PF-2: base row must be >= 80 days older than the newest reading for the
    # delta rule to fire ("~90 days back" per spec intent). 2026-04-08 is 91
    # days before 2026-07-08, still in April, still -12% (34000 -> 29999).
    rows = [
        {"indicatorId": "gpuSpotPrice", "period": "2026-04", "value": 34000.0,
         "unit": "USD", "publishedAt": "2026-04-08", "label": "H100 NVL card"},
        {"indicatorId": "gpuSpotPrice", "period": "2026-07", "value": 29999.0,
         "unit": "USD", "publishedAt": "2026-07-08", "label": "H100 NVL card"},
    ]
    got = candidates_for_slot(
        {"id": "x", "label": "X", "question": "q", "indicators": ["gpuSpotPrice"]},
        [], {"gpuSpotPrice": rows})
    c = got[0]
    assert c.label == "H100 NVL card"
    assert c.delta_line == "-12% vs Apr"


def test_series_candidate_no_delta_for_non_money_units():
    # Review fix (F98 Task-4): a percentage delta is only meaningful for
    # money/price units. A "pct" series (e.g. market share) must NOT get a
    # "+13% vs Apr"-style delta line, even though the >= 80-day lookback and
    # a real value change would otherwise make one fire.
    rows = [
        {"indicatorId": "marketSharePct", "period": "2026-04", "value": 40.0,
         "unit": "pct", "publishedAt": "2026-04-08", "label": "Merchant GPU share"},
        {"indicatorId": "marketSharePct", "period": "2026-07", "value": 45.0,
         "unit": "pct", "publishedAt": "2026-07-08", "label": "Merchant GPU share"},
    ]
    got = candidates_for_slot(
        {"id": "x", "label": "X", "question": "q", "indicators": ["marketSharePct"]},
        [], {"marketSharePct": rows})
    assert got[0].delta_line == ""


def test_series_candidate_delta_still_fires_for_money_price_unit():
    # Pin: USD_per_hr (an end-market-economics price unit) still gets a delta.
    rows = [
        {"indicatorId": "gpuHourlyRate", "period": "2026-04", "value": 8.00,
         "unit": "USD_per_hr", "publishedAt": "2026-04-08", "label": "H100 spot rate"},
        {"indicatorId": "gpuHourlyRate", "period": "2026-07", "value": 6.00,
         "unit": "USD_per_hr", "publishedAt": "2026-07-08", "label": "H100 spot rate"},
    ]
    got = candidates_for_slot(
        {"id": "x", "label": "X", "question": "q", "indicators": ["gpuHourlyRate"]},
        [], {"gpuHourlyRate": rows})
    assert got[0].delta_line == "-25% vs Apr"


def test_finding_candidate_plain_label():
    got = candidates_for_slot(SLOT, [F_MEASURED], {},
                              labels={"D2": "DC revenue structure"})
    assert got[0].label == "DC revenue structure"


def test_real_slot_families_match_f98_spec():
    fam = {s["id"]: set(s["indicators"]) for s in load_slots()}
    assert "S9" in fam["customer-mix"] and "S9" not in fam["binding-constraint"]
    assert "S10" in fam["binding-constraint"]
    assert {"gpuSpotPrice", "gpuRentalOnDemand", "gpuRentalSpot", "gpuRental1yr",
            "flopsPerDollar"} <= fam["end-market-economics"]
    assert "apiArr" in fam["demand-quality"]
    assert "releaseCadence" in fam["demand-durability"]
