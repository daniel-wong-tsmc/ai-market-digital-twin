import json
import pytest
from gpu_agent.gathering.webreach import (
    FetchRequest, validate_request, load_licensed_domains, licensed_source_host,
)

REGISTRY = {"tools": [{
    "id": "agent-reach", "enabled": True, "role": "fetch",
    "fetchVerbs": {
        "read":   {"argv": ["agent-reach", "read", "{target}"],   "kind": "url"},
        "search": {"argv": ["agent-reach", "search", "{target}"], "kind": "query"},
    },
}]}
LICENSED = {"trendforce.com", "semianalysis.com"}

def _req(**kw):
    base = dict(toolId="agent-reach", verb="read", target="https://example.com/a")
    base.update(kw)
    return FetchRequest(**base)

def test_valid_https_url_passes():
    assert validate_request(_req(), REGISTRY, LICENSED) is None

def test_non_http_scheme_refused():
    for bad in ("file:///C:/x", "ftp://x/y", "javascript:alert(1)",
                r"\\evil\share\x", "data:text/html,hi"):
        reason = validate_request(_req(target=bad), REGISTRY, LICENSED)
        assert reason is not None and "scheme" in reason

def test_licensed_domain_is_allowed_not_refused():
    # D6: licensed/inventoried domains (TrendForce, SemiAnalysis, ...) are no longer
    # hard-blocked -- validate_request allows them like any other http(s) host. The
    # licensed_source_host tests below cover the flag that replaces the old refusal.
    for url in ("https://trendforce.com/r", "https://www.trendforce.com/r",
                "https://api.semianalysis.com/x",
                "https://user:pass@trendforce.com/x"):
        assert validate_request(_req(target=url), REGISTRY, LICENSED) is None

def test_unknown_tool_and_verb_refused():
    assert "unknown tool" in validate_request(_req(toolId="nope"), REGISTRY, LICENSED)
    assert "unknown verb" in validate_request(_req(verb="exec"), REGISTRY, LICENSED)

def test_query_verb_skips_url_checks_but_not_tool_checks():
    ok = _req(verb="search", target="H100 spot pricing july")
    assert validate_request(ok, REGISTRY, LICENSED) is None

def test_load_licensed_domains(tmp_path):
    p = tmp_path / "lic.json"
    p.write_text(json.dumps({"domains": ["TrendForce.com", "dello.ro"]}), "utf-8")
    assert load_licensed_domains(p) == {"trendforce.com", "dello.ro"}

def test_licensed_source_host_matches_exact_and_subdomain_and_userinfo_is_not_a_bypass():
    for url, expected in [
        ("https://trendforce.com/r", "trendforce.com"),
        ("https://www.trendforce.com/r", "trendforce.com"),
        ("https://api.semianalysis.com/x", "semianalysis.com"),
        ("https://user:pass@trendforce.com/x", "trendforce.com"),  # userinfo can't hide it
    ]:
        assert licensed_source_host(url, LICENSED) == expected

def test_licensed_source_host_lookalikes_and_clean_hosts_return_none():
    for url in ("https://nottrendforce.com/r", "https://trendforce.com.evil.com/r",
                "https://example.com/a", "https://user:pass@example.com/a"):
        assert licensed_source_host(url, LICENSED) is None

def test_licensed_source_host_returns_none_for_non_url_target():
    # query-kind targets (free text, not a URL) are never a licensed-source match
    assert licensed_source_host("H100 spot pricing july", LICENSED) is None

def test_lookalike_domains_are_not_over_refused():
    for url in ("https://nottrendforce.com/r", "https://trendforce.com.evil.com/r"):
        assert validate_request(_req(target=url), REGISTRY, LICENSED) is None

def test_build_argv_substitutes_target_as_single_element():
    from gpu_agent.gathering.webreach import build_argv
    tool = REGISTRY["tools"][0]
    argv = build_argv(tool, _req(target="https://e.com/a?b=1&c=2;rm -rf /"))
    assert argv == ["agent-reach", "read", "https://e.com/a?b=1&c=2;rm -rf /"]
    assert len(argv) == 3  # metacharacters stay INSIDE one argv element

def test_build_argv_never_splits_or_formats_other_slots():
    from gpu_agent.gathering.webreach import build_argv
    tool = {"id": "t", "enabled": True,
            "fetchVerbs": {"read": {"argv": ["t", "read", "{target}", "--flag{x}"],
                                     "kind": "url"}}}
    argv = build_argv(tool, FetchRequest(toolId="t", verb="read", target="https://e.com"))
    assert argv == ["t", "read", "https://e.com", "--flag{x}"]  # only {target}, verbatim slots otherwise


# --------------------------------------------------------------------------- #
# F126: a publisher who asked not to be used is refused here, before anything
# is built or executed. A site that merely blocks the verifier's plain reader
# is NOT -- that is a fact about the verifier's reader, not about permission,
# and gatherers still read those pages for claims.
# --------------------------------------------------------------------------- #

from gpu_agent.fetch_policy import (   # noqa: E402 -- grouped with its own tests
    DoNotFetchEntry, DoNotFetchRegistry, KIND_BLOCKS_READERS, KIND_OBJECTION)

_DO_NOT_FETCH = DoNotFetchRegistry([
    DoNotFetchEntry("objector.test", KIND_OBJECTION, "2026-08-25", "asked us not to"),
    DoNotFetchEntry("blocker.test", KIND_BLOCKS_READERS, "2026-08-25", "403s the reader"),
])


def test_a_publisher_objection_domain_is_refused_with_a_clear_reason():
    reason = validate_request(_req(target="https://objector.test/a"), REGISTRY,
                              LICENSED, _DO_NOT_FETCH)
    assert reason == "refused: publisher objection (objector.test)"


def test_a_publisher_objection_covers_subdomains_and_userinfo():
    for url in ("https://news.objector.test/a", "https://user:pw@objector.test/a",
                "https://OBJECTOR.test:8443/a"):
        assert validate_request(_req(target=url), REGISTRY, LICENSED,
                                _DO_NOT_FETCH) == (
            "refused: publisher objection (objector.test)")


def test_a_blocks_plain_readers_domain_is_not_refused_by_the_fetch_runner():
    """Gatherers may still read those pages for claims -- the block is about
    the verifier's plain reader, not about permission."""
    assert validate_request(_req(target="https://blocker.test/a"), REGISTRY,
                            LICENSED, _DO_NOT_FETCH) is None


def test_a_query_kind_target_is_never_matched_against_the_do_not_fetch_list():
    """A free-text search target has no host to judge; it must pass through."""
    assert validate_request(_req(verb="search", target="objector.test foundry share"),
                            REGISTRY, LICENSED, _DO_NOT_FETCH) is None


def test_omitting_the_do_not_fetch_registry_refuses_nothing_new():
    assert validate_request(_req(target="https://objector.test/a"), REGISTRY,
                            LICENSED) is None
