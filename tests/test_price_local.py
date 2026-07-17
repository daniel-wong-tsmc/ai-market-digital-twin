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
