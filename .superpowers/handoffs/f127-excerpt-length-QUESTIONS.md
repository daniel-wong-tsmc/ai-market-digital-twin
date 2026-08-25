# F127 — design forks and AFK-default decisions

The user was AFK for this entire lane. **Nothing below was user-approved.** Each item is an
AFK-default: a choice made on best judgment, recorded so it can be overturned on review.

The standing question-stop rule in CLAUDE.md says a lane should park on a design fork rather
than pick one. This lane's dispatch brief instead directed AFK-default recording. Flagging
the tension rather than hiding it, same as F124 did.

---

## 1. "two sentences **or** 50 words" — read as OR, not AND

**AFK-default: reject only an excerpt that breaks BOTH limits.**

The dispatch brief suggested a hard 50-word cap (">50 words rejected") and a hard 2-sentence
cap. Re-measuring the store falsified the assumption behind that suggestion. The brief said
to verify that "the new gate would not have rejected anything already in the store"; under a
hard 50-word cap, it would have.

Measured across all 644 committed excerpts (the posture doc's 334 figure is stale):

- 1 excerpt over 50 words — **70 words, one sentence**, a verbatim AMD 10-Q gross-margin
  sentence (`store/findings/ir-amd-com-cfa508a5-2026-08-3.json`).
- 2 excerpts over 2 sentences — 29 words/4 sentences and 36 words/3 sentences, both short.
- **0 excerpts break both limits.**

Reasons for the OR reading:

1. It is what the DECIDED text literally says. Changing "or" to "and" would be tightening a
   decided norm without the user in the room.
2. The posture doc justifies the norm by saying it "costs nothing today". Only the OR
   reading is actually free; AND would have cost three real findings.
3. The harm the norm guards against is reproducing an article. A long single sentence quoted
   from a filing is not that; several sentences totalling 60+ words is closer to it.

**Overturn cost if the user wanted AND:** one constant and one `and`/`or` in `gate.py`, plus
a decision about the three stored excerpts that would then be non-conforming.

## 2. A 100-word absolute backstop was added

**AFK-default: reject any excerpt over 100 words regardless of sentence count.**

Not in the posture doc. Added because without it the OR rule has a trivial bypass: any text
with no sentence-ending punctuation counts as one sentence and passes at any length, so the
gate would not be a gate. 100 is twice the stated norm and well above the largest excerpt
ever stored (70 words). The doc's "never more than is needed" clause supports a ceiling in
spirit even though it names no number.

## 3. Sentence counting is in code, not left as documented norm

**AFK-default: implement it.**

The brief allowed dropping sentence counting if it proved too fragile. It did not, though the first draft was wrong and
code review caught it. The hard cases in real financial prose are abbreviations (`U.S.`,
`Inc.`, `Rev.`, `Calif.`), dotted acronyms (`A.I.`, `Ph.D.`), initials, numbered labels
(`2.1.`), quarter labels (`Q3.`, `FY26.`) and decimals (`$6.7B`, `54%`) — about twenty-five
lines of stdlib once the right rules are found.

The first draft claimed counting errors were always biased safe. **That claim was false**, and
the review demonstrated a realistic 58-word two-sentence passage being rejected by the gate.
Fixed by requiring a capital after a terminator and by never treating a token with an internal
period as a sentence end. The claim is now qualified rather than absolute: an abbreviation that
is unlisted AND followed by a capitalised word still over-counts by one. The gate tolerates
that because it requires BOTH limits to be broken, never the sentence count alone.

## 4. The check lives in `gate.py::check_finding`, not in the extractor

**AFK-default: shared gate.**

The brief pointed at the verbatim check in `gpu_agent/extraction/extractor.py` (~line 138),
but that check needs the fetched document and so cannot move. The length check needs only the
excerpt itself. `check_finding` is the one function the extractor,
`judgment/judge.py` and `pipeline.py` all route through (the latter two via
`check_scorecard`), so putting it there covers every path that runs the gate rather than
one.

Caveat surfaced by code review: `wiki/ingest.py::route_findings` writes into the finding
store WITHOUT calling `check_finding`, so `gpu-agent wiki-ingest --findings <file>` can put
an over-long excerpt into `store/`. That is pre-existing and not F127's — every other gate
rule (F2e, F8, F17) has the identical hole, and in a normal cycle that file is the gated
output of `extract`. Closing it would change behaviour for every gate rule at once and needs
its own item.

## 5. Nothing in the store was edited

**AFK-default: leave committed findings alone.**

The store is append-only by design. Under the rule as built, nothing stored is
non-conforming anyway, so no exemption list was needed.

## 6. The handoff file was force-added to git

**AFK-default: `git add -f .superpowers/handoffs/f127-excerpt-length-DONE.md`.**

`.superpowers/` is in `.gitignore`, and every prior lane's DONE handoff is untracked and
lives in the root checkout. The dispatch brief explicitly said to commit the handoff on the
branch, and the brief also forbids writing to the root checkout — so the only way to stop the
handoff dying with the worktree was to force-add it. Convention break, flagged here. If the
coordinator prefers the old convention, `git rm --cached` it and copy the file to the root
checkout's `.superpowers/handoffs/`.
