# F110 dashboard revamp — DONE (branch `f110-dashboard`, NOT merged)

**State:** built, committed, green, and waiting. Only the user merges this branch.
The last commit is whichever commit added this file — check `git log --oneline -1`
rather than trusting a hash written inside the record it describes.

**Before merging:** `main` has moved on since this branch was cut. It carries two
unrelated commits from the 2026-08-06 daily cycle, `0d6036c` and `be543d8`, and
the merge base is `bc08b61`. This branch is behind main by those two commits.

### There will be one merge conflict, and it is the important one

`git merge-tree main HEAD` reports a content conflict in
**`site/chips.merchant-gpu/index.html`** — the single file this whole feature
lives in. Main's 2026-08-06 cycle regenerated it as the old story-style page;
this branch replaced it with the compiled dashboard.

**Resolve it by taking THIS BRANCH's version of that file.** Nothing will tell
you if you get it wrong: if the merge resolves toward main, the category page
quietly reverts to the old page, the compiled bundle sits in the folder with
nothing pointing at it, and no check fails — the link gate only asks whether the
file exists, not what is in it.

### Run one command straight after merging

```
.venv/Scripts/python -m gpu_agent.cli dashboard-json --category chips.merchant-gpu
```

Main's store now holds the 6 August reading while the data file committed on this
branch holds 5 August. Until the next scheduled cycle runs, the dashboard header
and the story archive it links to would disagree by a day. This one command lines
them back up.

## What shipped

The merchant-GPU category page is now a compiled single-page app instead of the
old story page. It answers one question at the top — *is supply catching up to
demand?* — and everything under it exists to back that answer up:

1. **The verdict.** The question, the answer, a direction badge, how sure we are,
   and a "so what" line. A small badge next to the answer opens the published
   sources it rests on.
2. **The gap.** One chart of demand against supply since 1 June, with the widest
   reading marked, a hover readout, and a "Show the numbers" table for anyone who
   would rather read figures than a picture.
3. **What changed.** Three dated bullets from the day's story, each with its
   sources and either a small chart or an honest panel saying why there isn't one.
4. **Six dimension rows.** Plain-English names, a rating, a direction, and an
   expandable panel giving the reasoning and the evidence behind it.
5. **A footer** linking to the deeper pages: evidence, the numbers we track, past
   readings, the story archive, and companies.

The daily Python run feeds it one file, `site/chips.merchant-gpu/data/dashboard.json`,
written by the `dashboard-json` step. No Node runs in the daily cycle: the compiled
page and its bundles are committed.

With scripting turned off, the page states no verdict at all. It gives the question
and points at the story archive for the current answer — because this file only
changes when someone rebuilds the app by hand, so any answer written into it would
go stale and end up contradicting the page's own data.

**The site builder** no longer writes the category page — that file is a committed
input now. It still emits every deep page exactly as before, it fails the build if
the committed page is missing (every deep page links back to it), and it makes sure
the data file is present (failing softly, so a bad export can never stop the cycle).
The compiled app and the deep pages share one folder, so the build is pinned to
`emptyOutDir: false` with a check that fails if anyone ever flips it; a narrow
plugin clears only the bundle folder so old bundles don't pile up.

## Gate results (all run in this session, in the foreground)

| Gate | Result |
| --- | --- |
| `../../.venv/Scripts/python -m pytest -q` | 2316 passed, 6 skipped |
| Four pinned baselines (eval baseline, narrator prompt, scoring-v1 replay, run-cycle conformance) | 56 passed |
| `npm test` (web) | 9 files, 116 tests passed |
| `npm run build` (web) | built in 696ms |
| Forbidden-diff check vs `main` | empty (no output) |
| Deletions under `site/chips.merchant-gpu/{findings,series,story,entities}` | none |

The forbidden-diff command run was the plan's Global Constraints list, not the
bare `fixtures/` path in the task brief — this lane legitimately added
`fixtures/chartdata/` and `fixtures/dashboard/`, which the bare path would have
flagged as its own violation. The user confirmed this reading.

Exactly one pin moved in this lane, in Task 7 (the run-cycle conformance
re-record, planned). Nothing moved in this task.

## What was actually checked on the built page

Served the built `site/` locally and clicked through: the verdict's source
badge opens three real sources with dates; the chart hover shows a date and the
demand / supply / gap figures for that reading; a bullet's source link opens the
live AMD investor-relations release it cites; a dimension row expands to its
reasoning and evidence; the footer's "Evidence" link lands on the findings page,
whose back-link returns to the dashboard. No errors in the browser console.

