# Publishing posture — what this project puts in front of the world

**Status: IN FORCE — every clause below is DECIDED.** All eight approval points were approved by
the user, interactive, 2026-08-22 (relayed decision session; zero AFK-defaults). Clauses marked
`[DECIDED …]` cite their decision date. Follow-up build items minted at approval: F124 (footer
disclaimer), F125 (honest-removal mechanism), F126 (publisher do-not-fetch wiring), F127
(excerpt-length gate check).
Written for F91(b). Drafted 2026-08-04 against main @ `e588591`; approved 2026-08-22.

This is the missing half of F91. Part (a) — should the old public repo stay public — was answered.
Part (b) — the written rule for what may appear in public, and on what terms — is this document.

Two things are world-readable today and neither has a written rule attached:

1. **The old GitHub repository** `github.com/daniel-wong-tsmc/random_for_fun` — public, un-archived,
   frozen at the 2026-07-15 move. `[DECIDED 2026-07-29, user, interactive: it stays public.
   Recorded in docs/fix-backlog.md (F91(a)) at commit 8f260d3, after the memo
   .superpowers/handoffs/f91-f92-decision-MEMO.md recommended flipping it private and the user
   declined.]`
2. **The live website** `ai-market-digital-twin.pages.dev` — rebuilt on every push, carrying the
   desk's daily market read, its findings list, and links out to every source.

Nothing here changes what the software does today. Where a clause would need a code change to
enforce, it says so and the change is listed as a follow-up, not done here.

---

## 1. What we republish, and the honest framing

**What actually leaves this machine today** (checked in the code and in the committed output, not
assumed):

- **In the repository.** Each saved finding (`store/findings/*.json`) carries an `evidence` list, and
  each piece of evidence has four fields: the publisher's name, the exact web address of the page,
  the page's publication date, and an `excerpt` — a short passage copied word-for-word out of the
  page. Typically one sentence, occasionally two. The full fetched page is **not** saved and **not**
  committed; only the passage the finding leans on. Verified: no raw fetched documents are tracked
  in version control.
- **On the website.** Less than the repository holds. Source passages appear only as link labels,
  cut off at 60 characters, each next to the outlet's name, the date, and a live link to the
  original page. The findings pages carry the desk's own one-line summary of each finding plus the
  publisher name, tier, date and address. The daily story itself is written by the desk in its own
  words; the numbers in it are re-checked against the findings that cite them, and the writer is
  only allowed to quote figures it was actually shown
  `[DECIDED 2026-07-29 (F66 D5b, sourcing option (a)); implemented in gpu_agent/cli.py and
  gpu_agent/citation_audit.py]`.

**The framing we stand behind** `[DECIDED 2026-08-22, user, interactive]`:

> This project reads publicly available reporting and filings, forms its own view, and publishes
> that view. Where it leans on someone else's words, it quotes a short passage, names the outlet,
> gives the publication date, and links to the original. It does not reproduce whole articles, does
> not mirror or host source pages, does not paraphrase an article end-to-end as a substitute for
> reading it, and does not compete with the publisher for that article's readership. Every quoted
> passage exists to show a reader *why* a conclusion was drawn and to send them to the source.

That is the ordinary short-quotation-with-attribution position, and it is the position we intend to
keep. It is a statement of practice and etiquette, not a legal opinion; nobody here is a lawyer and
this document does not pretend otherwise `[DECIDED 2026-08-22, user, interactive]`.

**What we will not claim** `[DECIDED 2026-08-22, user, interactive]`: we will not describe the site as a news
service, a wire, or an aggregator, and we will not present a source's reporting as our own work.

---

## 2. Excerpt norms and attribution — what is already enforced, and what we are adding

### Already enforced by the software (stating existing behaviour as policy)

