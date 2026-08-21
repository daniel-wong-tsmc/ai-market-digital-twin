import json
import pytest
from gpu_agent.price_local import (
    BENCHMARKS_PATH, HardwarePoint, load_benchmarks, read_hardware_points)


def test_load_benchmarks_real_config_sorted_by_rank_desc():
    gens = load_benchmarks()
    ranks = [g["rank"] for g in gens]
    assert ranks == sorted(ranks, reverse=True)
    ids = [g["id"] for g in gens]
    assert "blackwell" in ids and "hopper" in ids
    for g in gens:
        for h in g["hardware"]:
            assert h["file"] and h["row"] and h["perGpuDivisor"] >= 1 and h["label"]


BENCH = [{"id": "hopper", "rank": 2, "hardware": [
            {"file": "hw.csv", "row": "NVIDIA H100 Card", "perGpuDivisor": 1,
             "label": "H100 card"}], "rental": {"models": ["H100"]}},
         {"id": "blackwell", "rank": 3, "hardware": [
            {"file": "hw.csv", "row": "HGX B200 8-GPU", "perGpuDivisor": 8,
             "label": "B200 platform, per GPU"}], "rental": {"models": ["B200"]}}]


def _write_hw(tmp_path, rows):
    lines = ["gpu,250601,250715,260701"]
    lines += rows
    (tmp_path / "hw.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_read_hardware_points_curates_divides_and_skips(tmp_path):
    _write_hw(tmp_path, [
        "NVIDIA H100 Card,30000.0,29500.0,29999.0",
        "HGX B200 8-GPU,,260000.0,260128.0",
        "Broken Junk Row,1.0,2.0,3.0",              # unlisted -> never read
    ])
    pts = read_hardware_points(tmp_path, BENCH)
    by_gen = {(p.generation, p.date): p for p in pts}
    assert by_gen[("hopper", "250601")].usd_per_gpu == 30000.0
    assert by_gen[("blackwell", "260701")].usd_per_gpu == pytest.approx(260128.0 / 8)
    assert ("blackwell", "250601") not in by_gen          # blank cell skipped
    assert not [p for p in pts if p.row_name == "Broken Junk Row"]
    assert by_gen[("hopper", "250601")].label == "H100 card"


def test_read_hardware_points_duplicate_rows_keep_longest(tmp_path):
    _write_hw(tmp_path, [
        "NVIDIA H100 Card,30000.0,,",               # 1 cell
        "NVIDIA H100 Card,31000.0,30500.0,29999.0", # 3 cells -> wins
    ])
    pts = read_hardware_points(tmp_path, BENCH)
    hopper = sorted([p for p in pts if p.generation == "hopper"],
                    key=lambda p: p.date)
    assert [p.usd_per_gpu for p in hopper] == [31000.0, 30500.0, 29999.0]


def test_read_hardware_points_missing_file_is_empty(tmp_path):
    assert read_hardware_points(tmp_path, BENCH) == []


from gpu_agent.price_local import RentalPoint, read_rental_points


def _mk_leasing(tmp_path):
    # aws_price.csv: on-demand + 1yr rows for p5.48xlarge (H100 x8 per AWS_INSTANCE_MAP)
    (tmp_path / "aws_price.csv").write_text(
        "instance,term,region,260601,260708\n"
        "p5.48xlarge,on_demand,US East (N. Virginia),98.32,96.00\n"
        "p5.48xlarge,1 year,US East (N. Virginia),63.20,60.80\n",
        encoding="utf-8")
    (tmp_path / "aws_spot_price.csv").write_text(
        ",instance,region,date,avg_price,high,low\n"
        "1,p5.48xlarge,us-east-1a,260705,41.60,42.0,41.0\n"
        "2,p5.48xlarge,us-east-1b,260706,44.80,45.0,44.0\n",
        encoding="utf-8")
    return tmp_path


def test_read_rental_points_all_three_modalities(tmp_path):
    d = _mk_leasing(tmp_path)
    pts = read_rental_points(d, {"H100"}, "260708")
    by_mod = {p.modality: p for p in pts}
    assert by_mod["on_demand"].usd_per_gpu_hour == pytest.approx(96.00 / 8)
    assert by_mod["1yr"].usd_per_gpu_hour == pytest.approx(60.80 / 8)
    # spot: median of the two newest-per-instance readings (same instance, two
    # regions -> both kept; median of 41.60/8 and 44.80/8)
    assert by_mod["spot"].usd_per_gpu_hour == pytest.approx((41.60 + 44.80) / 2 / 8)
    assert all(p.model == "H100" for p in pts)


def test_read_rental_points_ignores_unwanted_models_and_missing_files(tmp_path):
    d = _mk_leasing(tmp_path)
    assert read_rental_points(d, {"B200"}, "260708") == []
    assert read_rental_points(tmp_path / "nope", {"H100"}, "260708") == []


# --- Task 3: series emission + price-sync CLI verb ---------------------------------

from gpu_agent.price_local import latest_generation, sync_series


def test_latest_generation_rolls_with_freshness(tmp_path):
    hw = [HardwarePoint("hopper", "H100 NVL card", "260701", 29999.0, "f", "r"),
          HardwarePoint("blackwell", "B200 platform, per GPU", "260305",
                        32516.0, "f", "r")]
    # blackwell newest reading is >90d old at 2026-07-08 -> hopper wins
    g = latest_generation(BENCH, hw, "260708")
    assert g["id"] == "hopper"
    hw.append(HardwarePoint("blackwell", "B200 platform, per GPU", "260630",
                            32516.0, "f", "r"))
    assert latest_generation(BENCH, hw, "260708")["id"] == "blackwell"
    assert latest_generation(BENCH, [], "260708") is None


def test_sync_series_backfills_and_is_idempotent(tmp_path):
    d = _mk_leasing(tmp_path)
    _write_hw(tmp_path, ["NVIDIA H100 Card,30000.0,29500.0,29999.0",
                         "HGX B200 8-GPU,,260000.0,260128.0"])
    series = tmp_path / "series"
    s1 = sync_series(d, series, "2026-07-08", benchmarks=BENCH)
    rows = [json.loads(l) for l in
            (series / "gpuSpotPrice.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [r["period"] for r in rows] == ["2025-06", "2025-07", "2026-07"]
    assert rows[-1]["unit"] == "USD" and rows[-1]["label"]
    # blackwell has a fresh 2026-07 point -> latest month is blackwell per-GPU
    assert rows[-1]["value"] == pytest.approx(260128.0 / 8)
    assert "blackwell" in rows[-1]["note"]
    # rentals written too
    od = [json.loads(l) for l in
          (series / "gpuRentalOnDemand.jsonl").read_text(encoding="utf-8").splitlines()]
    assert od[-1]["unit"] == "USD_per_hr"
    # idempotent: run again, same as_of -> same row count, current month replaced
    s2 = sync_series(d, series, "2026-07-08", benchmarks=BENCH)
    rows2 = (series / "gpuSpotPrice.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(rows2) == len(rows)


def test_sync_series_stale_folder_warns_and_freezes(tmp_path):
    d = _mk_leasing(tmp_path)
    _write_hw(tmp_path, ["NVIDIA H100 Card,30000.0,29500.0,29999.0"])
    series = tmp_path / "series"
    out = sync_series(d, series, "2026-11-30", benchmarks=BENCH)   # data ends 260708
    assert any("stale" in w.lower() for w in out["warnings"])
    rows = [json.loads(l) for l in
            (series / "gpuSpotPrice.jsonl").read_text(encoding="utf-8").splitlines()]
    assert all(r["period"] != "2026-11" for r in rows)


def test_sync_series_survives_malformed_series_file(tmp_path):
    # M3: a corrupt existing series line (bad JSON, not just a missing file)
    # must degrade gracefully -- _read_jsonl broadened to catch ValueError too
    # -- rather than crashing sync_series/price-sync (run-cycle documents this
    # step as "never fatal").
    d = _mk_leasing(tmp_path)
    _write_hw(tmp_path, ["NVIDIA H100 Card,30000.0,29500.0,29999.0",
                         "HGX B200 8-GPU,,260000.0,260128.0"])
    series = tmp_path / "series"
    series.mkdir()
    (series / "gpuSpotPrice.jsonl").write_text(
        '{"period": "2025-01", "value": 1}\n' + "not valid json\n", encoding="utf-8")
    out = sync_series(d, series, "2026-07-08", benchmarks=BENCH)   # must not raise
    assert isinstance(out, dict)
    rows = [json.loads(l) for l in
            (series / "gpuSpotPrice.jsonl").read_text(encoding="utf-8").splitlines()]
    assert rows[-1]["period"] == "2026-07"   # current-month upsert still worked


def _mk_leasing_no_spot(tmp_path):
    # Same on-demand/1yr data as _mk_leasing, but the spot CSV has zero rows
    # for any GPU instance (header only) -- simulates a modality that never
    # surfaces data for this benchmark set.
    (tmp_path / "aws_price.csv").write_text(
        "instance,term,region,260601,260708\n"
        "p5.48xlarge,on_demand,US East (N. Virginia),98.32,96.00\n"
        "p5.48xlarge,1 year,US East (N. Virginia),63.20,60.80\n",
        encoding="utf-8")
    (tmp_path / "aws_spot_price.csv").write_text(
        ",instance,region,date,avg_price,high,low\n",
        encoding="utf-8")
    return tmp_path


def test_sync_series_empty_modality_writes_no_file(tmp_path):
    # M2: gpuRentalSpot never has data in this fixture -> no series file should
    # be created for it, while gpuRentalOnDemand (which does have data) still
    # gets written normally.
    d = _mk_leasing_no_spot(tmp_path)
    _write_hw(tmp_path, ["NVIDIA H100 Card,30000.0,29500.0,29999.0",
                         "HGX B200 8-GPU,,260000.0,260128.0"])
    series = tmp_path / "series"
    out = sync_series(d, series, "2026-07-08", benchmarks=BENCH)
    assert (series / "gpuRentalOnDemand.jsonl").exists()
    assert (series / "gpuRentalSpot.jsonl").exists() is False
    assert out["written"]["gpuRentalSpot"] == 0


# --- F102: month-grain --as-of + malformed-input tolerance -------------------------

import datetime as dt
from gpu_agent.price_local import _parse_as_of


def test_parse_as_of_day_grain():
    assert _parse_as_of("2026-07-17") == "260717"


def test_parse_as_of_month_grain_true_month_end():
    assert _parse_as_of("2026-07") == "260731"
    assert _parse_as_of("2026-02") == "260228"
    assert _parse_as_of("2028-02") == "280229"      # leap year


def test_parse_as_of_rejects_garbage_without_raising():
    for bad in ("", "garbage", "2026", "2026-7", "2026-07-99", "26-07-01"):
        assert _parse_as_of(bad) is None


def test_sync_series_month_grain_completes(tmp_path):
    # the four-sighting reproduction (v11/v14/v15/v17): month-grain as-of must
    # sync cleanly.
    d = _mk_leasing(tmp_path)
    _write_hw(tmp_path, ["NVIDIA H100 Card,30000.0,29500.0,29999.0",
                         "HGX B200 8-GPU,,260000.0,260128.0"])
    series = tmp_path / "series"
    result = sync_series(d, series, "2026-07", benchmarks=BENCH)
    assert sum(result["written"].values()) > 0
    assert not any("unusable as-of" in w for w in result["warnings"])
    assert (series / "gpuSpotPrice.jsonl").exists()


def test_sync_series_bad_as_of_warns_and_writes_nothing(tmp_path):
    d = _mk_leasing(tmp_path)
    _write_hw(tmp_path, ["NVIDIA H100 Card,30000.0,29500.0,29999.0",
                         "HGX B200 8-GPU,,260000.0,260128.0"])
    series = tmp_path / "series"
    series.mkdir()
    before = sorted(series.iterdir())
    before_bytes = {p.name: p.read_bytes() for p in before}
    result = sync_series(d, series, "garbage", benchmarks=BENCH)
    assert any("unusable as-of" in w and "garbage" in w for w in result["warnings"])
    after = sorted(series.iterdir())
    assert [p.name for p in after] == [p.name for p in before]
    for p in after:
        assert p.read_bytes() == before_bytes[p.name]


# --- F122: rental modalities from the daily snapshots; staleness decoupled ---------

import csv as _csv
from gpu_agent.pricepull import SNAPSHOT_FIELDS


def _snap(dir_, date, rows):
    dir_.mkdir(parents=True, exist_ok=True)
    path = dir_ / f"gpu_prices-{date}.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = _csv.DictWriter(f, fieldnames=SNAPSHOT_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow(dict(zip(SNAPSHOT_FIELDS, r)))
    return path


SNAP_ROWS = [
    ("AWS", "H100", "on_demand", "7.0", "56.0", "8", "p5.48xlarge", "us-east-1", "s", "t"),
    ("Azure", "H100", "on_demand", "9.0", "72.0", "8", "ND96", "eastus", "s", "t"),
    ("AWS", "H100", "spot", "3.0", "24.0", "8", "p5.48xlarge", "us-east-1", "s", "t"),
    ("Azure", "H100", "spot", "5.0", "40.0", "8", "ND96", "eastus", "s", "t"),
    ("Azure", "H100", "spot", "1.0", "8.0", "8", "ND96", "australiaeast", "s", "t"),   # non-US
    ("AWS", "H100", "reserved_1yr", "4.0", "32.0", "8", "p5.48xlarge", "us-east-1", "s", "t"),
    ("Vast.ai", "H100", "interruptible_min", "0.9", "0.9", "1", "1x", "Georgia, US", "s", "t"),  # not spot
    # NOTE (pre-flight ruling): no B200 row here on purpose — a lone blackwell on-demand row would
    # out-rank hopper on the ladder and the hopper expectations below would be wrong.
]


def test_read_rental_points_from_snapshot_all_three_modalities(tmp_path):
    snaps = tmp_path / "snaps"
    _snap(snaps, "2026-08-20", SNAP_ROWS)
    pts = read_rental_points(tmp_path / "no-legacy", {"H100"}, "260831", snapshot_dir=snaps)
    by_mod = {p.modality: p for p in pts}
    assert by_mod["on_demand"].usd_per_gpu_hour == pytest.approx((7.0 + 9.0) / 2)
    assert by_mod["spot"].usd_per_gpu_hour == pytest.approx((3.0 + 5.0) / 2)   # non-US + interruptible excluded
    assert by_mod["1yr"].usd_per_gpu_hour == pytest.approx(4.0)
    assert all(p.date == "260820" and p.model == "H100" for p in pts)
    assert by_mod["spot"].source == "gpu_prices-2026-08-20.csv"


def test_read_rental_points_snapshot_dir_none_is_legacy_only(tmp_path):
    d = _mk_leasing(tmp_path)
    legacy = read_rental_points(d, {"H100"}, "260708")
    assert read_rental_points(d, {"H100"}, "260708", snapshot_dir=None) == legacy


def test_sync_series_fresh_rental_writes_current_month_while_hardware_is_stale(tmp_path):
    # hardware data ends 2026-07-01 -> stale at 2026-08-20 (>45d); rental snapshot is fresh
    _write_hw(tmp_path, ["NVIDIA H100 Card,30000.0,29500.0,29999.0"])
    snaps = tmp_path / "snaps"
    _snap(snaps, "2026-08-20", SNAP_ROWS)
    series = tmp_path / "series"
    out = sync_series(tmp_path, series, "2026-08-20", benchmarks=BENCH, snapshot_dir=snaps)
    assert any(w.startswith("stale price folder") for w in out["warnings"])      # hardware, unchanged
    assert not any(w.startswith("stale rental data") for w in out["warnings"])
    hw_rows = [json.loads(l) for l in (series / "gpuSpotPrice.jsonl").read_text(encoding="utf-8").splitlines()]
    assert all(r["period"] != "2026-08" for r in hw_rows)                         # hardware still frozen
    od = [json.loads(l) for l in (series / "gpuRentalOnDemand.jsonl").read_text(encoding="utf-8").splitlines()]
    assert od[-1]["period"] == "2026-08" and od[-1]["value"] == pytest.approx(8.0)   # median(7, 9)
    assert od[-1]["note"] == "generation=hopper"
    spot = [json.loads(l) for l in (series / "gpuRentalSpot.jsonl").read_text(encoding="utf-8").splitlines()]
    assert spot[-1]["period"] == "2026-08" and spot[-1]["value"] == pytest.approx(4.0)
    assert out["written"]["gpuRentalOnDemand"] >= 1


def test_sync_series_stale_rental_warns_and_skips_current_month(tmp_path):
    d = _mk_leasing(tmp_path)                       # legacy rental ends 260708
    _write_hw(tmp_path, ["NVIDIA H100 Card,30000.0,29500.0,29999.0"])
    series = tmp_path / "series"
    out = sync_series(d, series, "2026-11-30", benchmarks=BENCH, snapshot_dir=tmp_path / "none")
    assert any(w.startswith("stale rental data") for w in out["warnings"])
    od = [json.loads(l) for l in (series / "gpuRentalOnDemand.jsonl").read_text(encoding="utf-8").splitlines()]
    assert all(r["period"] != "2026-11" for r in od)