One real defect was found and fixed here: five readings landed in the same week,
and their date labels printed on top of each other. The axis now labels only
readings far enough apart, always keeping the first and last.

## The final fix wave (after the whole-branch review)

The branch was reviewed end to end and came back "ready, with fixes". They were
all made in one pass before this record was finalised. The five that changed what
a reader sees:

1. **The "how sure we are" line on the six dimension rows was printing our
   internal scoring notes.** Under that heading an executive was reading
   *"Medium — majority of 3/3 samples; capped by finding confidence (medium)."*
   The verdict at the top of the page had always translated the same field into
   plain words; the rows never did. They now say what the mock says, for example
   *"Medium — the underlying reports are single-source in places."* An earlier
   claim in this record that the reader-facing copy was clean was sincere but
   wrong until this was fixed. It is true of what ships.
2. **The "this reading may be old" warning was watching the wrong file.** It
   compared against the page's own timestamp — a file that only changes when
   someone rebuilds by hand — instead of the data file the daily run rewrites.
   A failed export would have left yesterday's verdict on the page with no
   warning at all. It now uses the timestamp the server sends with the data.
3. **The chart's spoken description could contradict the caption printed under
   it.** Two different calculations of "is the gap widening or narrowing" — one
   in Python, one in the page — could disagree on the same data. There is now
   one answer, and the page reads it from the data rather than working out its
   own.
4. **A "no chart" panel said something untrue about the bullet beside it.** It
   read *"The only numbers here are our own estimates, not published facts"*
   next to a bullet citing a company's own published results. It now says
   *"No chart. The number we track for this is our own estimate, not a published
   figure, so we don't draw it."*
5. **"Why we say that" could show a heading with nothing under it.** The panel
   now leaves out any block — reasoning, how sure we are, evidence — that has
   nothing in it.

Smaller reader-facing tidies in the same pass: two readings that fall on the same
calendar date are now ordered the same way every time (a whole-month reading is
dated the 1st, so a reading taken on the 1st used to collide with it and the file
order decided which counted as "last" — which decides the direction word); three
panels printed a literal double hyphen where the design uses a dash; a failure
message that showed the reader a file path and a status code now reads as plain
English; the two spellings of one unit ("USD bn" and "US$ billions") are now one;
and the colour key under the six rows names the colours by the words the rows
actually use (green strong, amber mixed, red weak) rather than words that appear
nowhere else on the page. That last one is a deliberate, recorded departure from
the mock, which says "green healthy · amber mixed · red strained".

The review also found that no committed test ever walked a bullet's chart, so a
second payload fixture that carries a real chart now runs through the same
contract check.

## Known limitations — recorded deliberately, not bugs to fix

- **The gap chart mixes single-day and whole-month readings**, which sit on
  different scales. The direction badge can therefore flip depending on which
  kind of reading came last. The user was shown this consequence and chose to
  keep it. The chart's own caption says so in plain words.
- **Two details from the mock cannot render**: the numeric context note beside
  the confidence line, and the bolded clause in the "so what" line. The data
  contract carries plain strings only, with no place to mark them up.
- **The dimension summaries run long** — 26 to 39 words against the mock's 12 to
  19 — because complete honest sentences were chosen over truncated fragments.
- **Charts under the bullets will stay absent** until a curated series has enough
  history. On today's data all three bullets correctly show the dashed "no chart"
  panel. The AMD series needs one more quarterly release before it can be drawn.
- Minor, cosmetic: a source whose title is missing shows only its outlet name
  ("Yahoo Finance"); a bullet's source panel can overlap the chart above it when
  opened near the top of the section.

## Post-merge criteria (design spec section 11) — to confirm on the live site

1. The next scheduled cycle writes `dashboard.json` with no manual steps, and the
   live page renders it.
2. At least one daily bullet renders a curated-series chart with a working source
   link; a bullet with no defensible series renders the honest no-chart panel.
3. Every visible statement on the live page resolves to a working source.

Note for the merge: `main` has run a daily cycle (2026-08-06) since this branch
was cut, so `main` is ahead. The committed `dashboard.json` here holds the
2026-08-05 reading; the first cycle after merge overwrites it. The deep pages in
this branch were deliberately left at their committed state rather than
regenerated, so the merge carries no unrelated site churn.
