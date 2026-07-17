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
