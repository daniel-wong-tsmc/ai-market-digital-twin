# F117 + F126 — one do-not-fetch registry, two kinds

**Date:** 2026-08-25
**Branch:** `f117-f126-fetch-registry` (based on main @ `f6d61f9`)
**Backlog items:** F117 (rule 8's blocking list is a registry lookup, and the registry is
missing the domains that actually block) + F126 (publisher do-not-fetch list wired into
the fetch runner), plus the still-open **F116 tail** (the verifier reports a 403 as
"number not found" rather than "blocked source").

---

## 1. The problem, in plain words

Two different things make a domain one we should not read, and today the desk has a name
for neither.

1. **A publisher asked us not to.** Posture doc §3(4) already DECIDED that a domain-level
   objection stops future fetching. Nothing in code carries that list, so an objection
   would have to be honoured by memory. No publisher has ever objected — this is a plan,
   not a history — but the plumbing has to exist before the first letter arrives, not
   after.
2. **The site turns our plain reader away.** On the 2026-08-19 cycle a researcher cited
   `counterpointresearch.com` for five points. Its own WebFetch opened the page cleanly
   three times. The verifier's plain reader got HTTP 403 on all five, and the whole
   candidate died. Rule 8 warned about *licensed* publishers, so it never mentioned this
   one — and the researcher had no way to find out, because **its fetcher and the
   verifier's fetcher are different readers**. "I checked and it opens" is not evidence.

The F116 tail makes both worse: a 403 comes back through the verifier as "unreachable",
indistinguishable from a DNS failure or a timeout, so nothing downstream can learn from it.

## 2. What we are building

One file — `registry/do-not-fetch.json` — with an entry per domain carrying a `kind`:

| kind | who puts it there | what it means |
| --- | --- | --- |
| `publisher-objection` | a human, after an objection | **Never fetch. Never cite.** Hard refusal everywhere. |
| `blocks-plain-readers` | a human, or the verifier learning from a 401/403/429 | **The plain reader can't get in.** Gatherers may still read it; the verifier still tries; a researcher is told to treat it as unavailable. |

Seeded with `counterpointresearch.com` as `blocks-plain-readers`. No
`publisher-objection` entry exists — the kind is fully wired anyway, so the first
objection is a one-line edit, not a build.

`registry/licensed-sources.json` is left exactly as it is. It means something different
(publishers whose material we hold a licence to) and D6 deliberately stopped it being a
refusal list.

### File shape

```json
{
  "version": 1,
  "entries": [
    {
      "domain": "counterpointresearch.com",
      "kind": "blocks-plain-readers",
      "since": "2026-08-19",
      "why": "HTTP 403 to the verifier's plain reader on all 5 points, 2026-08-19 cycle; opened fine to the researcher's WebFetch"
    }
  ]
}
```

Sorted by domain. Learned entries add `firstSeenUrl` (the page that first proved the
block) after `why`; the seed has no `firstSeenUrl` because a human recorded it, not a
fetch. Key order is fixed — `domain`, `kind`, `since`, `why`, `firstSeenUrl` — and the
file is written with LF newlines and a trailing newline so a learned append is a
one-line diff, not a reformat.

## 3. Where the code goes

A new stdlib-only leaf module, **`gpu_agent/fetch_policy.py`**: "who we may fetch, and
who we must not". It is a leaf on purpose — the verifier (`gpu_agent/chartdata/`), the
fetch runner (`gpu_agent/gathering/webreach.py`) and the researcher's prompt builder all
import it, and none of them may drag the others' dependencies (pydantic, subprocess)
along.

It exports:

- `matching_domain(target, domains) -> str | None` — **the** host matcher: exact host or
  dot-suffix subdomain, reading `parsed.hostname` so `user:pass@host` cannot hide the
  real host, returning `None` for anything that is not an http(s) URL. This is
  `webreach.licensed_source_host`'s body, lifted here so there is one copy;
  `licensed_source_host` becomes a thin delegate keeping its name, docstring intent and
  every existing call site and test working.
- `DoNotFetchRegistry` — the loaded file. `.match(target, kind=None) -> Entry | None`,
  `.domains(kind) -> list[str]`, `.is_empty`.
- `load_do_not_fetch(path=DO_NOT_FETCH_REGISTRY) -> DoNotFetchRegistry` — a missing
  file, unreadable file, or malformed JSON returns an **empty** registry. A registry
  that can strand a cycle is worse than no registry, so this never raises. Entries with
  an unknown `kind` or a blank `domain` are dropped from `entries` rather than trusted,
  but kept verbatim in `rows`. A file that is **present but unparseable** comes back
  flagged `unreadable=True` — reads carry on, writers must not.
