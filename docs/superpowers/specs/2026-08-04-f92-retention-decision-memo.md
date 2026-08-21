# F92 — Store retention & archival: decision memo

**Written:** 2026-08-04 · **Lane:** `f92-retention-memo` · **Status:** DECISION MEMO — awaiting the
user. Nothing implemented, nothing changed outside this file. Supersedes the numbers in Section 2 of
`.superpowers/handoffs/f91-f92-decision-MEMO.md` (2026-07-29), which measured the right things but
projected them forward using the wrong shape of growth.

---

## The bottom line

The saved market work is **8.5 MB today** — small, harmless, nothing is close to breaking. But it is
not growing the way the last memo assumed, and the difference matters:

- The last memo projected **~145 MB after a year at one desk**. The real figure is **~2.6 GB** —
  about eighteen times bigger. Its alarm ("act at 250 MB, or when 3 desks go live") would fire in
  about **ten weeks at one desk**, not "someday when the fleet arrives."
- The reason is a piece of duplication nobody had looked at: **every daily scorecard carries a
  complete copy of every fact it scored, and those same facts are already saved once each as their
  own files.** Today that is 238 facts copied into a 500 KB file. In a year it is roughly 5,000
  facts copied into a 10 MB file, written fresh every single day.
- Good news that changes the answer: **the project's saved history is not the problem.** All the
  scorecard history there has ever been compresses to **353 KB**. Version control already notices
  that today's scorecard is yesterday's plus a bit, and stores only the difference. What costs money
  is the working copy on disk — the one folder full of near-identical multi-megabyte files.
- That kills two of the three escape hatches the backlog pre-listed. A cold-archive branch and
  large-file storage both attack the *history*, which is already almost free. They would buy
  0.35 MB and cost real complexity.

**My recommendation: stop the duplication at the source — new scorecards point at the facts instead
of copying them — and keep the year-partition idea in reserve behind a written trip point.** That is
a ~23x reduction, it is forward-only so nothing already saved is touched, and it leaves the
replay-fidelity guarantee intact by construction.

Nothing here needs doing this week. It needs deciding this month.

---

## 1. What I measured today

All measurements taken 2026-08-04 on this machine, working tree at `e588591`. Read-only.

### 1a. Size of the saved work (`store/`)

| Folder | On disk | Files | What it is |
|---|---|---|---|
| `store/chips.merchant-gpu/` | **5.9 MB** | 51 | the daily scorecards — **69% of everything** |
| `store/findings/` | 1.2 MB | 271 | one file per fact, immutable |
| `store/theses/` | 796 KB | 2 | the running thesis history file |
| `store/live_run/` | 265 KB | 27 | run bookkeeping |
| `store/series/` | 124 KB | 9 | the scoring-v2 time series |
| `store/wiki/` | 87 KB | 24 | the wiki pages and their event log |
| everything else | ~140 KB | 34 | docs, brain snapshots, demo/dry-run leftovers |
| **total** | **8.5 MB** | **418** | |

Tracked in version control: 7.3 MB / 360 files (the difference is untracked scratch).

### 1b. Size of the version history

| Measure | Today |
|---|---|
| Packed history | 3.96 MB (+ 9.7 MB of loose objects a routine cleanup would fold in) |
| `.git` folder on disk | 20 MB |
| Commits | 1,035 |
| **Every scorecard version ever, packed together** | **353 KB** (176 objects) |

That last line is the one that decides this memo. The scorecard folder is 5.9 MB in the working
copy; its entire history — every version of every file — packs into 353 KB. Version control's
difference-storage is extremely good at this data, because consecutive scorecards are 98% identical.
Plain zip compression alone gets 6x; difference-storage gets about 17x on top of a *single* copy.

### 1c. Growth per daily cycle

Measured from the last five daily cycle commits:

| Date | Files touched | Lines added | Saved-work size after | Added that day |
|---|---|---|---|---|
| 2026-07-25 | 20 | 9,635 | 5.09 MB | — |
| 2026-07-26 | 27 | 11,032 | 5.61 MB | 514 KB |
| 2026-07-27 | 18 | 11,112 | 6.14 MB | 529 KB |
| 2026-07-28 | 21 | 11,729 | 6.70 MB | 562 KB |
| 2026-07-29 | 31 | 13,214 | 7.32 MB | 619 KB |

Note the last column: 514, 529, 562, 619. **The daily cost is itself rising.** That is the signature
of the duplication, and it is why a straight-line projection understates the future.

### 1d. Why it rises — the actual mechanism

Each scorecard embeds the full text of every fact it scored. The relationship is exact and boring:

| Scorecard | Facts inside | File size |
|---|---|---|
| 2026-07-v1 | 72 | 124 KB |
| 2026-07-v10 | 97 | 206 KB |
| 2026-07-v15 | 150 | 315 KB |
| 2026-07-v21 | 238 | 501 KB |

**2,100 bytes per fact, every time.** The fact count climbs by about 11 per cycle net (22 new facts
arrive; older ones fade out). So each day writes a *complete, slightly longer* copy of the same
document — 500 KB today, more tomorrow, forever.

And it is pure duplication. I checked 50 of the 238 facts in the newest scorecard: **all 50 already
exist as their own files in `store/findings/`.** The scorecard is carrying a second copy of data the
project already stores once, canonically, immutably.

### 1e. Does it grow forever? No — it plateaus, but high

There is already a fading rule: a fact decays on a half-life set by how often its indicator updates,
and drops out once its weight falls below a floor (`gpu_agent/corpus.py:50-61`,
`gpu_agent/wiki/lint.py:83-94`). Half-lives are 7 days for daily-cadence facts, 21 for weekly, 120
for quarterly; the drop-out floor is 0.1 against a starting weight of 0.5–1.0.

Of the 238 facts in the newest scorecard, **184 are quarterly-cadence** (120-day half-life), 37
weekly, 17 daily. That mix survives an average of **224 to 321 days** before fading. At 22 arrivals
per cycle, the window settles at roughly **4,900–7,100 facts**, reached about **7 to 10 months from
now** — a scorecard of **10 to 14 MB**, written fresh every day, forever after.

So the growth is not unbounded-quadratic. It is quadratic for about a year, then linear at a very
high rate.

### 1f. Projection

Working-copy size of `store/`, daily cycles, starting from today's 8.5 MB. Range reflects the
survival-window uncertainty in 1e.

| | 1 year | 3 years | 5 years |
|---|---|---|---|
| **1 desk** | 2.6 – 3.0 GB | 9.7 – 13.2 GB | 16.8 – 23.4 GB |
| **34 desks** | 88 – 103 GB | 330 – 448 GB | 572 – 794 GB |

Version *history* on top of that stays modest — probably low hundreds of MB even at the five-year
mark, given the 17x difference-storage already observed. **The pain is the checkout on disk and
every tool that has to read it, not the download.**

Milestones at **one desk alone**, no fleet required:

- crosses **100 MB** at about **cycle 68** — roughly **mid-October 2026**
- crosses **1 GB** at about **cycle 278** — roughly **May 2027**
- crosses **5 GB** at about **cycle 655** — roughly **May 2028**

A single scorecard file hits the hosting service's 50 MB warning around **year 6** and its 100 MB
hard block around **year 12**. Those are not the binding constraints. Repository size is.

### 1g. Is anything urgent right now?

**No.** 8.5 MB of saved work, a 20 MB history folder, a clone measured in seconds. No hosting limit
is near — the nearest (a 1 GB repository advisory) is about nine months away at the current single
desk. This memo is a decision, not an incident. I did not stop for questions under the question-stop
rule because nothing demands action before the user reads this.

---

## 2. The constraint every option must respect: replay fidelity

`tests/test_scoring_v1_replay_pin.py` is the promise that a scorecard saved months ago still
reproduces its own published numbers. It does three things, and each one constrains retention:

