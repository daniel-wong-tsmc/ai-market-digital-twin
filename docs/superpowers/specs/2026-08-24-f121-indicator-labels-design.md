# F121 — registry indicator labels shed their old-scheme id tails (design)

**Date:** 2026-08-24 · **Lane:** `f121-indicator-labels` (off main `f53d2df`)
**Backlog item:** docs/fix-backlog.md F121
**Decisions log:** `.superpowers/sdd/2026-08-24-f121-indicator-labels/QUESTIONS.md`
(no human on this lane — every design call there is recorded **agent-decided (AFK-default)**)

## Problem

Seven labels in `registry/indicators.json` still carry the retired indicator scheme's short id
in parentheses — `"Hyperscaler capex-revision direction (D1)"` and the same for S1, S2, S4, D4,
D9, X5. Any label row rendered above the fold (the DEMAND | SUPPLY board, quick glance, change
lines) would leak a raw id, and the F120 assembled-brief acronym gate blocks the whole brief on
them.

F120 round-3 shipped an interim cover: `reader.indicator_label` runs the label through
`reader.strip_stale_paren_ids`, so the display is already clean while the registry data is not.
The real fix — cleaning the data — was deferred to its own lane because those label strings are
baked verbatim into the emitted brain prompts (`gpu_agent/evals/emit.py` and `gpu_agent/cli.py`
read `spec.label` raw into the scoring/price indicator vocab), so it moves the F6 prompt-hash
baseline pin.

## Approach

Delete the parenthesised tail and the single space before it from the seven label strings. That
is the entire semantic change. Nothing is reworded.

| indicator id | after |
|---|---|
| `pkgCapacityOrderSpread` | `Advanced-packaging capacity-order spread` |
| `hbmSupplyCapex` | `HBM bit-supply growth + memory capex` |
| `upstreamLeadTimes` | `Upstream long-lead component lead times` |
| `hyperscalerCapexRevision` | `Hyperscaler capex-revision direction` |
| `odmMonthlyAiRevenue` | `Taiwan ODM monthly AI-server revenue` |
| `tokenEconomics` | `Inference token economics` |
| `marginalBuyerFinancing` | `Marginal-buyer financing conditions` |

The cleaned strings are byte-identical to what the display layer already prints today, so **no
rendered output changes** — not the brief, not the report, not the dashboard, not the web brief.
The only bytes that move are the emitted `extract` brain prompt.

### What stays

- `reader.strip_stale_paren_ids` **stays**, unchanged. Two of its three call sites
  (`brief.py:445`, `report.py:1183`) strip stale ids out of stored thesis-book
  `falsifiableTrigger` text, which F121 does not touch — the F54 GATE deliberately keeps
  observable indicator ids in the book. Its third call site (inside `indicator_label`) simply
  becomes a no-op: harmless belt-and-braces against a label re-acquiring a tail.
- `dashboard/brief_model._TILE_CODE_SUFFIX` **stays**, for the same reason. (Note for the
  backlog: contrary to F121's closing sentence, this strip already removed the tails on the
  dashboard path, so the web brief was never showing them.)
- `registry/acronyms.json` needs **no change**: its allowlist contains none of the seven codes.

### The pin consequence

Measured, not assumed: cleaning the seven labels moves exactly one seam.

```
extract  43afd610cda461bd3c7323c51c3efdc6ab3c6e39772fb494209527b1c53c6152
      -> 09a6a5e19227f6b1f21809618fb76a2fc2d248f08c8c8a781b7e4f3b484e2093
judge / thesis / implication — byte-unmoved
```

`tests/test_evals_baseline_pin.py` therefore goes red. That is the F6 gate doing its job. The
unlock is the recorded recipe only (`.claude/skills/run-eval/SKILL.md`: dispatch brains, gate,
dispatch graders, three replicates, then `eval rebaseline … --seams extract`). That recipe's own
invariant forbids an implementer subagent from running it ("Run-eval is SESSION-level work"), so
**this lane leaves the pin red** and hands the exact old→new fingerprints plus the `--seams
extract` instruction to the session-level operator. No pin hash is hand-edited.

The narrator prompt pin, the F83 run-cycle step fingerprint (`ce869181…`, a hash over the
run-cycle SKILL.md step list) and the scoring replay pin must stay byte-unmoved and green; the
plan verifies each explicitly.

## Testing

- A new registry-data test asserts every active indicator label is free of an old-scheme
  parenthesised id tail — the regression guard that stops a tail coming back.
- The existing F120 tests are the second half of the safety net and must pass **unchanged**:
  `test_f120_indicator_label_sheds_old_scheme_id_tail` (now trivially true at the data layer),
  the four book-text strip tests, and `test_f120_board_renders_clean_labels_above_fold`.
- Full suite from the worktree root; a worktree adds one expected skip (price scrape data).
- `npm --prefix web test` — the web brief consumes registry labels transitively through
  `brief_model`; output is unchanged but the run is cheap insurance.

## Out of scope

Generated cycle output under `site/chips.merchant-gpu/how/*.html` keeps the old strings: those
files are the record of what past runs actually printed and the next cycle regenerates them.
Historical docs and eval notes likewise stay as written.