- `record_blocked_domain(path, domain, *, since, first_seen_url) -> bool` — idempotent
  append of a `blocks-plain-readers` entry. Returns `False` and touches nothing if the
  file is unreadable, or if the domain is already covered under **either** kind (matched
  the same exact-host-or-subdomain way every read path matches, so one blocking site
  cannot grow an entry per subdomain; and an objection is never quietly downgraded to a
  block). Existing rows and the document's other top-level keys are written back
  verbatim. The write is atomic (temp file + rename). Never raises: a read-only checkout
  must not break a cycle.

**Why the unreadable flag matters (code review, 2026-08-25 — a data-loss path).** The
loader turning every parse failure into an empty registry is right for readers and fatal
for writers: rebuilding the file from an empty list would erase every publisher objection
on record the first time a stray comma met a learned domain. Distinguishing "absent" from
"present but unparseable" is what closes it, and `accept_research` reports the unreadable
case in its summary so a fail-open is never a silent one.

## 4. Enforcement, seam by seam

### 4.1 The fetch runner — `gpu_agent/gathering/webreach.py`

`validate_request(req, registry, licensed_domains, do_not_fetch=None)`. A
`publisher-objection` match refuses with exactly:

```
refused: publisher objection (<domain>)
```

`blocks-plain-readers` does **not** refuse — gatherers read those pages for claims all
the time, and the block is about the verifier's reader, not about permission.
`run_requests` gains the same optional parameter and passes it down; a refused row keeps
its reason in `refused` and `licensedSource: None`, exactly as today. Every existing
positional call site stays valid because the new parameter is optional and defaults to
an empty registry.

### 4.2 The verifier — `gpu_agent/chartdata/verify.py`

**Before any fetch**, alongside the existing scheme and unreachable-host pre-checks, a
`publisher-objection` host is rejected outright:

```
point 3: counterexample.test is on the do-not-fetch list (publisher objection) (https://...)
```

**F116 tail — failure lines that say what happened.** Today every fetch exception
becomes `"<url> unreachable (<Type>: <msg>)"`. The wrapper now classifies:

| what happened | failure line |
| --- | --- |
| `HTTPError` 401 / 403 / 429 | `point 1: <url> blocked (HTTP 403)` |
| `HTTPError` 404 | `point 1: <url> not found (HTTP 404)` |
| known `blocks-plain-readers` domain, any other failure | `point 1: <url> blocked (known to turn plain readers away; <Type>: <msg>)` |
| anything else | `point 1: <url> unreachable (<Type>: <msg>)` — unchanged |

Classification reads `urllib.error.HTTPError.code`, so a test's injected `fetch_html`
raises a real `HTTPError` and is classified identically to the live path. The per-call
page cache stores a small `FetchFailure` record (kind, status, text) instead of a bare
string, so the same failure is classified once however many points share the page.

**Auto-learn.** `verify_candidate` stays a pure decision function returning
`(ok, failures)`. It gains an optional `on_blocked(domain, url)` callback, invoked once
per blocked domain. `accept_research` supplies a callback that calls
`record_blocked_domain` against **the same path it loaded the registry from**, so a
custom `--do-not-fetch` never reads one file and writes another.

**The `since` date is the story date, not the wall clock.** This module's standing rule
is that records it writes carry no wall-clock field, so a rerun of a cycle is
byte-identical. `accept_research` already resolves the story date; a learned entry
inherits it. Rerunning a cycle re-learns nothing (idempotent) and, if it did, would
write the same bytes.

`accept_research(..., do_not_fetch_path=None)` defaults to `registry/do-not-fetch.json`;
missing means empty, and learning is simply skipped when nothing can be written.

### 4.3 The researcher's brief — `gpu_agent/chartdata/research_prompt.py`

Rule 8 keeps everything it says today and gains the two things F117 found:

1. **Your own fetch proves nothing.** Stated plainly: the machine that re-checks is a
   different reader with different access, so a page that opens for you can still refuse
   it. This is the real fix — the list will always lag, the principle will not.
2. **The two named lists**, read from `registry/do-not-fetch.json` at build time (same
   pattern as the licensed list — missing file means a generic warning, never a crash):
   publishers who asked not to be used (**never cite**), and sites known to turn the
   plain reader away (**treat as unavailable**). The registered-licensed-publisher list
   stays.

### 4.4 The CLI — `gpu_agent/cli.py`

