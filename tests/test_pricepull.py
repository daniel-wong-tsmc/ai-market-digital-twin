"""F122 — the ported GPU leasing-price puller. All offline: fixtures + fake fetchers."""
import csv
import pathlib

import pytest

from gpu_agent import pricepull as p

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "pricepull"


# --- normalize (ported) -----------------------------------------------------------
def test_normalize_common_datacenter_names():
    assert p.normalize("NVIDIA H100 80GB HBM3") == "H100"
    assert p.normalize("NVIDIA HGX B200") == "B200"
    assert p.normalize("AMD Instinct MI300X OAM") == "MI300X"
    assert p.normalize("NVIDIA A100-SXM4-80GB") == "A100 80GB"
    assert p.normalize("NVIDIA A100-SXM4-40GB") == "A100 40GB"


def test_normalize_h100_nvl_distinguished_from_h100():
    assert p.normalize("NVIDIA H100 NVL") == "H100 NVL"
    assert p.normalize("H100 SXM") == "H100"


def test_normalize_rtx_a4000_is_not_an_a40():
    assert p.normalize("NVIDIA RTX A4000") == "NVIDIA RTX A4000"


def test_normalize_t4_and_rtx_2000_ada():
    assert p.normalize("Tesla T4") == "T4"
    assert p.normalize("NVIDIA RTX 2000 Ada") == "NVIDIA RTX 2000 Ada"


def test_normalize_unknown_name_passes_through_stripped():
    assert p.normalize("  SomeFuture GPU 9000 ") == "SomeFuture GPU 9000"


# --- CoreWeave parser (ported, fixture) ------------------------------------------
@pytest.fixture(scope="module")
def cw_rows():
    html = (FIXTURES / "coreweave_sample.html").read_text(encoding="utf-8")
    return p.parse_coreweave(html)


def test_coreweave_each_model_once_per_price_type(cw_rows):
    keys = [(r["gpu_model"], r["price_type"]) for r in cw_rows]
    assert len(keys) == len(set(keys))


def test_coreweave_b200_on_demand(cw_rows):
    [r] = [r for r in cw_rows if r["gpu_model"] == "B200" and r["price_type"] == "on_demand"]
    assert r["usd_per_instance_hr"] == 68.80
    assert r["gpus_per_instance"] == 8
    assert r["usd_per_gpu_hr"] == pytest.approx(8.60, abs=0.01)


def test_coreweave_b200_spot(cw_rows):
    [r] = [r for r in cw_rows if r["gpu_model"] == "B200" and r["price_type"] == "spot"]
    assert r["usd_per_instance_hr"] == 34.11


def test_coreweave_h100_present(cw_rows):
    assert "H100" in {r["gpu_model"] for r in cw_rows}


# --- Azure item pricing (ported) -------------------------------------------------
def _item(**kw):
    base = {"type": "Consumption", "meterName": "NC40adsH100v5",
            "productName": "Virtual Machines NCadsH100v5 Series", "retailPrice": 9.98}
    base.update(kw)
    return base


def test_azure_on_demand_consumption():
    assert p.azure_item_to_price(_item()) == ("on_demand", 9.98)


def test_azure_spot_meter():
    assert p.azure_item_to_price(_item(meterName="NC40adsH100v5 Spot", retailPrice=2.5)) == ("spot", 2.5)


def test_azure_windows_meter_excluded():
    assert p.azure_item_to_price(_item(productName="Virtual Machines NCadsH100v5 Series Windows")) is None


def test_azure_reservation_lump_sum_becomes_hourly():
    ptype, hourly = p.azure_item_to_price(
        _item(type="Reservation", reservationTerm="1 Year", retailPrice=65569.0))
    assert ptype == "reserved_1yr"
    assert hourly == pytest.approx(65569.0 / 8760, abs=1e-4)


def test_azure_three_year_reservation():
    ptype, hourly = p.azure_item_to_price(
        _item(type="Reservation", reservationTerm="3 Years", retailPrice=144251.0))
    assert ptype == "reserved_3yr"
    assert hourly == pytest.approx(144251.0 / (3 * 8760), abs=1e-4)


def test_azure_zero_price_excluded():
    assert p.azure_item_to_price(_item(retailPrice=0.0)) is None


# --- Vast offer pick (ported) ----------------------------------------------------
def test_vast_price_is_per_whole_gpu_not_scaled_by_frac():
    per_gpu, _ = p.pick_vast_offer([{"dph_total": 3.936, "num_gpus": 1, "gpu_frac": 0.125}])
    assert per_gpu == pytest.approx(3.936, abs=1e-3)


