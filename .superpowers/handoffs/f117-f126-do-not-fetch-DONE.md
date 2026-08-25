# F117 + F126 — do-not-fetch registry — DONE

**Date:** 2026-08-25
**Branch:** `f117-f126-fetch-registry` (worktree `.worktrees/f117-f126-fetch-registry`,
based on main @ `f6d61f9`)
**Status:** built, reviewed, green. **NOT merged, NOT pushed.** `main` untouched.

## What shipped

One registry file, `registry/do-not-fetch.json`, with a `kind` on every entry:

- **`publisher-objection`** — the publisher asked not to be used at all (posture doc
  §3(4)). Hard refusal: `webreach.validate_request` refuses with
  `refused: publisher objection (<domain>)` before argv is built, and the chart verifier
  rejects any point citing such a domain before a single request goes out.
- **`blocks-plain-readers`** — the site turns the chart verifier's plain reader away.
  NOT a refusal in the fetch runner (gatherers still read those pages for claims). The
  verifier still fetches, because a site may recover, but a failed fetch says *blocked*.

Seeded with `counterpointresearch.com` (`since: 2026-08-19`). **No `publisher-objection`
entry exists** — no publisher has ever objected. The kind is fully wired and tested; the
first objection is a one-line edit, not a build.

Also in this lane:

- **F116 tail.** Verifier failure lines now read `blocked (HTTP 401|403|429)`,
  `not found (HTTP 404)`, `blocked (known to turn plain readers away; …)`, or the
  original `unreachable (…)`. They all used to say "unreachable".
- **Auto-learn.** Any 401/403/429 the verifier meets appends a `blocks-plain-readers`
  entry to the same file, once per domain, `since` = the **story date** (never the wall
  clock, so a cycle rerun is byte-identical).
- **Rule 8** now states plainly that the researcher's own fetch proves nothing because
  the verifier is a different reader, and names both do-not-fetch lists beside the
  licensed one.
- **CLI:** `--do-not-fetch` on `webreach-fetch` and on both `chart-research` actions,
  defaulting to `registry/do-not-fetch.json`; missing file = empty, never a failed cycle.

## Commits (oldest first)

| SHA | Message |
| --- | --- |
| `005f407` | docs(f117-f126): design for one do-not-fetch list with two kinds |
| `3ce9e9c` | docs(f117-f126): implementation plan, seven task-sized steps |
| `e8d2f7b` | feat(f117-f126): one do-not-fetch list with two kinds |
| `dcb8aa3` | feat(f117-f126): the fetch runner refuses a publisher who asked not to be used |
| `4a41699` | feat(f117-f126): the verifier says blocked when a page turns its reader away |
| `74f0f47` | feat(f117-f126): the verifier records every domain that turns its reader away |
| `b29bf7c` | feat(f117-f126): tell the researcher its own fetch proves nothing |
| `aa519dc` | feat(f117-f126): wire the do-not-fetch list into the two commands that fetch |
| `0a7af79` | docs(f117-f126): tick F117 and F126, record what stays open |
| `c6ccef0` | fix(f117-f126): a trailing dot must not dodge a refusal |
| `4c5c8fb` | fix(f117-f126): act on code review, starting with a data-loss path |
| (this file) | docs(f117-f126): completion sentinel |

## Full suite

```
2711 passed, 6 skipped, 1 warning in 265.69s (0:04:25)
```

Baseline on main was **2660 passed, 6 skipped**. This lane adds 51 tests and skips
nothing new.

## Pins — all untouched, with evidence

