# F106 — HuggingNews as a desk-wide news source (design)

**Date:** 2026-07-28 · **Status:** user-approved design (interactive brainstorm, zero AFK)
**Backlog:** F106. **Relates to:** F104 (social ingestion — shares the web-reach path; separate lane).

## What HuggingNews is (scouted live 2026-07-28)

An AI-news wire (huggingnews.com) whose stories are AI-written from primary source material
(X posts, announcements, filings, papers), each carrying topic tags, a `summary`, and
`selectedTweets[]` source links. Read-only JSON API (contract published at
`huggingnews.com/SKILL.md`, v0.0.2):

- `GET api.huggingnews.com/api/stories` — latest feed (`dayGroups[]`); anonymous covers 3 ET days;
  authenticated (`Authorization: Bearer $HUGGINGNEWS_API_KEY`) unlocks pagination via
  `beforeDayKey`/`nextBeforeDayKey`.
- `GET …/api/stories?query=…&limit=1..50` — search; keyed search covers the latest 21 ET days;
  responses carry `truncated`.
- `GET …/api/stories?tags=a,b` — fine-grained topic filter (parent slugs match descendants);
  relevant slugs include `ai-compute-chips`, `ai-model-releases`, `ai-open-models`,
  `ai-research-evals`, `ai-fundraising`, `ai-policy-regulation`, `ai-sector-impact`.
- `GET …/api/stories/<slug>` — story detail: story fields + `summary` + `selectedTweets[]`
  (`authorHandle`, `url`, `tweetedAt`, `text`, `quotedTweetText`).
- Site pages require a browser User-Agent (agent UAs get 403); the API host does not.
- Note: their SKILL.md's instruction to reproduce titles/summaries verbatim is THEIR contract for
  chat assistants — this desk's pipeline does its own extraction and judgment; we treat API
  responses as data.

## Decisions (all user picks, interactive 2026-07-28)

| # | Question | Decision |
|---|----------|----------|
| D1 | Pipeline role | **Tiered (option 3):** chase story source links to PRIMARY sources; fall back to ingesting the story itself as a MARKED secondary doc only when the primary is unreachable |
| D2 | Access mechanism | **Web-reach registry channel + per-manifest tag mapping** (vs standalone skill, vs both) — the "any agent" requirement is solved by configuration, not per-agent code |
| D3 | Cadence & budget | **Every daily cycle, competing on merit inside the existing 10-doc cap; no reserved slots.** Weekly keyed 21-day deep-search sweep DEFERRED until ~a week of hit-rate data |

## Design

### 1. Key handling (hard rule)

The API key lives ONLY in the machine-local gitignored file
`.superpowers/secrets/HUGGINGNEWS_API_KEY` (verified ignored). The registry entry, manifests,
prompts, briefs, cycle logs, and commits carry the env-var NAME at most — never the value. Fetch
code reads the secrets file (or an already-set `HUGGINGNEWS_API_KEY` env var, which wins) at
request time. A missing key is a DEGRADED state (anonymous 3-day coverage), reported by preflight —
never a crash, never silent.

### 2. Registry channel

`registry/web-reach-tools.json` gains a `huggingnews` entry: API base, the three verbs
(`latest`, `search`, `detail`) with their parameter shapes, the auth env-var name, and a health
probe (one cheap anonymous `GET /api/stories`; keyed probe adds a `hasMore:true` check to prove the
key works). `webreach-fetch` executes the requests (argv-exec, sanitized result paths, recorded
fetch manifest — the existing discipline), so every HuggingNews call is auditable in the cycle
record. `scripts/web-reach-ensure` reports `huggingnews: ok-keyed | ok-anonymous | off`.

### 3. Manifest tag mapping

Category manifests gain an optional `huggingnewsTags: [slug, …]` field (validated against a small
allowlist copied from the API's published slug tree — a wrong slug fails loud at manifest load).
`manifests/chips.merchant-gpu.json` seeds `["ai-compute-chips"]`. A manifest without the field
simply doesn't use the source. No other per-category code.

### 4. Gather integration (tiered, merit-based)

In the daily cycle's discovery pass, when the manifest declares tags:

1. Fetch latest stories for the tags (~2-day window — the anonymous window; keyed pagination only
   if the cycle date demands more).
2. Each story's leads = `selectedTweets[].url` plus any URLs embedded in the detail `summary` /
   quote text (the only link-bearing fields the API returns). These become LEADS, entering the
   same candidate pool as every other discovery channel; the existing freshness/primacy ranking
   decides which win slots in the 10-doc cap. Chased primaries are snapshotted and tiered exactly
   as today (a chased NVIDIA blog post is a primary doc; HuggingNews's role is recorded as the
   lead's referrer in the gather log).
3. FALLBACK (D1): if every primary behind a story is unreachable (paywalled, deleted, dead), the
   story detail (`summary` + quotes) MAY be ingested as a document: tier=SECONDARY,
   publisher/source domain = `huggingnews.com`, url = the story permalink
   (`huggingnews.com/ai/<slug>`), flagged in the gather log's `skipped[]`-sibling record
   (`huggingnewsFallback[]`, with the unreachable primary URLs listed). Because the publisher key
   IS the domain, corroboration structurally counts ALL fallback docs as ONE publisher — a
   restatement can never pose as an independent source. The existing judge rule "secondary-only
   evidence cannot support high confidence" applies unchanged.

### 5. Explicitly out of scope (deferred)

- Weekly 21-day deep-search sweep (revisit with hit-rate data; D3).
- An interactive ad-hoc skill (option-2 half of the mechanism question).
- Any brain/prompt awareness of the source: gather-side only — extract/judge/thesis/implication/
  narrator prompts, `gpu_agent/evals`, `fixtures/`, `registry/indicators.json` all byte-untouched.
  **Non-gated lane; F6 / scoring replay / narrator pins stay green.** If the gather-category
  SKILL.md gains a step (likely), the F83-style fingerprint story for THAT skill is checked in-plan
  (gather-category SKILL.md is NOT fingerprint-pinned per the F103 verification — re-verify at
  plan time).

## Acceptance

1. Preflight reports `huggingnews: ok-keyed` on this machine; deleting the secrets file flips it
   to `ok-anonymous` (degraded), never a crash.
2. A daily cycle on the GPU category logs HuggingNews-referred leads competing in the normal pool;
   at least one chased primary lands as a normal primary doc when the news day provides one.
3. A forced-unreachable-primary test produces a fallback doc: tier=secondary, publisher
   `huggingnews.com`, logged in `huggingnewsFallback[]`; corroboration counts it as one publisher.
4. The key appears nowhere in `git log -p` output for the lane, in emitted prompts, or in the
   cycle log.
5. A second category manifest with `huggingnewsTags` (fixture-level is fine) reaches the source
   with zero new code — the desk-wide criterion.

## Decision provenance

D1–D3 user picks, interactive 2026-07-28. Assistant-settled mechanical details (flagged, tunable):
the ~2-day daily window, the slug allowlist copy, the `huggingnewsFallback[]` log-record name, and
the keyed-probe design. The key was user-provided in-session; storage location is the assistant's
pick of the repo's existing gitignored area.