1. **It reads the files directly off disk** at the fixed path `store/chips.merchant-gpu/*.json`
   (line 30) and re-computes each scorecard's demand/supply numbers from the fact bodies embedded
   inside it. Move the file, and the pin cannot find it.
2. **It requires the fact bodies to be there.** The re-computation is
   `dmi_smi_contribution(sc.findings, ...)` — it scores the facts *inside* the scorecard. If those
   bodies are gone, the pin needs somewhere else to read them from.
3. **`test_all_pinned_files_known` asserts the folder's contents exactly** (lines 118-127): the set
   of scorecard files on disk must equal the pinned set plus the superseded set. **Removing,
   moving, or renaming any scorecard turns the test suite red immediately.** This is deliberate —
   it is the trip-wire that stops replay fidelity from silently lapsing.

Point 3 is the sharp edge. Any archival scheme that moves files out of that folder is a
test-suite-breaking change on the day it runs. That is not a reason to reject such a scheme — it is
a cost that must be paid deliberately, in the same change, by teaching the pin where the archive
lives. It is a reason to prefer a scheme that never moves a file.

Two other promises in the same category: findings are write-once and refuse to be overwritten with
different content (`gpu_agent/store.py:41,57-58`), and the series store appends revisions and never
rewrites (`gpu_agent/series_store.py:1-6`). Nothing below touches either.

---

## 3. The options

### Option A — Scorecards reference their facts instead of copying them (forward-only)

**What it is.** From a chosen date, a new scorecard stores the *identifiers* of the facts it scored,
not their full text. The bodies stay exactly where they already are — one file each in
`store/findings/`, immutable, unchanged. Every scorecard written before that date is left byte-for-byte
alone, forever.

**What it protects.** The whole problem, at the source. Measured on the real file: today's 501 KB
scorecard becomes **21.9 KB** — **23x smaller**. At the projected plateau it is ~170–230 KB instead
of 10–14 MB. Revised projection:

| | 1 year | 3 years | 5 years |
|---|---|---|---|
| **1 desk** | ~0.1 GB | ~0.3 GB | ~0.5 GB |
| **34 desks** | ~3 GB | ~10 GB | ~17 GB |

The five-year, full-fleet number drops from ~700 GB to ~17 GB. That is the difference between "this
ends the project" and "this is a large but ordinary repository."

**What it costs.** A real code change, not a policy: a save path that writes identifiers, a load path
that fetches the bodies back, and every reader of a scorecard updated to go through it. Roughly a
day of careful work plus tests. It also means a scorecard is no longer readable on its own — you need
the findings folder beside it. That is a genuine loss of self-containedness and should be named as
such.

**What breaks — and the replay answer.** Nothing already on disk. Because it is forward-only, all 37
currently-pinned scorecards keep their embedded facts and the pin keeps passing untouched. New
scorecards need the pin's loader to fetch bodies before scoring — one helper function, and the
`test_all_pinned_files_known` trip-wire keeps working unchanged because no file ever moves or
disappears. Replay fidelity is preserved *by construction* rather than by remembering to preserve it.

The one honest risk: a referenced fact must never vanish. That is already guaranteed — the findings
store is append-only and refuses destructive writes — but it becomes load-bearing in a way it was
not before, and any future pruning of `store/findings/` would become a replay-breaking act. Worth
writing down as a standing rule alongside the change.

### Option B — Per-year store partitions

**What it is.** Saved work moves into year folders (`store/2026/…`, `store/2027/…`); only the current
and previous year stay in the live checkout, older years move to an archive location or a separate
branch.

**What it protects.** Caps the *live* checkout at roughly two years of data. Under today's format
that is still 5–8 GB at one desk and hundreds of GB at 34 — it slows the bleeding without stopping
it. Under Option A's format it caps an already-small thing. It is a good second layer, a poor first
one.

**What it costs.** A migration that moves hundreds of files, path changes across every reader, and
new failure modes sitting next to the append-only guarantees — the one part of this system whose
entire value is that it never changes underneath you.

