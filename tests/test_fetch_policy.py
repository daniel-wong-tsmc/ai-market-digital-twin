"""F117/F126: the do-not-fetch registry and the shared host matcher."""
import json

import pytest

from gpu_agent.fetch_policy import (
    KIND_BLOCKS_READERS, KIND_OBJECTION,
    load_do_not_fetch, matching_domain, record_blocked_domain)

DOMAINS = {"trendforce.com", "dello.ro"}


def _write(path, entries):
    path.write_text(json.dumps({"version": 1, "entries": entries}, indent=2) + "\n",
                    encoding="utf-8", newline="\n")


def test_matching_domain_matches_exact_host_and_dot_suffix_subdomain():
    for url, expected in [
        ("https://trendforce.com/news/1", "trendforce.com"),
        ("https://www.trendforce.com/news/1", "trendforce.com"),
        ("http://a.b.trendforce.com/x", "trendforce.com"),
        ("https://user:pw@trendforce.com/x", "trendforce.com"),
        ("https://trendforce.com:8443/x", "trendforce.com"),
        ("https://TRENDFORCE.com/x", "trendforce.com"),
    ]:
        assert matching_domain(url, DOMAINS) == expected


def test_matching_domain_rejects_lookalikes_and_non_urls():
    for url in ["https://nottrendforce.com/x", "https://trendforce.com.evil.test/x",
                "https://example.test/x", "file:///etc/passwd", "H100 spot pricing"]:
        assert matching_domain(url, DOMAINS) is None


def test_load_missing_file_is_an_empty_registry_not_a_crash(tmp_path):
    reg = load_do_not_fetch(tmp_path / "nope.json")
    assert reg.is_empty
    assert reg.match("https://anything.test/x") is None


def test_load_malformed_file_is_an_empty_registry(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    assert load_do_not_fetch(p).is_empty


def test_entries_with_an_unknown_kind_or_blank_domain_are_dropped(tmp_path):
    p = tmp_path / "r.json"
    _write(p, [
        {"domain": "ok.test", "kind": KIND_OBJECTION, "since": "2026-01-01", "why": "asked"},
        {"domain": "weird.test", "kind": "made-up", "since": "2026-01-01", "why": "x"},
        {"domain": "  ", "kind": KIND_OBJECTION, "since": "2026-01-01", "why": "x"},
    ])
    reg = load_do_not_fetch(p)
    assert reg.domains() == ["ok.test"]


def test_match_filters_by_kind(tmp_path):
    p = tmp_path / "r.json"
    _write(p, [
        {"domain": "objector.test", "kind": KIND_OBJECTION, "since": "2026-01-01",
         "why": "asked us not to"},
        {"domain": "blocker.test", "kind": KIND_BLOCKS_READERS, "since": "2026-01-01",
         "why": "403s the plain reader"},
    ])
    reg = load_do_not_fetch(p)
    assert reg.match("https://objector.test/a", kind=KIND_OBJECTION).domain == "objector.test"
    assert reg.match("https://blocker.test/a", kind=KIND_OBJECTION) is None
    assert reg.match("https://blocker.test/a", kind=KIND_BLOCKS_READERS).domain == "blocker.test"
    assert reg.match("https://sub.blocker.test/a") is not None
    assert reg.domains(KIND_BLOCKS_READERS) == ["blocker.test"]


def test_record_blocked_domain_appends_once_and_keeps_the_file_sorted(tmp_path):
    p = tmp_path / "r.json"
    _write(p, [{"domain": "zeta.test", "kind": KIND_BLOCKS_READERS,
                "since": "2026-01-01", "why": "x"}])
    assert record_blocked_domain(p, "alpha.test", since="2026-08-19",
                                 first_seen_url="https://alpha.test/p") is True
    data = json.loads(p.read_text(encoding="utf-8"))
    assert [e["domain"] for e in data["entries"]] == ["alpha.test", "zeta.test"]
    added = data["entries"][0]
    assert list(added) == ["domain", "kind", "since", "why", "firstSeenUrl"]
    assert added["kind"] == KIND_BLOCKS_READERS
    assert added["firstSeenUrl"] == "https://alpha.test/p"
    # the untouched neighbour keeps its shape: no firstSeenUrl invented for it
    assert list(data["entries"][1]) == ["domain", "kind", "since", "why"]
    # LF newlines, trailing newline -- a learned append stays a one-line diff
    raw = p.read_bytes()
    assert b"\r\n" not in raw and raw.endswith(b"\n")
    # idempotent: a second learn of the same domain changes nothing
    before = p.read_text(encoding="utf-8")
    assert record_blocked_domain(p, "alpha.test", since="2026-08-20") is False
    assert p.read_text(encoding="utf-8") == before


def test_record_blocked_domain_never_downgrades_an_objection(tmp_path):
    p = tmp_path / "r.json"
    _write(p, [{"domain": "objector.test", "kind": KIND_OBJECTION,
                "since": "2026-01-01", "why": "asked us not to"}])
    assert record_blocked_domain(p, "objector.test", since="2026-08-19") is False
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["entries"][0]["kind"] == KIND_OBJECTION


def test_record_blocked_domain_creates_the_file_when_it_is_missing(tmp_path):
    p = tmp_path / "sub" / "r.json"
    assert record_blocked_domain(p, "alpha.test", since="2026-08-19") is True
    assert load_do_not_fetch(p).domains() == ["alpha.test"]


def test_record_blocked_domain_swallows_a_write_failure(tmp_path):
    """A read-only checkout must not break a cycle."""
    p = tmp_path / "r.json"
    p.mkdir()   # a directory where the file should be: the write must fail quietly
    assert record_blocked_domain(p, "alpha.test", since="2026-08-19") is False


def test_the_shipped_registry_seeds_counterpoint_as_a_blocked_reader():
    reg = load_do_not_fetch()
    entry = reg.match("https://www.counterpointresearch.com/insights/x")
    assert entry is not None
    assert entry.kind == KIND_BLOCKS_READERS
    assert entry.since == "2026-08-19"


def test_the_shipped_registry_holds_no_publisher_objection_yet():
    """No publisher has ever objected. The kind is wired, the list is empty --
    and this test is the thing that notices when that changes."""
    assert load_do_not_fetch().domains(KIND_OBJECTION) == []
