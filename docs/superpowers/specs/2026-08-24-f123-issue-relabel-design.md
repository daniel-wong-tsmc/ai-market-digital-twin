# F123 — Issue identity survives a constraint relabel (design)

**Date:** 2026-08-24
**Backlog item:** F123, `docs/fix-backlog.md`
**Decisions record:** `.superpowers/sdd/2026-08-24-f123-issue-relabel/QUESTIONS.md`
(every design choice below is agent-decided, AFK-default — no human approved them)

## The problem

An issue's id is derived from the exact binding-constraint label:
`issue_id()` slugs `categoryStatus.constraintLabel` into
`constraint-<slug>`. When the brain re-words the same real constraint, the slug
changes, `open_issues()` finds no matching id, and it mints a twin.

It happened three times over three cycles for one physical problem:

| cycle | `constraintLabel` | minted id |
|---|---|---|
| 2026-08-v8 | `HBM stacked memory supply` | `constraint-hbm-stacked-memory-supply` |
| 2026-08-v9 | `stacked memory and server DRAM` | `constraint-stacked-memory-and-server-dram` |
| 2026-08-v10 | `Stacked high-bandwidth memory supply` | `constraint-stacked-high-bandwidth-memory-supply` |

Each stranded id keeps its own streak counters. Because a stranded issue's
`trigger.label` no longer equals the current `constraintLabel`,
`trigger_still_firing()` reads False, so every "unchanged" assessment counts as
improvement; after `RESOLVE_STREAK` (5) quiet cycles the register reports it
**Resolved** to the reader while the real constraint is still biting. The
2026-08-22 hand-consolidation fixed that instance, not the class.

## The fix, in one line

Before minting a new `binding-constraint` id, try to match the new label against
the **open** constraint-kind issues by token overlap. A hit **renames** the
standing issue — title and trigger label update, id and history persist —
instead of opening a twin.

## Scope

- **In:** `gpu_agent/issues.py`, open-trigger logic (`open_issues` and new
  helpers), plus its tests.
- **Out:** narrator prompt (byte-frozen), pins, `register.json` schema,
  `history.jsonl` record shape, the `issues update` CLI path, dimension issues.

## Why token overlap and not a stable indicator anchor

The backlog names both as a fork. The anchor option is unreachable in scope:
`categoryStatus` carries only `rating`, `direction`, `bottleneck`, `reason`,
`constraintLabel`, and `bottleneck` is the literal string `"bottleneck"` in v8,
v9 and v10 — the dimension key, not an indicator of the constraint. There is no
per-constraint indicator id in any existing payload, so an anchor would need a
new brain-emitted field, i.e. a judgment-prompt edit, i.e. a moved pin. Token
overlap needs nothing that is not already there.

## The matching rule

`_label_tokens(label)` → `_slug(label)` split on `-`, dropping stop words
`{and, or, the, a, an, of, for, in, on, to, with, at, by, is, its}`.

`_labels_match(a, b)` is True when all three hold:

1. `len(shared) >= 2`
2. `len(shared - GENERIC_TOKENS) >= 1`
3. `len(shared) / min(len(A), len(B)) >= 0.5`

`GENERIC_TOKENS = {supply, capacity, shortage, availability, constraint,
constraints, limits, limited}` — they count toward the ratio but cannot by
themselves justify a match (rule 2). Empty token sets never match.

Against the real data: v8↔v9 share `{stacked, memory}` (ratio 0.5) → match;
v9↔v10 share `{stacked, memory}` (0.5) → match; v8↔v10 share
`{stacked, memory, supply}` (0.75) → match. `CoWoS advanced packaging capacity`
vs `HBM stacked memory supply` share nothing specific → no match.

When more than one open constraint issue matches, the winner is deterministic:
highest ratio, then most shared tokens, then earliest position in
`register.issues`. The committed register holds two open constraint issues
today, so ties are real, not theoretical.

## Behaviour of `open_issues` after the change

For each current trigger:

1. **Exact id hit** (unchanged priority).
   - resolved → reopen in place, as today (`reopenedAsOf` grows, counters reset).
   - open → no-op, **except** that a stale `trigger.label`/`title` is refreshed
     to the incoming label. Needed for the revert case: the id is derived from
     the *first* label, so a label that swings back finds the standing issue by
     id while its stored label still names the newer wording — leaving that
     stale would break `trigger_still_firing` in exactly the way F123 is about.
2. **No exact id, kind is `binding-constraint`** → look for a rename target
   among open constraint issues using the rule above. On a hit: keep `id`,
   `openedAsOf`, `reopenedAsOf`, `latest`, `improvedStreak`, `worsenedCount`,
   `checkCount`; set `title` and `trigger.label` to the new label; report the
   id in the returned `touched` list.
3. **Otherwise** → mint a new issue, exactly as today.

A rename is not a reopen: counters are evidence about a problem that never went
away, so they persist. `history.jsonl` is not read, rewritten or truncated by
this path — the append-only guarantee is untouched by construction.

Dimension issues keep exact-id matching only; their labels come from a closed
list of dimension keys and cannot be re-worded.

## Idempotence

`issues open` is naturally idempotent: after a rename the stored label equals the
scorecard's, so a rerun takes the exact-id branch and changes nothing. `issues
update`'s per-story-date idempotence lives in the CLI (`history_has_as_of`) and
is not touched.

## Pin safety

No register field is added or removed; no history line shape changes; the
narrator prompt file is not opened. `gpu_agent/narrator/inputs.py` reads
`id`, `title`, `trigger`, and a history tail — all still present, and for a
renamed issue the title is now the *correct* current one. The F6 baseline,
narrator prompt pin, F83 run-cycle fingerprint and scoring replay pin must be
verified byte-unmoved before the lane is claimed done.

## Testing

- Reproduce the real bug: v8 label opens an issue, v9 label must NOT mint a
  second — one issue, same id, title updated.
- Full three-cycle walk v8 → v9 → v10 ends with exactly one constraint issue.
- History + counters persist through a rename; existing history lines byte-identical.
- A genuinely different constraint still mints a new id.
- Ties resolve deterministically.
- Revert-to-old-label refreshes the stale stored label.
- Resolved issues are not fuzzy-matched.
- Dimension issues unaffected; rerun of `issues open` is a no-op.
