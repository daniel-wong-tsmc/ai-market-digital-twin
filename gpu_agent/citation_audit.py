"""F66 Phase 1 — post-hoc citation audit over finished story scenes + implication lines.

Every existing citation gate is a *referential-integrity* check ("does this id
resolve?"). None is a *support* check ("does this finding actually say that?").
This module is the deterministic, LLM-free half of the support check: for each
claim, build the set of numeric tokens its cited findings can back, then verify
every number in the finished prose is in that set (allowing honest rounding).

Reads finished artifacts only -- `store/<cat>/story/<date>.json`,
`store/implications/<cat>/<asOf>.json` and `store/findings/` -- and writes
`store/<cat>/audit/<date>.json`. It touches no frozen-core file, no brain prompt,
and changes no existing gate's behaviour.

Leaf module: it imports the shared tokenizer, the canonical FindingStore and the
two artifact stores, and nothing from `gpu_agent.dashboard`. The self-computed
KPI/price-series values (D5b) arrive as `extra_texts` from the CLI layer, which
is what keeps this module free of a dashboard dependency (user-approved
2026-07-29, sourcing option (a)).

Phase 2 -- a tool-less reading subagent returning supported/unsupported/overstated
-- is deferred to ride F81. `ClaimResult.verdict` already carries the field it
will annotate, so no schema migration is needed then.
"""
from __future__ import annotations

import os
import pathlib
from dataclasses import dataclass
from typing import Literal, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field

from gpu_agent.implication import ImplicationArtifact, ImplicationStore
from gpu_agent.narrator.schema import StoryArtifact
from gpu_agent.narrator.store import StoryStore
from gpu_agent.numeric_tokens import numeric_tokens, supported, value_renderings
from gpu_agent.schema.finding import Finding
from gpu_agent.store import FindingStore

SCHEMA_VERSION = 1


# --- the unit of audit --------------------------------------------------------

@dataclass(frozen=True)
class Claim:
    """One auditable assertion: prose plus the findings it says it rests on."""
    claimKey: str
    text: str
    findingIds: tuple[str, ...]


def claims_from_story(art: StoryArtifact) -> list[Claim]:
    """One claim per scene. `scene:<n>` matches the evidence-map key the story
    renderer already uses (dashboard/story_model.py:637)."""
    return [Claim(claimKey=f"scene:{sc.n}",
                  text=" ".join(sc.paragraphs),
                  findingIds=tuple(sc.claimFindingIds))
            for sc in art.scenes]


def claims_from_bullets(art: StoryArtifact) -> list[Claim]:
    """One claim per bullet, keyed by list order (`bullet:<i>`) -- bullets carry
    no id of their own, so this mirrors `claims_from_implication`'s `impl:<i>`
    pattern rather than the scene's own-numbered `scene:<n>`. `bullets` is None
    on a pre-F114 (v1) artifact; that contributes zero claims, which is what
    keeps v1 audits identical to their pre-F114 behaviour."""
    if not art.bullets:
        return []
    return [Claim(claimKey=f"bullet:{i}", text=b.text,
                  findingIds=tuple(b.claimFindingIds))
            for i, b in enumerate(art.bullets)]


def claims_from_implication(art: ImplicationArtifact) -> list[Claim]:
    """One claim per line, keyed by dispatch order (the lines carry no id)."""
    return [Claim(claimKey=f"impl:{i}",
                  text=line.watchItem,
                  findingIds=tuple(line.findingIds))
            for i, line in enumerate(art.lines)]


# --- findings ----------------------------------------------------------------

class FindingsReader:
    """Thin read-only adapter over the canonical FindingStore (`store/findings/`).

    Differs from FindingStore in one way only: an id that does not resolve, or a
    file that will not parse, returns None instead of raising -- the audit reports
    an unresolved citation as a finding of its own rather than crashing the cycle.
    """

    def __init__(self, findings_root: str | pathlib.Path):
        self._store = FindingStore(pathlib.Path(findings_root))

    def get(self, finding_id: str) -> Optional[Finding]:
        try:
            if not self._store.exists(finding_id):
                return None
            return self._store.get(finding_id)
        except Exception:  # noqa: BLE001 -- unsafe id, unreadable file, or a payload
            # that no longer validates: all are "this citation does not resolve".
            return None


def allowed_tokens(claim: Claim, reader: FindingsReader,
                   extra_texts: Sequence[str] = ()) -> tuple[set[str], list[str]]:
    """The numeric tokens this claim is entitled to use, plus its unresolved ids.

    The pool is the WIDE one, and that is measured, not assumed: a statement-only
    pool flags day-of-month tokens that live in evidence dates (spec section 4).
    It is also strictly per-claim -- a number that exists elsewhere in the store
    but in a finding this claim does not cite is a mis-attribution, and must flag.
    """
    pool: set[str] = set()
    unresolved: list[str] = []
    for fid in claim.findingIds:
        f = reader.get(fid)
        if f is None:
            unresolved.append(fid)
            continue
        parts = [f.statement, f.why]
        if f.value is not None:
            parts.extend(value_renderings(f.value.number))
        for e in f.evidence:
            parts.append(e.excerpt)
            parts.append(e.date)
        for p in parts:
            pool |= numeric_tokens(p)
    for t in extra_texts:
        pool |= numeric_tokens(t)
    return pool, unresolved