def test_vast_multi_gpu_offer_divided_by_count():
    per_gpu, _ = p.pick_vast_offer([{"dph_total": 8.0, "num_gpus": 4, "gpu_frac": 0.5}])
    assert per_gpu == pytest.approx(2.0)


def test_vast_picks_cheapest_per_gpu():
    offers = [{"dph_total": 5.0, "num_gpus": 1}, {"dph_total": 3.0, "num_gpus": 1},
              {"dph_total": 9.0, "num_gpus": 2}]
    per_gpu, best = p.pick_vast_offer(offers)
    assert per_gpu == 3.0 and best is offers[1]


def test_vast_empty_or_invalid_offers():
    assert p.pick_vast_offer([]) is None
    assert p.pick_vast_offer([{"dph_total": None, "num_gpus": 1},
                              {"dph_total": 2.0, "num_gpus": 0}]) is None


# --- snapshot naming + run_pull (new) --------------------------------------------
def test_snapshot_path_is_one_dated_csv():
    assert p.snapshot_path("/base", "2026-08-20").as_posix() == "/base/gpu_prices-2026-08-20.csv"


def _fake(provider, rows):
    def fetch():
        return [p.row(provider, "H100", "on_demand", 2.0 + i, 16.0 + i, 8,
                      f"inst{i}", "us-east-1", "fake") for i in range(rows)]
    return (provider, fetch)


def _boom():
    raise RuntimeError("site down")


def test_run_pull_writes_dated_csv_with_exact_columns(tmp_path):
    out = p.run_pull("2026-08-20", tmp_path, fetchers=[_fake("AWS", 2), _fake("Azure", 1)],
                     retrieved_at="2026-08-20T01:02:03Z")
    path = tmp_path / "gpu_prices-2026-08-20.csv"
    assert out["path"] == str(path) and path.exists()
    assert out["rows"] == 3 and out["perProvider"] == {"AWS": 2, "Azure": 1}
    assert out["failed"] == [] and out["date"] == "2026-08-20"
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert list(rows[0].keys()) == p.SNAPSHOT_FIELDS
    assert all(r["retrieved_at"] == "2026-08-20T01:02:03Z" for r in rows)


def test_run_pull_one_failing_provider_is_reported_others_still_write(tmp_path):
    out = p.run_pull("2026-08-20", tmp_path,
                     fetchers=[_fake("AWS", 2), ("CoreWeave", _boom)])
    assert out["rows"] == 2 and out["perProvider"] == {"AWS": 2}
    assert out["failed"] == [{"provider": "CoreWeave", "error": "RuntimeError: site down"}]
    assert (tmp_path / "gpu_prices-2026-08-20.csv").exists()


def test_run_pull_all_failing_writes_no_file(tmp_path):
    out = p.run_pull("2026-08-20", tmp_path, fetchers=[("A", _boom), ("B", _boom)])
    assert out["rows"] == 0 and out["path"] is None and len(out["failed"]) == 2
    assert list(tmp_path.iterdir()) == []


def test_run_pull_same_day_rerun_overwrites(tmp_path):
    p.run_pull("2026-08-20", tmp_path, fetchers=[_fake("AWS", 3)])
    out = p.run_pull("2026-08-20", tmp_path, fetchers=[_fake("AWS", 1)])
    assert out["rows"] == 1
    with (tmp_path / "gpu_prices-2026-08-20.csv").open(newline="", encoding="utf-8") as f:
        assert len(list(csv.DictReader(f))) == 1


def test_run_pull_rows_sorted_by_model_then_price(tmp_path):
    def fetch():
        return [p.row("X", "H200", "on_demand", 5.0, 5.0, 1, "i", "us-east-1", "s"),
                p.row("X", "B200", "on_demand", 9.0, 9.0, 1, "i", "us-east-1", "s"),
                p.row("X", "B200", "on_demand", 7.0, 7.0, 1, "i", "us-east-1", "s")]
    p.run_pull("2026-08-20", tmp_path, fetchers=[("X", fetch)])
    with (tmp_path / "gpu_prices-2026-08-20.csv").open(newline="", encoding="utf-8") as f:
        got = [(r["gpu_model"], float(r["usd_per_gpu_hr"])) for r in csv.DictReader(f)]
    assert got == [("B200", 7.0), ("B200", 9.0), ("H200", 5.0)]


def test_http_get_default_timeout_is_bounded():
    """Fix 3: ~40 requests per pull, so a stalled provider must not cost minutes each."""
    import inspect
    assert inspect.signature(p.http_get).parameters["timeout"].default == p.HTTP_TIMEOUT == 20
