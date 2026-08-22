"""F122 — `price-pull` CLI verb: exit codes + JSON summary. Fetchers are faked; no network."""
import json

import pytest

from gpu_agent import pricepull
from gpu_agent.cli import main


def _fake_fetchers():
    def fetch():
        return [pricepull.row("AWS", "H100", "on_demand", 3.0, 24.0, 8, "p5", "us-east-1", "ec2.shop")]
    return [("AWS", fetch)]


def test_price_pull_writes_snapshot_and_prints_json(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(pricepull, "FETCHERS", _fake_fetchers())
    rc = main(["price-pull", "--as-of", "2026-08-20", "--out", str(tmp_path)])
    assert rc == 0
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["rows"] == 1 and out["perProvider"] == {"AWS": 1} and out["failed"] == []
    assert (tmp_path / "gpu_prices-2026-08-20.csv").exists()
    assert out["path"].endswith("gpu_prices-2026-08-20.csv")


def test_price_pull_malformed_as_of_exits_2(tmp_path, capsys):
    rc = main(["price-pull", "--as-of", "2026-08", "--out", str(tmp_path)])
    assert rc == 2
    assert "malformed --as-of" in capsys.readouterr().err


def test_price_pull_all_providers_failing_still_exits_0(tmp_path, capsys, monkeypatch):
    def boom():
        raise OSError("offline")
    monkeypatch.setattr(pricepull, "FETCHERS", [("AWS", boom)])
    rc = main(["price-pull", "--as-of", "2026-08-20", "--out", str(tmp_path)])
    assert rc == 0
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["rows"] == 0 and out["path"] is None
    assert out["failed"] == [{"provider": "AWS", "error": "OSError: offline"}]


def test_price_pull_unwritable_out_exits_2(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(pricepull, "FETCHERS", _fake_fetchers())
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    rc = main(["price-pull", "--as-of", "2026-08-20", "--out", str(blocker / "sub")])
    assert rc == 2
    assert "cannot create --out" in capsys.readouterr().err