- `webreach-fetch` gains `--do-not-fetch` (default `registry/do-not-fetch.json`), loads
  it, passes it to `run_requests`.
- `chart-research` gains `--do-not-fetch` (same default) on both actions:
  `accept` passes it to `accept_research` as both the pre-check source and the auto-learn
  target, and `emit` threads it through `emit_research` to `build_research_prompt` so
  rule 8 names the domains from the file the operator actually asked for. (Code review
  caught that the flag was originally accepted by `emit` and then ignored.)

Both default to the repo-relative path and treat a missing file as empty, so a worktree,
an odd cwd, or a stripped-down machine degrades to today's behaviour rather than
crashing a cycle.

## 5. What this does NOT do

- **No pre-flight fetch for researchers.** F117 listed "expose the verifier's own fetch
  as a pre-flight" as a candidate fix. Research agents are WebFetch-only by dispatch
  (`.claude/agents/web-gatherer.md` pattern) — they have no shell, so they cannot call
  the verifier's reader at all. Telling them plainly that their own fetch proves nothing
  is the honest fix available; the pre-flight stays open.
- **No promotion path from learned to human-curated.** A learned
  `blocks-plain-readers` entry sits in the same file a human edits. That is deliberate
  (one list, one place to look), and the `firstSeenUrl` field is what tells the two
  apart.
- **No unblocking.** A site that starts working again keeps its entry; the verifier still
  fetches it, so the entry costs a warning line in a brief, not a lost series. Removing
  an entry is a human edit.
- **F125 (honest removal of already-published excerpts) is untouched** — a separate item
  with its own design needed.

## 6. Pins and gates

- `tests/test_evals_baseline_pin.py` (F6, brain prompts) — chart-research is not an F6
  brain seam, so this must stay byte-untouched. Verified in-lane, not assumed.
- `tests/test_run_cycle_conformance.py` (F83) — pins the run-cycle SKILL's step titles.
  No skill edit in this lane, so untouched.
- `tests/test_chart_research.py` — the rule-8 assertions are substance checks
  (`trendforce.com` present, `verif` present), not a byte fingerprint, so a longer rule 8
  keeps them green. New assertions are added beside them.
- Full suite baseline on main: **2660 passed, 6 skipped**.

## 7. Decision provenance

| Decision | Source |
| --- | --- |
| One file, two kinds; `registry/do-not-fetch.json`; the seed entry and its wording | User, interactive, 2026-08-25 |
| Auto-learn on 401/403/429 into that same file, idempotent, sorted | User, interactive, 2026-08-25. The user's raw wording named `registry/blocked-readers.json`; they also chose "one file, two kinds". **Coordinator reconciliation:** one file, `registry/do-not-fetch.json`, learned entries appended there. |
| `publisher-objection` = hard refusal everywhere; `blocks-plain-readers` = verifier still tries | User, interactive, 2026-08-25 |
| Rule 8 must say the researcher's own fetch proves nothing | User, interactive, 2026-08-25 |
| New leaf module named `fetch_policy.py`, and `licensed_source_host` delegating to its `matching_domain` | AFK-default (mechanical). The user required "reuse, don't duplicate" the matcher; a stdlib-only leaf is the only place all three importers can share it. |
| Learned `since` = the story date, not the wall clock | AFK-default (mechanical). Follows verify.py's standing no-wall-clock rule so cycle reruns stay byte-identical. |
| 404 gets its own `not found (HTTP 404)` line | AFK-default. The user asked for blocked vs not-found vs unreachable; 404 is the not-found case. |
| A domain already listed as `publisher-objection` is never downgraded by auto-learn | AFK-default (safety). An objection outranks a technical block. |
| Rule 8 lists a kind only when that kind has domains in it | AFK-default. The brief names both kinds and says what to do with each, but an empty list produces no text — telling a researcher about an empty list is noise. The `publisher-objection` half is tested against a registry that has one. |
| A trailing-dot FQDN (`trendforce.com.`) is normalised on both sides of the matcher | AFK-default (safety). Found by self-review: it named the same host every resolver would reach, so typing the dot walked past a refusal. |
| An unreadable registry blocks the learned WRITE but not the reads | AFK-default (code review, Critical). Reads must fail open so a cycle never dies over a policy file; writes must fail closed so a damaged file is never rebuilt from nothing. |
| `warnings` added to `accept_research`'s returned summary | AFK-default (code review, Minor). Fail-open must not be silent. This changes that function's returned shape; one existing test pinned it and was updated. |
