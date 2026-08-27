# F127 — enforce the excerpt length cap in the extraction gate — design

**Date:** 2026-08-25
**Branch:** `f127-excerpt-length`, off main `e6b9de3`
**Backlog item:** F127. Source norm: `docs/publishing-posture.md` §2, `[DECIDED 2026-08-22]`.
**Classification:** bounded. The flow being changed already exists and is one function.

---

## What the decided norm actually says

> an excerpt should be **at most two sentences or about 50 words**, and never more than is
> needed to support the one claim it backs.

Two limits joined by "or", not "and". That word does real work, and the measurement below
shows why.

## What is in the store today

Re-measured on this branch across every `store/**/*.json` (the posture doc's figure of
334 excerpts is a year old; the store has since grown to **644**):

| Excerpts | Over 50 words | Over 2 sentences | Over **both** |
| --- | --- | --- | --- |
| 644 | 1 | 2 | **0** |

- The one over-long excerpt is **70 words in a single sentence** — a verbatim AMD 10-Q
  gross-margin sentence in `store/findings/ir-amd-com-cfa508a5-2026-08-3.json`.
- The two multi-sentence excerpts are **29 words / 4 sentences** and **36 words / 3
  sentences** — both short.

So a hard 50-word cap would have thrown away a real, well-sourced finding, and a hard
two-sentence cap would have thrown away two more. Reading the norm as written — reject only
what breaks *both* limits — rejects nothing that is in the store. That matches the posture
doc's own claim that "the norm costs nothing today".

## The rule being implemented

An excerpt is rejected when it is **longer than 50 words AND made of more than 2
sentences**. Either limit alone is satisfiable, exactly as the DECIDED text says.

Plus one backstop the doc implies but does not number: an excerpt over **100 words** is
rejected regardless of sentence count. Without it, a single run-on sentence — or any text
the sentence counter mis-reads as one sentence — bypasses the gate entirely, which is not a
gate. 100 is twice the norm and comfortably above the largest real excerpt ever stored (70).

Violation messages follow the existing house style:

```
{fid}: excerpt too long (63 words > 50 and 4 sentences > 2)
{fid}: excerpt too long (118 words > 100 absolute cap)
```

## Where the check goes

`gpu_agent/gate.py::check_finding`, in the existing loop over `f.evidence`.

This is the single shared gate. `gpu_agent/extraction/extractor.py` calls it (line ~144)
right after its own verbatim check, and `check_scorecard` calls it for every finding in a
scorecard — which is how `gpu_agent/judgment/judge.py` and `gpu_agent/pipeline.py` reach it.
Putting the length check in the extractor next to the verbatim check would cover only the
extraction path; putting it in `check_finding` covers **every path that runs the gate**,
which is what F127 asks for.

One honest caveat, raised in code review. `gpu_agent/wiki/ingest.py::route_findings` appends
straight into the finding store without calling `check_finding`, and the CLI verb behind it
(`wiki-ingest --findings`) validates its input against the schema only. So a hand-written
findings file can put an over-long excerpt into `store/` without meeting this rule. That hole
is **pre-existing and not F127's**: every other `check_finding` rule (F2e, F8, F17) is bypassed
by exactly the same path, and in a normal cycle that file is the already-gated output of
`extract`. Closing it would change behaviour for every gate rule at once and belongs in its
own item, not here.

## Counting

**Words:** `len(excerpt.split())`. Boring, stdlib, matches how the posture doc's own
measurement was taken.

**Sentences:** count `.`/`!`/`?` runs that are followed by whitespace or end-of-string, minus
the ones that are not really sentence ends:

- a known abbreviation (`U.S.`, `Inc.`, `Corp.`, `e.g.`, `No.`, `vs.`, …);
- a single-letter token, which catches initials and the tail of `U.S.`;
- a decimal point (`$6.7B`, `54.3%`) — the "followed by whitespace" rule already excludes
  these, since a digit follows the dot.

Two further rules, both added after code review found the first draft over-counting:

- a terminator only counts when end-of-text or a **capital or digit** follows it. Real prose
  capitalises after a full stop; an abbreviation does not. This is what separates "Rev. was
  up" and "the Fed. raised" from a genuine sentence end, without needing them on a list;
- a token with a period **inside** it is an acronym, a pair of initials, or a numbered label
  ("A.I.", "Ph.D.", "J.H.", "2.1."), never a sentence end.

Errors are deliberately biased toward **under**-counting. Under-counting lets a long excerpt
through; over-counting rejects a legitimate one. Since the sentence count only matters once
an excerpt is already over 50 words, and the 100-word backstop catches genuine bulk, leniency
is the safe direction.

**The counter is not infallible, and this is the case that survives:** an abbreviation that is
both unlisted and followed by a capitalised word still reads as a full stop and over-counts by
one. That is precisely why the gate requires BOTH limits to be broken rather than trusting the
sentence count alone. Anyone tightening the counter must re-run the store audit first.

Minimum returned is 1, so an excerpt with no terminal punctuation counts as one sentence.

## Testing

1. Unit tests on the counters: abbreviations, decimals, initials, no-punctuation, quotes.
2. Gate tests: over both limits rejected; over words only accepted; over sentences only
   accepted; over the absolute cap rejected; message wording pinned.
3. Extraction-path test proving a long excerpt lands in `dropped` with the new violation,
   the same way an invented excerpt already does.
4. A store test asserting **no committed excerpt** would be rejected by this gate — the
   guarantee that this change is not retroactively destructive.

## Explicitly out of scope

Prompt bytes. No prompt file, vocab glue, or registry data is touched, so
`tests/test_evals_baseline_pin.py` (F6) must stay green and byte-identical. Verified in-lane.

The store is append-only; nothing already committed is edited.
