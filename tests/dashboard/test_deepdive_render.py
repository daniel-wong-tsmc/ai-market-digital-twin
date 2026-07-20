import json, re
from gpu_agent.dashboard.deepdive_render import deepdive_json, render_deepdive_panel

def test_deepdive_json_roundtrips_and_escapes():
    blob = deepdive_json({"bottleneck": {"why": "a < b & c", "evidence": []}})
    m = re.search(r'id="dd-data"[^>]*>(.*?)</script>', blob, re.S)
    data = json.loads(m.group(1).replace("\\u003c", "<"))
    assert data["bottleneck"]["why"] == "a < b & c"
    assert "<" not in m.group(1)               # raw '<' must be escaped for safety

def test_panel_shell_has_hooks():
    html = render_deepdive_panel()
    assert 'id="dd-scrim"' in html and 'id="dd-drawer"' in html
    assert "window.openDD" in html and "dd-data" in html

def test_panel_script_builds_appendix_fulllink():
    html = render_deepdive_panel()
    assert "appendix.html#dim-" in html