- **Every excerpt must be genuine.** The passage must appear word-for-word in the fetched page, or
  the finding is thrown away (`gpu_agent/extraction/extractor.py`, "excerpt not found in source
  document"). There is no path by which a made-up quote reaches the store.
- **Every excerpt must carry its source.** The web address on the evidence must match the address of
  the page it came from, or the finding is thrown away (same check). Publisher name and publication
  date are required fields — a finding without them fails its schema
  (`gpu_agent/schema/finding.py`).
- **The publication date is the real one.** Evidence dates are the page's publication date, never
  the day we fetched it.
- **Source text is data, never instruction.** Nothing inside a fetched page can redirect the work
  (charter Parts 8 / 26 / 37).

### Proposed additions

- **Length norm** `[DECIDED 2026-08-22, user, interactive]`: an excerpt should be **at most two sentences or about
  50 words**, and never more than is needed to support the one claim it backs. Today nothing in the
  code enforces a maximum length — the only limit is that the model is asked for a quote and the
  quote must be real. Measured on the committed store (2026-08-04, all 334 excerpts in
  `store/findings/`): **longest 40 words, median 14, none over 50.** So the norm costs nothing
  today; writing it down is what stops it drifting later.
  - **Follow-up if approved** (not built in this lane): add a length check to the extraction gate so
    an over-long excerpt is rejected the way an invented one already is. This is a small code
    change, and it should be a separate backlog item so the eval gate can be re-run against it.
- **No stacking** `[DECIDED 2026-08-22, user, interactive]`: several short excerpts from the same article, spread
  across several findings, must not add up to a reproduction of that article. If a single article is
  the source of more than **three** findings in one cycle, that is a signal to link to it rather
  than quote it again. Not enforced in code today; proposed as a review norm.
- **Attribution on every public surface** `[DECIDED 2026-08-22, user, interactive]`: any page that shows source
  wording shows, next to it, the outlet's name and a working link to the original. This is what the
  site does today; the rule makes it a requirement rather than a happy accident.
- **Never present a source's number as our own** `[DECIDED 2026-08-22, user, interactive]`: figures taken from
  reporting keep their attribution wherever they appear.

---

## 3. If a publisher objects

`[DECIDED 2026-08-22, user, interactive — no publisher has ever contacted this project; this is a
plan, not a history.]`

The stance is **cooperative, fast, and not argumentative**. Being right about fair quotation is not
worth a fight with someone who would rather not be quoted.

1. **Acknowledge within one working day**, in plain terms, and name a real person as the contact.
2. **Comply first, discuss after.** On any objection about specific quoted material — a complaint, a
   takedown notice, or an informal "please stop" — remove or shorten the material, rebuild the site,
   and confirm to the objector. Do not condition removal on agreeing with the objection.
3. **Removal is honest, not silent.** Because the saved work is append-only by design, we do not
   quietly edit history. The finding stays, its excerpt is replaced with a note saying the passage
   was removed at the publisher's request, and the link to the original stays. The cycle log records
   the request and what was done. `[DECIDED 2026-08-22, user, interactive. The mechanism does not
   exist in code today; filed as F125 because it touches the append-only guarantee and must be
   designed rather than improvised.]`
4. **A domain-level objection stops future fetching too.** If a publisher asks not to be used at
   all, its domain goes on a do-not-fetch list and the source inventory records why. `[DECIDED
   2026-08-22, user, interactive. BUILT 2026-08-25 (F126). The list lives in
   `registry/do-not-fetch.json`; an objection is one entry with `kind: publisher-objection`,
   and the fetch runner then refuses every request to that domain outright, while the chart
   verifier rejects any point citing it before fetching. The same file carries a second kind,
   `blocks-plain-readers`, for sites that merely turn our automated reader away — that kind is
   NOT a refusal. No publisher has ever objected, so the objection list is currently empty.]`
5. **Escalate anything legal to the user immediately** — no agent, session, or automation answers a
   legal letter. That is a human decision, always.
6. **Write it down.** Every objection and its resolution is recorded in the repository so the next
   person can see the pattern.

---

## 4. The daily market calls: what is exposed, and the disclaimer

**The exposure, stated plainly.** The site publishes a daily read on the AI-hardware market —
direction calls on demand, supply, and specific companies — and it is readable by anyone. It is
built and pushed from a GitHub account whose name contains the user's employer, `daniel-wong-tsmc`.
A stranger who finds the site can reasonably guess who is behind it and where they work. That is the
real risk here: not the quoting, but a market view that could be read as coming from an employer who
never approved it.

**The line that must not be crossed** `[DECIDED 2026-08-22, user, interactive; this is Option A
from the F91/F92 memo, now accepted]`:

> The public site may carry market analysis about publicly traded companies, drawn from public
> reporting, with short attributed quotes. It may **not** carry anything addressed to, prepared for,
> or framed as advice to the user's employer — no employer-directed implications, no capacity,
> capex, pricing, or account recommendations, and no material marked as prepared for an executive
> audience.

This is currently true of the live site by accident, not by rule: the layout that used to carry the
employer-directed implications text was replaced in a redesign. The rule is what keeps the next
redesign from putting it back.

**Disclaimer, to appear in the footer of every public page** `[DECIDED 2026-08-22, user,
interactive; wording and placement both approved — implementation filed as F124]`:

> Independent personal project. The analysis here is one individual's own work, produced from public
> sources. It is not affiliated with, endorsed by, or representative of any employer, and it is not
> investment advice.

**Honest status:** no disclaimer of any kind appears on the site today — checked across the built
pages. Adding one is a small template change in the site builder
(`gpu_agent/dashboard/`), and it is **not done in this lane** — this lane writes the policy, not the
code. If the user approves the wording, the change should be its own backlog item.

**Related standing rule, unchanged:** "Do not publish anything TSMC-branded from a repo still named
`random_for_fun`" (`.claude/skills/desk-external-positioning/SKILL.md`). Nothing in this document
relaxes it. Note the tension the user has accepted with eyes open: the old public repo does contain
TSMC-branded material and stays public by decision `[DECIDED 2026-07-29, above]`. This posture
governs what we publish **from now on**; it does not retroactively clean the frozen old repository.

---

## 5. What must never be committed or published

`[DECIDED 2026-08-22, user, interactive. Items marked "already true" describe protections that exist today.]`

1. **Credentials of any kind** — API keys, cookies, session tokens, passwords. Already true in
   practice: the automatic tool bootstrap never touches secrets, and per-machine secrets are set up
   outside the repository by design (`docs/web-reach.md`).
2. **Full text of paywalled or licensed articles.** Short attributed excerpts only, exactly as for
   any other source. Already partly enforced: sources declared paywalled are never fetched and are
   logged as a coverage gap; licensed and subscription domains are fetched openly but every such
   fetch is flagged `[DECIDED 2026-07-13, user, interactive — D6, docs/web-reach.md]`. The addition
   here is the **republishing** half: a licensed source's wording is quoted under the same two-
   sentence norm as anything else, and never stored or shown in bulk.
3. **Whole fetched pages.** Raw fetched documents stay out of version control. Already true —
   verified: no raw document bodies are tracked; the committed record of what was read
   (`store/seen_docs.jsonl`) holds only the address, a fingerprint, and the month.
4. **Personal data.** No names, contact details, addresses, or other identifying information about
   private individuals. Public statements by named executives acting in their public role are
   ordinary reporting and are fine; anything about a private person is not.
5. **Anything internal to the user's employer** — internal documents, unpublished figures,
   colleagues' names, or anything learned at work rather than from public sources. This is the
   clause that matters most and the one no gate can check.
6. **Machine-local paths, hostnames, and account identifiers** beyond what is already unavoidable in
   the repository's own history.

**How this is meant to be checked** `[DECIDED 2026-08-22, user, interactive]`: item 3 is covered by the ignore
rules and by the shape of what the software writes. Item 1 rests on the fact that secrets live
outside the repository by design — there is **no automatic secret scan** on commits today, and if
the user wants one that is a separate decision. Items 2, 4, 5 and 6 are human judgement at review
time. This
document does not propose an automated scanner for them, because a scanner that half-works on this
kind of content would give false comfort. If the user wants one, that is a separate decision.

---

## Decision provenance

| Clause | Status | Source |
|---|---|---|
| Old repo stays public | DECIDED 2026-07-29 (user, interactive) | `docs/fix-backlog.md` F91(a); commit `8f260d3`; memo `.superpowers/handoffs/f91-f92-decision-MEMO.md` |
| Licensed/subscription sources fetched openly, flagged loudly | DECIDED 2026-07-13 (user, interactive) | `docs/web-reach.md` §D6 |
| Story quotes only figures the writer was shown | DECIDED 2026-07-29 | F66 D5b option (a); `gpu_agent/cli.py:767` |
| No TSMC-branded publishing from a repo named `random_for_fun` | Standing rule | `.claude/skills/desk-external-positioning/SKILL.md` §5 |
| Excerpts must be verbatim and carry the source address | Already enforced in code | `gpu_agent/extraction/extractor.py:138-140` |
| Everything else in this document | **DECIDED 2026-08-22 (user, interactive)** | this file; relayed decision session, all 8 approval points |

Every decision in this document was taken by the user, interactively. No clause is an AFK-default.
The approval session changed no code, gates, or site output; the four build items it minted
(F124–F127) are in `docs/fix-backlog.md`.