**What breaks — and the replay answer.** Directly hits the trip-wire. `STORE = "store/chips.merchant-gpu"`
and the exact-set assertion both break the moment a file moves. Preserving replay means teaching the
pin to glob across year folders *and* the archive, and keeping the archive mounted wherever tests
run. Doable, but replayability now depends on a second location staying attached — the guarantee
gets weaker, not just more complicated.

### Option C — Large-file storage (git-lfs) for the bulky scorecards

**What it is.** Scorecard files are held outside normal version control; the repository keeps small
pointers.

**What it protects.** Almost nothing here. The entire scorecard history already packs to **353 KB**.
Large-file storage exists to rescue repositories from big *binary* blobs that do not compress and do
not diff. This is repetitive text that does both superbly. It would replace 353 KB of extremely
efficient storage with a per-clone dependency, a quota, and a bandwidth bill — while leaving the
working copy exactly as large as it is now, because a checked-out large file is still a full file on
disk. **It solves neither of the two problems and adds a third.**

**What breaks — and the replay answer.** The worst of the four. Any environment that clones without
fetching the large files gets a ~130-byte pointer where a scorecard should be; the pin then tries to
parse a pointer as a scorecard and fails with a confusing error. Replay fidelity would silently
depend on an external service being reachable. Not acceptable for a guarantee whose whole purpose is
to be unconditional.

### Option D — Do nothing; add a size line to the cycle log and a written trip point

**What it is.** The backlog's original lean, and the July 29 memo's recommendation. Record the size
each cycle, write down a threshold, act when it trips.

**What it protects.** Only against being surprised. Cost is a few lines of code.

**What breaks.** Nothing — and that is the point, but also the problem. The new measurements change
this option's character: the threshold the last memo proposed (250 MB) now fires in about **ten
weeks**, and the "3 live desks" condition is no longer the thing that arrives first. Chosen alone,
this option schedules the same decision for October with a bigger folder to migrate.

**Worth keeping regardless.** Whatever else is decided, the size line belongs in the cycle log. It is
the only reason anyone caught this at 8.5 MB rather than at 8 GB.

---

## 4. Recommended trigger threshold

Under the recommendation below, the trip points should be:

| Trip point | Value | Why this number |
|---|---|---|
| **Saved work exceeds** | **500 MB** | Roughly six months of headroom under Option A even at several desks; well clear of any hosting advisory. |
| **A single scorecard exceeds** | **5 MB** | Early warning that the fading rule stopped bounding the window — the assumption this whole projection rests on. |
| **Fresh clone exceeds** | **2 minutes** | The user-visible symptom, regardless of what the numbers say. |
| **Live desks reaches** | **5** | Multiplies everything by 5 in one step; belongs on the fleet-rollout checklist, not in a file nobody reads. |

**When any trips:** implement Option B (year partitions), which by then is a small change to an
already-small store — and budget the replay-pin work described in §3B as part of it, not after it.

Recorded now so that whoever hits the wall — plausibly an unattended run at 3 a.m. — is executing a
decision rather than making one.

---

## 5. Recommendation

**Do Option A now (forward-only reference scorecards), plus the size line from Option D. Pre-pick
Option B as the escape hatch behind the thresholds above. Rule out Option C explicitly so nobody
re-proposes it.**

The reasoning, shortest form:

1. **The duplication is the whole problem.** 69% of the saved work is scorecards, and essentially all
   of that is second copies of facts already stored once. Fix the cause and the symptom stops.
2. **The two hatches the backlog pre-listed aim at history, and history is already solved.** 353 KB
   for every scorecard version ever written. A cold-archive branch and large-file storage would both
   be spending real complexity to reclaim a third of a megabyte.
3. **Forward-only is what makes this safe.** Not one existing file is touched, so all 37 pinned
   scorecards keep replaying byte-for-byte, and the trip-wire test that guards the folder's contents
   keeps passing without modification. Every other option starts by moving files the pin is watching.
