import datetime as dt
import json
import pytest
from gpu_agent.freshness import (AGING_THRESHOLD, FreshnessLoadError,
                                 classify, load_freshness, parse_date, weight)

TODAY = dt.date(2026, 7, 24)
CFG = load_freshness()


def test_registry_loads_user_values():
    assert CFG.halfLivesDays == {"news": 3, "filings": 5, "structural": 45}


def test_weight_half_life_points():
    assert weight("2026-07-24", TODAY, "news", CFG) == 1.0
    assert weight("2026-07-21", TODAY, "news", CFG) == pytest.approx(0.5)
    assert weight("2026-07-18", TODAY, "news", CFG) == pytest.approx(0.25)
    assert weight("2026-07-19", TODAY, "filings", CFG) == pytest.approx(0.5)
    assert weight("2026-06-09", TODAY, "structural", CFG) == pytest.approx(0.5)


def test_may_earnings_is_negligible_now():
    # the complaint that started F103: late-May filings in late July
    assert weight("2026-05-28", TODAY, "filings", CFG) < 0.001


def test_missing_date_treated_as_30_days_old():
    got = weight(None, TODAY, "news", CFG)
    assert got == pytest.approx(0.5 ** (30 / 3), rel=1e-3)
    assert weight("garbage", TODAY, "news", CFG) == got


def test_future_date_clamps_to_full_weight():
    assert weight("2026-08-01", TODAY, "news", CFG) == 1.0


def test_parse_date_forms():
    assert parse_date("2026-07-24") == dt.date(2026, 7, 24)
    assert parse_date("2026-07") == dt.date(2026, 7, 1)
    assert parse_date("") is None and parse_date(None) is None


def test_classify_precedence():
    assert classify("https://investor.nvidia.com/x", None, CFG) == "filings"
    assert classify("https://nvidianews.nvidia.com/y", "leadTimes", CFG) == "filings"
    assert classify("https://reuters.com/z", "upstreamLeadTimes", CFG) == "structural"
    assert classify("https://reuters.com/z", None, CFG) == "news"


def test_loader_is_a_trust_boundary(tmp_path):
    bad = tmp_path / "f.json"
    bad.write_text(json.dumps({"schemaVersion": 1,
                                "halfLivesDays": {"news": 3},
                                "filingsDomains": [], "structuralIndicators": [],
                                "surprise": True}), encoding="utf-8")
    with pytest.raises(FreshnessLoadError):
        load_freshness(bad)
    with pytest.raises(FreshnessLoadError):
        load_freshness(tmp_path / "missing.json")