| Pin | Result | Evidence |
| --- | --- | --- |
| `tests/test_evals_baseline_pin.py` (F6, brain prompts) | **GREEN, byte-untouched** | Ran green after every prompt-touching commit. `git diff f6d61f9..HEAD --stat` shows no change to `tests/test_evals_baseline_pin.py` or `fixtures/evals/`. Expected: chart-research is not an F6 brain seam — the F6 pin covers extract/judge/thesis/implication/narrator, and `research_prompt.py` is deliberately unpinned by design (F113 §3, its quality mechanism is the verifier, not a fixed-text pin). |
| `tests/test_run_cycle_conformance.py` (F83 fingerprint) | **GREEN, byte-untouched** | No skill file edited in this lane; it pins `SKILL.md` step titles only. |
| `tests/test_scoring_v1_replay_pin.py` | **GREEN, byte-untouched** | Ran green; nothing in this lane touches scoring. |

**Nothing was re-recorded.** No pin moved, so no recorded recipe was invoked.

## Code review

A reviewer subagent was dispatched over `f6d61f9..0a7af79` and found one **Critical** and
three **Important** issues. All are fixed in `4c5c8fb`:

1. **Critical — a typo in the registry file silently deleted every publisher objection.**
   The loader turned any parse failure into an empty registry (correct — a cycle must not
   die over a policy file), and the writer then rebuilt the whole file from that empty
   list. One stray comma plus one learned domain would have erased every objection on
   record. Fixed: the loader now distinguishes *absent* from *present but unparseable*,
   and a learned append refuses to write when the file is unreadable.
