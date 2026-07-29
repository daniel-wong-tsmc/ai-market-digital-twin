# F106 — HuggingNews Desk-Wide Source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. The question-stop rule (CLAUDE.md) applies verbatim: a design fork STOPS the lane — write questions + recommendation to `.superpowers/handoffs/f106-huggingnews-QUESTIONS.md`, end turn. STOP before merge; only the user merges.

**Goal:** Register HuggingNews as a keyed web-reach channel any category manifest can opt into via `huggingnewsTags`, feeding the daily gather pass with leads chased to primaries (marked secondary fallback).

**Architecture:** Extend `gpu_agent/gathering/webreach.py` with generic secret resolution + per-verb auth argv (key never committed, never logged); add the `huggingnews` tool to `registry/web-reach-tools.json`; add a validated `huggingnewsTags` field to `CoverageManifest`; add the discovery sub-step to the gather-category skill prose. Gather-side only — no brain prompt, eval, or scoring exposure.

**Tech Stack:** Python 3.13, pydantic v2, pytest, curl (argv-exec via the existing `webreach-fetch` discipline). Venv: `../../.venv/Scripts/python` from the worktree root.

**Spec:** `docs/superpowers/specs/2026-07-28-f106-huggingnews-source-design.md` (user decisions D1–D3).

## Global Constraints

- Lane: worktree `.worktrees/f106-huggingnews`, branch `f106-huggingnews`. Never touch root `store/`.
- **The API key never enters git, prompts, briefs, logs, test files, or commit messages.** It lives ONLY in `.superpowers/secrets/HUGGINGNEWS_API_KEY` (already present, verified gitignored). Tests use fake secrets like `"sk-test-fake"`.
- MUST-NOT-TOUCH: `registry/indicators.json`, `registry/series-indicators.json`, `fixtures/`, `gpu_agent/evals/`, `gpu_agent/narrator/`, brain prompts, `scoring.py`, `report.py`. (`registry/web-reach-tools.json` is IN scope — it is prompt-neutral; precedent `15625be`.)
- Pins: F6, scoring-v1 replay, narrator, **and F83** all stay GREEN at every commit — run-cycle SKILL.md is untouched (the gather step lives in gather-category SKILL.md, which is NOT fingerprint-pinned; Task 4 re-verifies before editing).
- No network access in pytest: all tests are offline (argv/template assertions, temp registries, fake secrets). Live behavior is a post-merge criterion.
- Never-blocks discipline: a HuggingNews failure is a logged gap, never a cycle abort.

---

### Task 1: Secret resolution + auth-aware argv + log scrubbing (`webreach.py`)

**Files:**
- Modify: `gpu_agent/gathering/webreach.py`
- Test: `tests/test_webreach_auth.py` (new file — do not touch existing webreach tests)

