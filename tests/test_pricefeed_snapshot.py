"""F122 — pricefeed reads the daily leasing snapshots (and falls back to the legacy folders)."""
import csv

import pytest

from gpu_agent.pricefeed import (
    _is_us_region, _snapshot_file, _snapshot_points, headline_prices, load_points, price_delta,
)
from gpu_agent.pricepull import SNAPSHOT_FIELDS

# legacy AWS file used for the fallback test (H100 = 55.04/8 = 6.88)
AWS = ("instance,term,region,260601,260707,260708\n"
       "p5.48xlarge,on_demand,US East (N. Virginia),50.0,55.04,55.04\n")


def _snap(dir_, date, rows):
    dir_.mkdir(parents=True, exist_ok=True)
    path = dir_ / f"gpu_prices-{date}.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=SNAPSHOT_FIELDS)
        w.writeheader()
        for r in rows:
            full = dict(zip(SNAPSHOT_FIELDS, r))
            w.writerow(full)
    return path


# provider, gpu_model, price_type, usd_per_gpu_hr, usd_per_instance_hr, gpus, instance, region, source, retrieved_at
ROWS = [
    ("Azure", "H100", "on_demand", "9.0", "72.0", "8", "ND96isr_H100_v5", "eastus", "azure", "t"),
    ("Azure", "H100", "on_demand", "11.0", "88.0", "8", "ND96isr_H100_v5", "westus2", "azure", "t"),
    ("Azure", "H100", "on_demand", "5.0", "40.0", "8", "ND96isr_H100_v5", "australiaeast", "azure", "t"),
    ("Azure", "H100", "spot", "2.0", "16.0", "8", "ND96isr_H100_v5", "eastus", "azure", "t"),
    ("AWS", "H100", "on_demand", "7.0", "56.0", "8", "p5.48xlarge", "us-east-1", "ec2.shop", "t"),
    ("AWS", "H100", "on_demand", "1.0", "8.0", "8", "p5.48xlarge", "eu-west-1", "ec2.shop", "t"),
    ("RunPod", "H100", "on_demand", "3.0", "3.0", "1", "H100 SXM", "global", "runpod", "t"),
    ("Vast.ai", "H100", "marketplace_min", "1.5", "1.5", "1", "1x H100 SXM", "Georgia, US", "vast", "t"),
    ("Vast.ai", "H100", "on_demand", "1.6", "1.6", "1", "1x H100 SXM", "Slovenia, SI", "vast", "t"),
    ("CoreWeave", "B200", "on_demand", "8.6", "68.8", "8", "NVIDIA B200", "us", "coreweave", "t"),
    ("RunPod", "RTX 4090", "on_demand", "0.4", "0.4", "1", "RTX 4090", "global", "runpod", "t"),
]


def test_is_us_region_rules():
    assert _is_us_region("azure", "eastus2") and _is_us_region("azure", "westcentralus")
    assert not _is_us_region("azure", "australiaeast") and not _is_us_region("azure", "usgovvirginia")
    assert _is_us_region("aws", "us-west-2") and not _is_us_region("aws", "eu-west-1")
    assert _is_us_region("vast.ai", "Georgia, US") and not _is_us_region("vast.ai", "Slovenia, SI")
    assert _is_us_region("runpod", "global") and _is_us_region("coreweave", "us")
    assert _is_us_region("lambda", "varies") and not _is_us_region("unknown", "us")


def test_snapshot_file_picks_newest_at_or_before(tmp_path):
    _snap(tmp_path, "2026-08-18", ROWS)
    _snap(tmp_path, "2026-08-20", ROWS)
    _snap(tmp_path, "2026-08-25", ROWS)
    assert _snapshot_file("2026-08-21", tmp_path).name == "gpu_prices-2026-08-20.csv"
    assert _snapshot_file("2026-08-20", tmp_path).name == "gpu_prices-2026-08-20.csv"
    assert _snapshot_file("2026-08-17", tmp_path) is None
    assert _snapshot_file("2026-08-21", tmp_path / "missing") is None
    # month-grain label resolves to the month END (period_end), so 2026-08 -> newest in August
    assert _snapshot_file("2026-08", tmp_path).name == "gpu_prices-2026-08-25.csv"