2. **Important — a learned append dropped rows and keys it did not understand** (a
   hand-added `contact:`, a future `kind`, the document's other top-level fields). Fixed:
   everything is written back verbatim.
3. **Important — the idempotence check was exact-match while every read path matches
   subdomains**, so one blocking site could grow an entry per subdomain. Fixed: the write
   path uses the same matcher as the read paths.
4. **Important — `--do-not-fetch` on `chart-research emit` was accepted and ignored**, so
   the brief was built from a file nobody named. Fixed: the path is threaded through
   `emit_research` into `build_research_prompt`.
5. Minor — fail-open on an unreadable registry was silent. Fixed: `accept_research` now
   returns a `warnings` list (this **changes that function's returned shape**; one
   existing test pinned the old shape and was updated).
6. Minor — the module docstring claimed a matcher monopoly that was not true. Softened.
7. Minor — the CLI default test asserted on source text. Replaced with two behavioural
   tests that chdir into a temp repo and prove the default by producing a real refusal
   and a real brief.
8. Minor — the write was not atomic. Fixed: temp file + rename.

Found by self-review before the reviewer returned, fixed in `c6ccef0`: a **trailing-dot
FQDN** (`objector.test.`) walked straight past the matcher. It names the same host every
resolver would reach, so it was a genuine way to dodge a refusal. Both sides are now
normalised.

The reviewer also noted the worktree was dirty mid-review (it was reviewing `0a7af79`
while `c6ccef0` was being written). That was this same lane, not a concurrent instance.

## Coordinator reconciliation (recorded as instructed)

The user's raw wording for the auto-learn destination was **`registry/blocked-readers.json`**,
but the user also chose **"one file, two kinds"**. The coordinator reconciled these as:
one file, **`registry/do-not-fetch.json`**, with learned entries appended there under
`kind: blocks-plain-readers`. This lane implemented the reconciliation. *(Coordinator
judgment call, relayed in the lane brief — not a user decision.)*

## Judgment calls — every one an AFK-default

The user was not answering questions during this lane, so every choice below is recorded
as **AFK-default**, never as user-approved.

1. **New module named `gpu_agent/fetch_policy.py`**, holding both the shared host matcher
   and the registry. The brief required reuse of `licensed_source_host`'s matching rather
   than a duplicate; a stdlib-only leaf is the only place the fetch runner, the verifier
   and the prompt builder can all import from. `licensed_source_host` now delegates and
   keeps its name and behaviour.
2. **Learned `since` = the story date, not the wall clock.** `verify.py`'s standing rule
   is that nothing it writes carries a wall-clock field, so cycle reruns stay
   byte-identical. A learned entry obeys the same rule.
3. **404 gets its own `not found (HTTP 404)` line.** The brief asked for blocked vs not
   found vs unreachable; 404 is the not-found case.
4. **Auto-learn never downgrades a `publisher-objection` to a technical block.** An
   objection outranks a 403.
5. **Rule 8 lists a kind only when that kind has domains in it.** The brief said rule 8
   must name both kinds; with zero objections on file there is nothing to name, and
   telling a researcher about an empty list is noise. The `publisher-objection` half is
   tested against a registry that has one, so the day an objection is filed the brief
   names it.
6. **Trailing-dot hosts normalised** on both sides of the matcher (see above).
7. **Reads fail open, writes fail closed** on an unreadable registry.
8. **`warnings` added to `accept_research`'s returned dict** — a shape change to a public
   function, so flagged here explicitly.
9. **This sentinel is committed with `git add -f`.** `.superpowers/` is gitignored
   (`.gitignore:6`); the lane brief explicitly required the sentinel committed, so the
   ignore was overridden for this one file. Flagging it in case the merger would rather
   it stayed untracked.

## Rebase note

This branch is based on main @ `f6d61f9`. By the time the lane finished, main had moved
to `c6dad78` (a handoff-doc commit from another instance). Nothing in this lane touched
main, and the moved commits are documentation, but rebase before merging rather than
assuming a clean fast-forward.

## Merger notes — shared files this lane changed

Expect conflicts with any concurrent lane touching these:

| File | What this lane did |
| --- | --- |
| `gpu_agent/cli.py` | Added `--do-not-fetch` to the `webreach-fetch` and `chart-research` parsers; `_webreach_fetch` and `_chart_research` load/pass it. Two small handler edits plus two parser blocks. |
| `docs/fix-backlog.md` | Ticked F117 (~line 1927) and F126 (~line 1157), each with a DONE paragraph. **Line-number-sensitive: F117's entry is far down the file.** |
| `registry/` | **New file** `registry/do-not-fetch.json`. `registry/licensed-sources.json` deliberately untouched — it means something different (licensed publishers) and D6 stopped it being a refusal list. |
| `docs/publishing-posture.md` | §3(4) bracketed note only. The DECIDED clause text is byte-identical. |
| `gpu_agent/gathering/webreach.py` | `licensed_source_host` now delegates to the shared matcher; `validate_request` and `run_requests` take an optional `do_not_fetch` (appended last, defaults to None, so every existing call site is unchanged). |
| `gpu_agent/chartdata/verify.py` | New failure classification, do-not-fetch pre-check, auto-learn, and `warnings` in the returned summary. |
| `gpu_agent/chartdata/research.py` / `research_prompt.py` | `do_not_fetch_path` threaded through `emit_research` into `build_research_prompt`; rule 8 rewritten. |

New files (no conflict risk): `gpu_agent/fetch_policy.py`, `tests/test_fetch_policy.py`,
`tests/test_fetch_policy_cli.py`, `registry/do-not-fetch.json`, the design doc and the plan.

## What stays open

- **No pre-flight fetch for researchers.** F117 listed "expose the verifier's own fetch as
  a pre-flight" as a candidate fix. Research agents are dispatched WebFetch-only with no
  shell, so they cannot call the verifier's reader at all — closing this would need a new
  tool seam, not a flag. Telling them their own fetch proves nothing is the honest fix
  available today, and it is what rule 8 now does.
- **Nothing ever un-blocks a domain.** A site that starts answering again still verifies
  normally, because the verifier keeps fetching `blocks-plain-readers` domains. A stale
  entry costs a warning line in a brief, not a lost series. Removing one is a human edit.
- **F125** (honest removal of already-published excerpts) is untouched — separate item,
  needs its own design.
- Two other host helpers exist elsewhere in the repo (`gathering/ingest.py`,
  `manifest.py`). They answer different questions and were deliberately left alone; the
  reviewer flagged the docstring that overclaimed, and the docstring was corrected rather
  than the modules folded together.
