from gpu_agent.manifest import load_manifest


def test_manifest_covers_apiArr_and_releaseCadence():
    m = load_manifest("manifests/chips.merchant-gpu.json")
    listed = {i.indicatorId for i in m.expectedIndicators}
    assert {"apiArr", "releaseCadence"} <= listed
    covered = {ind for s in m.expectedSources for ind in s.indicators}
    assert {"apiArr", "releaseCadence"} <= covered
