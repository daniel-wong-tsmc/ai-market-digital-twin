from gpu_agent.dashboard.deepdive_model import (
    LENS_TO_DIMENSION, SLOT_TO_DIMENSION, build_deepdive_targets)

def _latest():
    return {
      "dimensionRatings": {"bottleneck": {
          "rating": "Weak", "direction": "improving",
          "confidence": {"level": "medium", "basis": "3/3 samples; capped"},
          "voteSpread": "3/3 Weak", "rationale": "Packaging sold out. Gap narrowing.",
          "findingIds": ["f1", "f2"]}},
      "dimensionStatus": {"bottleneck": {"confidenceCap": True}},
      "findings": [
          {"id": "f1", "statement": "CoWoS sold out through 2027.", "trend": "rising",
           "evidence": [{"source": "TradingKey", "url": "https://x", "tier": "secondary"}]},
          {"id": "f2", "statement": "Gap narrows to 10%.", "trend": "falling",
           "evidence": [{"source": "TrendForce", "url": "https://y", "tier": "secondary"}]}],
    }

def test_maps_present():
    assert LENS_TO_DIMENSION["supply"] == "bottleneck"
    assert SLOT_TO_DIMENSION["binding-constraint"] == "bottleneck"

def test_build_targets_bottleneck_payload():
    calls = [{"title": "Supply binding", "lens": "supply",
              "falsifiableTrigger": "HBM eases", "lastVerdict": "reaffirmed"}]
    impls = [{"text": "Packaging caps GPU revenue.", "dimensions": ["bottleneck"]}]
    t = build_deepdive_targets(_latest(), {"bottleneck": [0.0, 2.0]}, calls, impls)
    b = t["bottleneck"]
    assert b["title"].startswith("bottleneck")
    assert "Packaging sold out" in b["why"]
    assert b["trend"] == [0.0, 2.0]
    assert b["trend_good"] is True                       # improving → good
    assert len(b["evidence"]) == 2 and b["evidence"][0]["source"] == "TradingKey"
    assert "3/3 Weak" in b["confidence"]
    assert b["tsmc"] == ["Packaging caps GPU revenue."]
    assert b["calls"][0]["trigger"] == "HBM eases"
    assert b["change"] == "HBM eases"                    # first mapped call's trigger
    assert any(x["text"] == "Weak" for x in b["badges"])