# --- verdicts + artifact ------------------------------------------------------

class ClaimResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claimKey: str
    verdict: Literal["clean", "flagged", "skipped"]
    flaggedTokens: list[str] = Field(default_factory=list)
    unresolvedIds: list[str] = Field(default_factory=list)
    citedFindingIds: list[str] = Field(default_factory=list)


class AuditArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schemaVersion: Literal[1]
    categoryId: str
    asOf: str
    claims: list[ClaimResult] = Field(default_factory=list)
    summary: dict[str, int] = Field(default_factory=dict)


def audit_claim(claim: Claim, reader: FindingsReader,
                extra_texts: Sequence[str] = ()) -> ClaimResult:
    """Audit one claim.

    A claim citing nothing is SKIPPED, not flagged: both write-time gates already
    enforce an honest-empty posture there (a sourceless scene must carry
    NO_SOURCE_LINE; an implication line may cite a dimension only), so flagging it
    would punish the honest case.
    """
    cited = list(claim.findingIds)
    if not cited:
        return ClaimResult(claimKey=claim.claimKey, verdict="skipped",
                           citedFindingIds=[])
    pool, unresolved = allowed_tokens(claim, reader, extra_texts)
    flagged = sorted(t for t in numeric_tokens(claim.text) if not supported(t, pool))
    verdict = "flagged" if (flagged or unresolved) else "clean"
    return ClaimResult(claimKey=claim.claimKey, verdict=verdict,
                       flaggedTokens=flagged, unresolvedIds=unresolved,
                       citedFindingIds=cited)


def _read_implication(store_root: pathlib.Path, category_id: str,
                      date: str) -> Optional[ImplicationArtifact]:
    """Implication artifacts are keyed by the scorecard's asOf (month grain today),
    while stories are keyed by day, so an exact hit on `date` is the exception.
    Resolution mirrors the repo's existing reader (dashboard/brief_model.py:100-108):
    exact match first, else the latest artifact in the directory. A missing
    artifact is normal and contributes zero claims."""
    root = pathlib.Path(store_root) / "implications" / category_id
    store = ImplicationStore(root)
    try:
        return store.load(date)
    except Exception:  # noqa: BLE001 -- no exact-date artifact; fall back to latest.
        pass
    try:
        candidates = sorted(p for p in root.iterdir() if p.suffix == ".json")
    except OSError:
        return None
    if not candidates:
        return None
    try:
        return ImplicationArtifact.model_validate_json(
            candidates[-1].read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 -- an unreadable artifact contributes no claims.
        return None


def run_audit(store_root: str | pathlib.Path, category_id: str, date: str,
              extra_texts: Sequence[str] = ()) -> AuditArtifact:
    """Audit a cycle's story scenes and implication lines. A missing story artifact
    is an empty clean result, not a crash -- not every cycle writes a story."""
    root = pathlib.Path(store_root)
    reader = FindingsReader(root / "findings")

    claims: list[Claim] = []
    story = StoryStore(root).read(category_id, date)
    if story is not None:
        claims.extend(claims_from_story(story))
        claims.extend(claims_from_bullets(story))
    impl = _read_implication(root, category_id, date)
    if impl is not None:
        claims.extend(claims_from_implication(impl))

    results = [audit_claim(c, reader, extra_texts) for c in claims]
    return AuditArtifact(
        schemaVersion=SCHEMA_VERSION,
        categoryId=category_id,
        asOf=date,
        claims=results,
        summary={
            "claimsAudited": len(results),
            "flagged": sum(1 for r in results if r.verdict == "flagged"),
            "skipped": sum(1 for r in results if r.verdict == "skipped"),
        },
    )


class AuditStore:
    """<store>/<categoryId>/audit/<date>.json -- one audit record per cycle.

    Mirrors the story artifact's layout and its atomic write (.json.tmp + os.replace).
    No .gitignore entry is needed: `store/<cat>/` is already whitelisted wholesale,
    exactly as `story/` is.
    """

    def __init__(self, root: str | pathlib.Path):
        self.root = pathlib.Path(root)

    def _path(self, category_id: str, date: str) -> pathlib.Path:
        return self.root / category_id / "audit" / f"{date}.json"

    def write(self, artifact: AuditArtifact) -> pathlib.Path:
        p = self._path(artifact.categoryId, artifact.asOf)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(artifact.model_dump_json(indent=2), encoding="utf-8")
        os.replace(tmp, p)
        return p

    def read(self, category_id: str, date: str) -> Optional[AuditArtifact]:
        p = self._path(category_id, date)
        if not p.exists():
            return None
        try:
            return AuditArtifact.model_validate_json(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return None