4. **It buys about forty times more runway than partitions do**, and it makes partitions cheap if
   they are ever needed — a small store is a small migration.
5. **Timing.** This is not urgent, but it is cheapest today and gets steadily more expensive: every
   week of delay adds another 10 MB of duplicated text that the forward-only cut will simply leave
   behind. Waiting does not make it wrong, it makes it larger.

**Two things I would explicitly not do.** Do not rewrite existing scorecards into the new form — the
saving is 5.9 MB and the price is disturbing immutable, replay-pinned records. Do not adopt
large-file storage on any timeline; the measurement says it is the wrong tool for thousands of small
repetitive text files.

**One caveat I want on the record.** The plateau in §1e (4,900–7,100 facts) is a projection from a
decay rule, not an observation — the store is only two months old and almost nothing has aged out
yet. If the fading rule turns out to be looser in practice, the numbers get worse, not better. The
5 MB single-scorecard trip point in §4 exists specifically to catch that.

---

## 6. Decision box

Please answer these four:

1. **Option A — forward-only reference scorecards: yes or no?**
   (My recommendation: yes. ~23x smaller, nothing existing is touched, replay pin unaffected.)

2. **If yes, from what date do new scorecards switch to reference form?**
   (My recommendation: the first cycle after the change merges — no back-dating, no migration.)

3. **Are the trip points in §4 right — 500 MB saved work / 5 MB single scorecard / 2-minute clone /
   5 live desks — and is year-partitioning (Option B) the pre-chosen hatch?**
   (My recommendation: yes to both.)

4. **Rule out large-file storage permanently, on the measured grounds in §3C?**
   (My recommendation: yes — record it so it is not re-litigated.)

If the answer to (1) is no, the fallback is Option D alone with a 250 MB trip point, and this becomes
an October decision instead of an August one.

**ANSWERED 2026-08-22 (user, interactive, relayed decision session — recorded in
docs/fix-backlog.md F92 and docs/superpowers/HANDOFF.md):**

1. **YES** — forward-only reference scorecards approved. Design-weight: the interactive brainstorm
   with the user must run before any build lane is dispatched.
2. **First cycle after the change merges** — no back-dating, no migration of existing files.
3. **YES to both** — trip points accepted as written; year-partitioning (Option B) is the
   pre-chosen hatch if one trips.
4. **YES** — large-file storage (git-lfs) permanently ruled out on §3C's measurements; not to be
   re-litigated.

---

## Decision provenance

No design forks were resolved by this lane. Every choice below is either a measurement or a
recommendation awaiting the user; none is an AFK-default.

- **Mechanical choices made without stopping** (per the question-stop rule's trivial-choices clause):
  the memo's file name and location; sampling the last five cycle commits rather than all 1,035;
  modelling the fade plateau with two survival bounds rather than one point estimate.
- **Not decided here:** every question in §6.
- **Supersedes:** Section 2 of `.superpowers/handoffs/f91-f92-decision-MEMO.md` (2026-07-29). That
  memo's measurements were correct for its date; its projection assumed straight-line growth at
  ~400 KB/day and therefore understated the one-year, one-desk figure by roughly eighteen times. Its
  recommended alarm values are superseded by §4. Its conclusion — decide now, build later — survives;
  its conclusion that *nothing* should be built now does not.

## How to re-check these numbers

- Saved-work sizes: `du -sh store/*/`
- History size: `git count-objects -vH`
- Scorecard history packed: `git rev-list --objects HEAD -- store/chips.merchant-gpu | awk '{print $1}' | git pack-objects --stdout | wc -c`
- Size at a past commit: `git ls-tree -r -l <commit> store/ | awk '{s+=$4} END {print s}'`
- Facts per scorecard: read `findings` array length from `store/chips.merchant-gpu/2026-07-v21.json`
- Fading rule: `gpu_agent/corpus.py:50-61` and `gpu_agent/wiki/lint.py:83-94`
- Replay pin: `tests/test_scoring_v1_replay_pin.py`, especially lines 30 and 118-127
