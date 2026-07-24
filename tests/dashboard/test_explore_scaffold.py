from gpu_agent.dashboard.explore_render import page_scaffold, check_links


def test_scaffold_has_crumb_and_tieback():
    html = page_scaffold("Findings", "every piece of evidence", "<p>x</p>", depth=2)
    assert "← today" in html and "../index.html" in html
    assert "Behind the verdict: every piece of evidence" in html


def test_check_links_catches_dead_href():
    pages = {"c/index.html": '<a href="findings/index.html">f</a>',
             "c/findings/index.html": '<a href="../index.html">b</a>'
                                       '<a href="../history.html#m-2026-07">h</a>'}
    errs = check_links(pages)
    assert len(errs) == 1 and "history.html" in errs[0]
    pages["c/history.html"] = "<p>ok</p>"
    assert check_links(pages) == []


def test_check_links_ignores_external_and_fragments():
    pages = {"c/a.html": '<a href="https://x.example/y">e</a><a href="#top">t</a>'}
    assert check_links(pages) == []