**Interfaces:**
- Consumes: existing `build_argv(tool, req)` (template `{target}` substitution), `run_requests(...)` (rows record `error` from stderr), `FetchRequest`.
- Produces: `resolve_secret(name: str, *, secrets_dir=SECRETS_DIR) -> str | None` (env var wins, else `.superpowers/secrets/<name>` file stripped, else None); `SECRETS_DIR = pathlib.Path(".superpowers/secrets")`; `build_argv` EXTENDED — same signature, same return type — appending a verb's optional auth slots when the secret resolves, omitting them entirely when it doesn't; `auth_secrets_used(tool, req) -> list[str]` (resolved secret VALUES for scrubbing); `run_requests` scrubs every resolved secret from recorded `error` text with `[redacted]`.
- Registry verb shape consumed (defined here, used by Task 2's entry):
  `fetchVerbs.<verb>.auth = {"secretName": "<ENV_NAME>", "argv": ["-H", "Authorization: Bearer {secret}"]}` — optional; absent means the verb is anonymous-only.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_webreach_auth.py
import json
import pathlib
import sys
import pytest
from gpu_agent.gathering.webreach import (
    FetchRequest, auth_secrets_used, build_argv, resolve_secret, run_requests)

FAKE = "sk-test-fake-not-a-real-key"

def _tool(auth=True):
    verb = {"kind": "query",
            "argv": ["curl", "-fsS", "--get", "https://api.example.com/stories",
                     "--data-urlencode", "tags={target}"]}
    if auth:
        verb["auth"] = {"secretName": "HN_TEST_KEY",
                        "argv": ["-H", "Authorization: Bearer {secret}"]}
    return {"id": "hn-test", "enabled": True, "fetchVerbs": {"latest": verb}}

def _req():
    return FetchRequest(toolId="hn-test", verb="latest", target="ai-compute-chips")

def test_resolve_secret_env_wins_over_file(tmp_path, monkeypatch):
    (tmp_path / "HN_TEST_KEY").write_text("from-file", "utf-8")
    monkeypatch.setenv("HN_TEST_KEY", "from-env")
    assert resolve_secret("HN_TEST_KEY", secrets_dir=tmp_path) == "from-env"

def test_resolve_secret_file_fallback_stripped(tmp_path, monkeypatch):
    monkeypatch.delenv("HN_TEST_KEY", raising=False)
    (tmp_path / "HN_TEST_KEY").write_text(FAKE + "\n", "utf-8")
    assert resolve_secret("HN_TEST_KEY", secrets_dir=tmp_path) == FAKE

def test_resolve_secret_missing_is_none(tmp_path, monkeypatch):
    monkeypatch.delenv("HN_TEST_KEY", raising=False)
    assert resolve_secret("HN_TEST_KEY", secrets_dir=tmp_path) is None

def test_build_argv_appends_auth_when_secret_present(monkeypatch):
    monkeypatch.setenv("HN_TEST_KEY", FAKE)
    argv = build_argv(_tool(), _req())
    assert argv[-2:] == ["-H", f"Authorization: Bearer {FAKE}"]
    assert "tags=ai-compute-chips" in argv       # {target} substitution untouched
    assert "tags={target}" not in argv

def test_build_argv_omits_auth_when_secret_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("HN_TEST_KEY", raising=False)
    monkeypatch.setattr("gpu_agent.gathering.webreach.SECRETS_DIR", tmp_path)
    argv = build_argv(_tool(), _req())
    assert "-H" not in argv                      # anonymous degrade: no auth slots at all

def test_build_argv_without_auth_block_unchanged(monkeypatch):
    monkeypatch.setenv("HN_TEST_KEY", FAKE)
    assert "-H" not in build_argv(_tool(auth=False), _req())

def test_run_requests_scrubs_secret_from_error(tmp_path, monkeypatch):
    # a failing tool that echoes its argv (secret included) to stderr must not
    # leak the secret into the recorded manifest
    monkeypatch.setenv("HN_TEST_KEY", FAKE)
    tool = _tool()
    tool["fetchVerbs"]["latest"]["argv"] = [
        sys.executable, "-c",
        "import sys; sys.stderr.write(' '.join(sys.argv[1:])); sys.exit(3)",
        "tags={target}"]
    registry = {"version": 1, "tools": [tool]}
    reqs = tmp_path / "reqs.json"
    reqs.write_text(json.dumps([{"toolId": "hn-test", "verb": "latest",
                                 "target": "ai-compute-chips"}]), "utf-8")
    manifest = run_requests(reqs, tmp_path / "out", registry, set())
    text = json.dumps(manifest) + (tmp_path / "out" / "fetch-manifest.json").read_text("utf-8")
    assert FAKE not in text
    assert manifest["results"][0]["exitCode"] == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `../../.venv/Scripts/python -m pytest tests/test_webreach_auth.py -q`
Expected: FAIL — `ImportError: cannot import name 'resolve_secret'`.

- [ ] **Step 3: Implement** in `gpu_agent/gathering/webreach.py`:

Add near the top:

```python
import os

SECRETS_DIR = pathlib.Path(".superpowers/secrets")


def resolve_secret(name: str, *, secrets_dir: pathlib.Path | None = None) -> str | None:
    """Env var wins; else the machine-local gitignored secrets file; else None.
    The value must NEVER be written to any committed file, manifest, or log."""
    val = os.environ.get(name)
    if val:
        return val
    path = (secrets_dir if secrets_dir is not None else SECRETS_DIR) / name
    if path.is_file():
        text = path.read_text(encoding="utf-8").strip()
        return text or None
    return None


def _auth_spec(tool: dict, req: FetchRequest) -> dict | None:
    return tool["fetchVerbs"][req.verb].get("auth")


def auth_secrets_used(tool: dict, req: FetchRequest) -> list[str]:
    """Resolved secret VALUES a request's argv may contain — for log scrubbing."""
    spec = _auth_spec(tool, req)
    if not spec:
        return []
    val = resolve_secret(spec["secretName"])
    return [val] if val else []
```

Extend `build_argv` (same signature; keep the existing docstring, append to it):

```python
def build_argv(tool: dict, req: FetchRequest) -> list[str]:
    template = tool["fetchVerbs"][req.verb]["argv"]
    argv = [slot.replace("{target}", req.target) for slot in template]
    spec = _auth_spec(tool, req)
    if spec:
        val = resolve_secret(spec["secretName"])
        if val:   # missing secret = anonymous degrade: omit the auth slots entirely
            argv += [slot.replace("{secret}", val) for slot in spec["argv"]]
    return argv
```

In `run_requests`, where `row["error"]` is set from stderr (`row["error"] = (cp.stderr or "")[-500:]`) and in the exception paths, scrub secrets. Compute once per request, right after `argv = build_argv(tool, req)`:

```python
        secrets = auth_secrets_used(tool, req)
```

and define a tiny helper used at every `row["error"] = ...` assignment in the loop:

```python
def _scrub(text: str | None, secrets: list[str]) -> str | None:
    if not text:
        return text
    for s in secrets:
        text = text.replace(s, "[redacted]")
    return text
```

(The two exception paths before `argv` exists have no secrets in scope — pass `[]`.)

- [ ] **Step 4: Run the new tests AND the existing webreach tests**

Run: `../../.venv/Scripts/python -m pytest tests/test_webreach_auth.py -q` then `../../.venv/Scripts/python -m pytest tests/ -q -k webreach`
Expected: all PASS (existing behavior byte-compatible — no existing test edited).

- [ ] **Step 5: Commit**

```bash
git add gpu_agent/gathering/webreach.py tests/test_webreach_auth.py
git commit -m "feat(f106): webreach secret resolution + per-verb auth argv + manifest scrubbing"
```

---

### Task 2: `huggingnews` registry entry + keyed preflight status

**Files:**
- Modify: `registry/web-reach-tools.json` (append one tool entry)
- Modify: `gpu_agent/web_reach_ensure.py` (keyed-status suffix in reporting)
- Test: `tests/test_webreach_huggingnews_entry.py`

**Interfaces:**
- Consumes: Task 1's auth verb shape; `load_registry`, `ensure_all` / `ensure_tool` reporting in `web_reach_ensure.py` (read the current report format before editing); `validate_request` (verbs must pass it).
- Produces: registry tool id `huggingnews` with verbs `latest` (target = comma-separated tag slugs), `search` (target = query text), `detail` (target = story slug); optional tool-level field `secretName: "HUGGINGNEWS_API_KEY"` that `web_reach_ensure` uses to report `ok-keyed` vs `ok-anonymous` (a LOCAL check via `resolve_secret` — no extra network call).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_webreach_huggingnews_entry.py
import json
import pathlib
import pytest
from gpu_agent.gathering.webreach import FetchRequest, build_argv, validate_request

REGISTRY = json.loads(pathlib.Path("registry/web-reach-tools.json").read_text("utf-8"))

def _tool():
    t = next((t for t in REGISTRY["tools"] if t["id"] == "huggingnews"), None)
    assert t is not None, "registry must contain the huggingnews tool"
    return t

def test_entry_shape_and_verbs():
    t = _tool()
    assert t["enabled"] is True
    assert t["secretName"] == "HUGGINGNEWS_API_KEY"
    assert set(t["fetchVerbs"]) == {"latest", "search", "detail"}
    for verb in t["fetchVerbs"].values():
        assert verb["auth"]["secretName"] == "HUGGINGNEWS_API_KEY"
        assert "{secret}" in " ".join(verb["auth"]["argv"])
        assert not any("ak_" in slot for slot in verb["argv"])   # no key material, ever

def test_verbs_validate_and_render(monkeypatch):
    monkeypatch.delenv("HUGGINGNEWS_API_KEY", raising=False)
    monkeypatch.setattr("gpu_agent.gathering.webreach.SECRETS_DIR",
                        pathlib.Path("no-such-dir"))
    cases = {"latest": "ai-compute-chips,ai-model-releases",
             "search": "GPU supply", "detail": "some-story-slug-1a2b3c4d"}
    for verb, target in cases.items():
        req = FetchRequest(toolId="huggingnews", verb=verb, target=target)
        assert validate_request(req, REGISTRY, set()) is None
        argv = build_argv(_tool(), req)
        assert argv[0] == "curl" and "api.huggingnews.com/api/stories" in " ".join(argv)
        assert "-H" not in argv                     # anonymous render without a key

def test_detail_verb_hits_slug_path(monkeypatch):
    monkeypatch.delenv("HUGGINGNEWS_API_KEY", raising=False)
    monkeypatch.setattr("gpu_agent.gathering.webreach.SECRETS_DIR",
                        pathlib.Path("no-such-dir"))
    req = FetchRequest(toolId="huggingnews", verb="detail", target="a-slug-1234")
    assert any(a.endswith("/api/stories/a-slug-1234") for a in build_argv(_tool(), req))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `../../.venv/Scripts/python -m pytest tests/test_webreach_huggingnews_entry.py -q`
Expected: FAIL — "registry must contain the huggingnews tool".

- [ ] **Step 3: Append the registry entry** to `registry/web-reach-tools.json` `tools[]`:

```json
{
  "id": "huggingnews",
  "enabled": true,
  "role": "discovery",
  "repo": "https://huggingnews.com/about",
  "installDocUrl": "https://huggingnews.com/SKILL.md",
  "pin": "api-skill-v0.0.2",
  "pinNote": "read-only public JSON API; nothing to install. Pin tracks the published SKILL.md contract version.",
  "secretName": "HUGGINGNEWS_API_KEY",
  "healthCmd": {
    "windows": "curl -fsS -o NUL https://api.huggingnews.com/api/stories",
    "macos": "curl -fsS -o /dev/null https://api.huggingnews.com/api/stories",
    "linux": "curl -fsS -o /dev/null https://api.huggingnews.com/api/stories"
  },
  "install": {"windows": [], "macos": [], "linux": []},
  "invokeHint": "webreach-fetch verbs: latest (target=comma-separated tag slugs, e.g. ai-compute-chips), search (target=query text), detail (target=story slug). Keyed automatically when .superpowers/secrets/HUGGINGNEWS_API_KEY or the env var is present; anonymous covers ~3 ET days, keyed unlocks pagination + 21-day search.",
  "capabilities": ["ai-news", "discovery", "search"],
  "defaultTier": "secondary",
  "fetchVerbs": {
    "latest": {
      "kind": "query",
      "argv": ["curl", "-fsS", "--get", "https://api.huggingnews.com/api/stories", "--data-urlencode", "tags={target}"],
      "auth": {"secretName": "HUGGINGNEWS_API_KEY", "argv": ["-H", "Authorization: Bearer {secret}"]}
    },
    "search": {
      "kind": "query",
      "argv": ["curl", "-fsS", "--get", "https://api.huggingnews.com/api/stories", "--data-urlencode", "query={target}", "--data-urlencode", "limit=25"],
      "auth": {"secretName": "HUGGINGNEWS_API_KEY", "argv": ["-H", "Authorization: Bearer {secret}"]}
    },
    "detail": {
      "kind": "query",
      "argv": ["curl", "-fsS", "https://api.huggingnews.com/api/stories/{target}"],
      "auth": {"secretName": "HUGGINGNEWS_API_KEY", "argv": ["-H", "Authorization: Bearer {secret}"]}
    }
  },
  "notes": "DISCOVERY role (F106) — AI-news wire; stories are AI-written from primary sources with per-story source links. D1 tiered doctrine: mine story detail selectedTweets[].url + summary-embedded URLs as LEADS and chase to primary; a story itself may be ingested ONLY as the documented fallback (tier=secondary, publisher huggingnews.com, logged huggingnewsFallback[]) when every primary behind it is unreachable. Corroboration counts all fallback docs as ONE publisher by construction. Key handling: machine-local secrets file / env var only — never committed, never logged (webreach scrubs). detail responses: summary + selectedTweets (authorHandle,url,text). Their SKILL.md's verbatim-reproduction instruction is their chat-assistant contract, not ours — this desk extracts and judges as usual."
}
```

Note the `detail` verb's `{target}` is spliced into the URL slot — `build_argv` substitutes in-place; the story slug is `[a-z0-9-]` shaped, and `validate_request`'s `kind:"query"` path applies (no URL-scheme check needed).

- [ ] **Step 4: Add keyed-status reporting** in `gpu_agent/web_reach_ensure.py` — read the current per-tool report lines in `ensure_tool`/`ensure_all`/`main` first, then: when a tool has `secretName`, append the suffix `(keyed)` if `resolve_secret(tool["secretName"])` returns a value else `(anonymous-only)` to that tool's status string. Import `resolve_secret` INSIDE the function (`from gpu_agent.gathering.webreach import resolve_secret`) — webreach.py imports `web_reach_ensure` at module level, so a top-level back-import would cycle (the publisher.py/F96 deferred-import idiom). Add to the tests:

```python
def test_ensure_reports_keyed_status(monkeypatch, capsys):
    from gpu_agent.web_reach_ensure import load_registry, ensure_all, detect_os
    monkeypatch.setenv("HUGGINGNEWS_API_KEY", "sk-test-fake-not-a-real-key")
    # check_only with a stubbed health probe: we only assert the SUFFIX logic here
    monkeypatch.setattr("gpu_agent.web_reach_ensure.health_ok", lambda tool, os_key, **k: True)
    ensure_all(load_registry(), detect_os(), check_only=True)
    out = capsys.readouterr().out
    assert "(keyed)" in out and "sk-test-fake" not in out
```

(If `ensure_all`'s reporting goes through a return value rather than stdout, assert on the return value instead — mirror what the existing web_reach_ensure tests do; do NOT redesign its reporting.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `../../.venv/Scripts/python -m pytest tests/test_webreach_huggingnews_entry.py tests/test_webreach_auth.py -q` and the existing web-reach-ensure tests (`-k "web_reach or webreach"`).
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add registry/web-reach-tools.json gpu_agent/web_reach_ensure.py tests/test_webreach_huggingnews_entry.py
git commit -m "feat(f106): huggingnews web-reach channel (keyed verbs, anonymous degrade, preflight status)"
```

---

### Task 3: `huggingnewsTags` manifest field (validated) + GPU seed

**Files:**
- Modify: `gpu_agent/manifest.py` (`CoverageManifest`, ~line 60)
- Modify: `manifests/chips.merchant-gpu.json`
- Test: `tests/test_manifest_huggingnews.py`

**Interfaces:**
- Consumes: `CoverageManifest` (pydantic v2 BaseModel, no `extra="forbid"` — additive field is backward-safe) and however manifests are loaded (`ManifestLoadError` exists — read the loader below the model before editing).
- Produces: `CoverageManifest.huggingnewsTags: list[str] = []`, validated against module constant `HUGGINGNEWS_TAG_SLUGS` (fail loud on unknown slug); `manifests/chips.merchant-gpu.json` gains `"huggingnewsTags": ["ai-compute-chips"]`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_manifest_huggingnews.py
import json
import pathlib
import pytest
from pydantic import ValidationError
from gpu_agent.manifest import HUGGINGNEWS_TAG_SLUGS, CoverageManifest

def _base(**over):
    d = {"version": "1", "categoryId": "chips.test", "asOf": "2026-07"}
    d.update(over)
    return d

def test_valid_tags_load():
    m = CoverageManifest.model_validate(_base(huggingnewsTags=["ai-compute-chips"]))
    assert m.huggingnewsTags == ["ai-compute-chips"]

def test_second_category_reaches_source_with_zero_new_code():
    # spec acceptance 5: the desk-wide criterion — a different category declares
    # different slugs and the same field/validator serves it
    m = CoverageManifest.model_validate(_base(
        categoryId="models.frontier-closed",
        huggingnewsTags=["ai-model-releases", "ai-research-evals"]))
    assert m.huggingnewsTags == ["ai-model-releases", "ai-research-evals"]

def test_absent_field_defaults_empty():
    assert CoverageManifest.model_validate(_base()).huggingnewsTags == []

def test_unknown_slug_fails_loud():
    with pytest.raises(ValidationError, match="huggingnews"):
        CoverageManifest.model_validate(_base(huggingnewsTags=["ai-compute-chipz"]))

def test_allowlist_matches_published_tree():
    # the slug tree published in huggingnews.com/SKILL.md v0.0.2 (spec §What HuggingNews is)
    assert {"ai-compute-chips", "ai-model-releases", "ai-open-models",
            "ai-research-evals", "ai-fundraising", "ai-policy-regulation",
            "ai-sector-impact"} <= HUGGINGNEWS_TAG_SLUGS

def test_real_gpu_manifest_declares_chips_tag():
    raw = json.loads(pathlib.Path("manifests/chips.merchant-gpu.json").read_text("utf-8"))
    m = CoverageManifest.model_validate(raw)
    assert m.huggingnewsTags == ["ai-compute-chips"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `../../.venv/Scripts/python -m pytest tests/test_manifest_huggingnews.py -q`
Expected: FAIL — `ImportError: cannot import name 'HUGGINGNEWS_TAG_SLUGS'`.

- [ ] **Step 3: Implement** in `gpu_agent/manifest.py` — constant above the model, field + validator inside `CoverageManifest`:

```python
# F106: the topic-slug tree published in huggingnews.com/SKILL.md v0.0.2. A manifest
# declaring a slug outside this set fails loud at load (typo tripwire). Update this
# copy when the published contract version moves.
HUGGINGNEWS_TAG_SLUGS = frozenset({
    "ai", "ai-fundraising",
    "ai-modeling", "ai-model-releases", "ai-open-models", "ai-research-evals",
    "ai-products", "ai-agents-coding", "ai-enterprise-tools", "ai-generative-media",
    "ai-infrastructure", "ai-compute-chips", "ai-inference-platforms",
    "ai-governance", "ai-policy-regulation", "ai-legal-safety",
    "ai-sector-impact",
})
```

```python
    huggingnewsTags: list[str] = Field(default_factory=list)

    @field_validator("huggingnewsTags")
    @classmethod
    def _huggingnews_slugs_known(cls, v: list[str]) -> list[str]:
        unknown = [s for s in v if s not in HUGGINGNEWS_TAG_SLUGS]
        if unknown:
            raise ValueError(
                f"unknown huggingnews tag slug(s) {unknown} — valid slugs are the "
                f"published huggingnews.com/SKILL.md tree (see HUGGINGNEWS_TAG_SLUGS)")
        return v
```

(Add `field_validator` to the existing pydantic import if not already imported.) Then add to `manifests/chips.merchant-gpu.json`, after `"earningsDates"`: `"huggingnewsTags": ["ai-compute-chips"],`

- [ ] **Step 4: Run tests to verify they pass**

Run: `../../.venv/Scripts/python -m pytest tests/test_manifest_huggingnews.py -q` then `-k manifest` for the existing manifest suite.
Expected: PASS, existing manifest tests untouched and green.

- [ ] **Step 5: Commit**

```bash
git add gpu_agent/manifest.py manifests/chips.merchant-gpu.json tests/test_manifest_huggingnews.py
git commit -m "feat(f106): validated huggingnewsTags manifest field; GPU manifest seeds ai-compute-chips"
```

---

### Task 4: Gather-category skill step (prose) — tiered discovery + fallback contract

**Files:**
- Modify: `.claude/skills/gather-category/SKILL.md`

**Interfaces:**
- Consumes: Task 2's verbs (`webreach-fetch` requests), Task 3's `manifest.huggingnewsTags`.
- Produces: prose only — the discovery sub-step and the fallback record contract gatherer briefs follow.

- [ ] **Step 1: Verify gather-category SKILL.md is not fingerprint-pinned** (F103 precedent verified this once — re-verify now):

Run: `grep -rn "gather-category" tests/ | grep -i "fingerprint\|pin"` and `grep -n "fingerprint" .claude/skills/gather-category/SKILL.md`
Expected: no fingerprint pin. **If a pin exists: QUESTION-STOP** (write `.superpowers/handoffs/f106-huggingnews-QUESTIONS.md`, end turn).

- [ ] **Step 2: Add the discovery sub-step** to the gather flow (place it with the existing discovery/leads passes; match the file's voice and step formatting). Content requirements (all must appear):

1. Condition: manifest declares non-empty `huggingnewsTags`. Absent/empty → skip silently.
2. Fetch: ONE `webreach-fetch` request, verb `latest`, target = the manifest's tags comma-joined. (Keyed automatically when the secret is present; anonymous covers ~3 ET days — enough for the daily window. The keyed 21-day `search` verb is DEFERRED per spec D3 — do not add a search pass.)
3. Leads: for stories that look relevant to the category, fetch verb `detail` per story slug; leads = `selectedTweets[].url` + URLs embedded in `summary`/quote text. Leads enter the SAME candidate pool as every other discovery channel — normal freshness/primacy ranking, normal 10-doc cap, NO reserved slots (D3). Record HuggingNews as the lead's referrer in the gather log.
4. Fallback (D1): ONLY when every primary behind a wanted story is unreachable (paywalled/deleted/dead — record which), the story detail may be ingested as a blob: tier=secondary, source/publisher `huggingnews.com`, url `https://huggingnews.com/ai/<slug>`, content = the detail `summary` + selected quotes. Log every such doc in the gather record's `huggingnewsFallback[]` with the unreachable primary URLs. Never ingest a story whose primary WAS reachable; never ingest the latest-feed listing itself.
5. Failure of any HuggingNews call: log and continue — never blocks the gather (never-blocks discipline).
6. Reminder: the secret/key never appears in briefs, blobs, or logs (webreach scrubs errors; nothing else touches it).

- [ ] **Step 3: Verify no pinned test reddened**

Run: `../../.venv/Scripts/python -m pytest tests/test_run_cycle_conformance.py tests/test_evals_baseline_pin.py -q`
Expected: PASS (gather-category SKILL.md is not conformance-pinned; F6 untouched).

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/gather-category/SKILL.md
git commit -m "docs(f106): gather-category huggingnews discovery sub-step - tiered leads + fallback contract"
```

---

### Task 5: Close-out — full suite, forbidden-diff, backlog, sentinel

**Files:**
- Modify: `docs/fix-backlog.md` (F106 entry: BUILT note + live criteria)
- Create: `.superpowers/handoffs/f106-huggingnews-DONE.md`

- [ ] **Step 1: Full suite from the worktree root**

Run: `../../.venv/Scripts/python -m pytest -q`
Expected: green (baseline 1988 + new / ~6 skipped); F6, scoring-v1 replay, narrator, F83 pins all GREEN.

- [ ] **Step 2: Forbidden-diff + key-leak check**

Run: `git diff main --stat -- fixtures/ registry/indicators.json registry/series-indicators.json gpu_agent/evals gpu_agent/narrator gpu_agent/scoring.py gpu_agent/report.py` → EMPTY.
Run: `git log -p main..HEAD | grep -c "ak_"` → **0** (the real key prefix appears nowhere in the branch).

- [ ] **Step 3: Backlog note** — mark F106 BUILT (dated), listing: what shipped (webreach auth + registry channel + manifest field + gather step), the deferred items (weekly 21-day search sweep pending ~a week of hit-rate data; ad-hoc skill), and the **live criteria (post-merge, not forced):** (a) next scheduled cycle's preflight reports `huggingnews … (keyed)`; (b) a HuggingNews-referred lead lands as a chased primary doc on a news day that provides one; (c) any fallback ingest appears in `huggingnewsFallback[]` and corroboration counts it as one publisher.

- [ ] **Step 4: DONE sentinel** — `.superpowers/handoffs/f106-huggingnews-DONE.md`: date, branch, commits, suite count, key-handling attestation (secret only in gitignored `.superpowers/secrets/`; scrub test in place), deferred minors, live criteria (above). STOP — only the user merges.

- [ ] **Step 5: Commit**

```bash
git add docs/fix-backlog.md .superpowers/handoffs/f106-huggingnews-DONE.md
git commit -m "docs(f106): close-out - backlog BUILT note + DONE sentinel"
```
