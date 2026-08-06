# F114 — Narrator-Authored "What Changed" Bullets

Date: 2026-08-06. All decisions interactive user decisions (screenshot review session) — ZERO
AFK-defaults. Follow-up to F110. **GATED LANE: prompt-affecting (narrator prompt + pin).**

## 1. Problem

F110 builds the three "What changed" bullets mechanically (scene title + first sentence,
chopped). The 2026-08-06 output proved scissors can't write: "The alternatives are real. They
are dated 2027 and 2028. MediaTek is the newest name trying to widen the supply." — no
antecedent for "dated 2027 and 2028", no reason WHY MediaTek matters. User decision: the
narrator brain writes the bullets itself; each must be self-contained, concrete, and concise.

## 2. What changes

- **Narrator schema** (`gpu_agent/narrator/schema.py`): story artifact gains `bullets` —
  exactly 3 objects `{text: str, claimFindingIds: [str]}`. Narrator prompt gains a section:
  write the day's three takeaways an executive can repeat in a meeting; each ≤ 28 words,
  self-contained (a reader who sees ONLY the bullet understands it), at least one concrete
  anchor (name + number or name + date), plain English, no acronyms.
- **Narrator gate** (`gpu_agent/narrator/gate.py`) additions, all mechanical: exactly 3; word
  cap; each bullet contains ≥ 1 digit; no bullet begins with a pronoun (They/It/These/Those);
  banned-word + outlet-string checks extended to bullets; `claimFindingIds` non-empty and every
  id resolves. Gate failure → the existing re-dispatch ×2 → fallback path.
- **Citation audit (F66)** extends to bullet numbers exactly as it covers scene numbers.
- **Exporter** (`gpu_agent/dashboard/bullets.py`): artifact `bullets` become THE bullets
  (`sources` from `claimFindingIds` via `refs_for_finding_ids`); the mechanical condenser
  remains ONLY as the fallback when the artifact predates this schema or the narrator fell back.
- **Narrator prompt pin** (`fixtures/narrator/prompt-pin.json`) re-recorded in the same commit
  as the prompt change (the F101b/F103 lockstep pattern).

## 3. Guardrails

- GATED-LANE RULES: no other prompt-affecting lane while open. MUST NOT TOUCH: the F6 eval
  baseline (`fixtures/evals/` byte-untouched — this lane cannot redden F6), `gpu_agent/evals/`,
  extract/judge/thesis prompts, `scoring.py`, `report.py`, registry indicator files.
- The ONLY pins that move: narrator prompt pin (re-recorded deliberately) and F83 ONLY IF a
  run-cycle step changes (none is expected — bullets ride the existing narrator step; if a step
  change becomes necessary, QUESTION-STOP first).
- Quality mechanism stays gate + pin, NO scored eval bar (the F101b user decision carries over).
- Schema version bump on the story artifact; old artifacts remain readable (fallback path).

## 4. Sequencing

Build FIRST, before F113 (this is the exclusive prompt lane and the smaller diff; both touch
`bullets.py` and the web bullet components). F113 dispatches only after this lane merges.

## 5. Live criteria (post-merge, not forced)

1. The next live cycle's artifact contains 3 gate-passing bullets, each self-contained with a
   concrete anchor, and the live page renders them with inline end-of-sentence source markers.
2. Citation audit covers the bullets (bullet numbers appear in `claimsAudited`).
3. A run where the narrator falls back still produces a page (mechanical bullets, no crash).