def test_snapshot_points_on_demand_us_matched_models_only(tmp_path):
    _snap(tmp_path, "2026-08-20", ROWS)
    pts = _snapshot_points("2026-08-20", tmp_path)
    got = sorted((p.provider, p.region, p.usd_per_gpu_hour) for p in pts)
    assert got == [("aws", "us-east-1", 7.0), ("azure", "eastus", 9.0), ("azure", "westus2", 11.0),
                   ("coreweave", "us", 8.6), ("runpod", "global", 3.0)]
    assert {p.model for p in pts} == {"H100", "B200"}            # RTX 4090 unmatched -> skipped
    assert all(p.term == "on_demand" and p.gpu_class == "gpu" for p in pts)
    assert all(p.price_date == "260820" and p.as_of == "2026-08-20" for p in pts)


def test_load_points_prefers_snapshot_and_falls_back_to_legacy(tmp_path):
    legacy = tmp_path / "legacy"; legacy.mkdir()
    (legacy / "aws_price.csv").write_text(AWS, encoding="utf-8")
    snaps = tmp_path / "snaps"
    _snap(snaps, "2026-08-20", ROWS)
    # snapshot exists at/before 2026-08-21 -> snapshot wins, legacy ignored
    assert {p.provider for p in load_points("2026-08-21", legacy, snapshot_dir=snaps)} == \
        {"aws", "azure", "coreweave", "runpod"}
    # before the first snapshot, but the folder IS in the snapshot era -> no points at all.
    # Mixing a snapshot basket with a legacy basket would fabricate a price move (Fix 1).
    assert load_points("2026-07-08", legacy, snapshot_dir=snaps) == []
    # no snapshot dir at all -> legacy
    assert len(load_points("2026-08-21", legacy, snapshot_dir=tmp_path / "none")) == 1


def test_snapshot_era_never_compares_snapshot_basket_with_legacy_basket(tmp_path):
    """Pin: with any snapshot present, a pre-snapshot date has no price and no comparison."""
    legacy = tmp_path / "legacy"; legacy.mkdir()
    (legacy / "aws_price.csv").write_text(AWS, encoding="utf-8")
    snaps = tmp_path / "snaps"
    _snap(snaps, "2026-08-22", ROWS)
    d = price_delta("2026-08-22", "2026-07-23", legacy, snapshot_dir=snaps)
    assert d["H100"]["current"] == pytest.approx(7.0)
    assert d["H100"]["prior"] is None
    assert d["H100"]["pct_delta"] is None
    assert headline_prices("2026-07-23", legacy, snapshot_dir=snaps) == {}


def test_headline_prices_from_snapshot_is_median_of_provider_medians(tmp_path):
    _snap(tmp_path, "2026-08-20", ROWS)
    hp = headline_prices("2026-08-20", tmp_path / "no-legacy", snapshot_dir=tmp_path)
    # H100 provider medians: azure median(9,11)=10, aws 7, runpod 3 -> median 7.0
    assert hp["H100"] == pytest.approx(7.0)
    assert hp["B200"] == pytest.approx(8.6)
    assert "H200" not in hp


def test_price_delta_has_no_comparison_before_history_exists(tmp_path):
    _snap(tmp_path, "2026-08-20", ROWS)
    d = price_delta("2026-08-20", "2026-07-21", tmp_path / "no-legacy", snapshot_dir=tmp_path)
    assert d["H100"]["current"] == pytest.approx(7.0)
    assert d["H100"]["prior"] is None and d["H100"]["pct_delta"] is None
