"""gpu_agent/narrator/schema.py — the daily narrator's story artifact.

Pattern: gpu_agent/implication.py (ImplicationLine/ImplicationAnswer/ImplicationArtifact).
NarratorAnswer is what the tool-less brain returns; StoryArtifact wraps it with the
gate/store metadata (schemaVersion, categoryId, storyDate, narratorMeta).
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict


class SceneVisual(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["spark"]
    seriesId: str
    label: str


class RelatedDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str
    title: str
    outlet: str
    date: str


class StoryScene(BaseModel):
    model_config = ConfigDict(extra="forbid")
    n: int
    title: str
    paragraphs: list[str]
    visual: Optional[SceneVisual]
    claimFindingIds: list[str]
    sourceLine: str
    relatedDocs: list[RelatedDoc]


class KpiPick(BaseModel):
    model_config = ConfigDict(extra="forbid")
    indicatorId: str
    whyCaption: str
    scene: int


class CalloutMonth(BaseModel):
    model_config = ConfigDict(extra="forbid")
    monthKey: str
    text: str
    scene: int


class NarratorMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: str
    promptHash: str
    retries: int
    fellBack: bool
    wroteAt: str


class StoryBullet(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str
    claimFindingIds: list[str]


class IssueAssessment(BaseModel):
    """The narrator's per-issue assessment (F115). Deliberately narrower than
    IssueLatest.status in gpu_agent/issues.py: the narrator may only say
    improved/worsened/unchanged. It may never say "resolved" (decided solely
    by the streak rule) or "not-assessed" (a system-set default, not
    something the narrator writes)."""
    model_config = ConfigDict(extra="forbid")
    issueId: str
    status: Literal["improved", "worsened", "unchanged"]
    reasoning: str
    claimFindingIds: list[str]


class NarratorAnswer(BaseModel):
    """What the tool-less brain returns; the CLI wraps it into a StoryArtifact."""
    model_config = ConfigDict(extra="forbid")
    headline: str
    deck: str
    scenes: list[StoryScene]
    kpiPicks: list[KpiPick]
    calloutMonths: list[CalloutMonth]
    bullets: Optional[list[StoryBullet]] = None  # None = pre-F114 answer (v1)
    issues: Optional[list[IssueAssessment]] = None  # None = pre-F115 answer (v1/v2)


class StoryArtifact(NarratorAnswer):
    model_config = ConfigDict(extra="forbid")
    schemaVersion: Literal[1, 2, 3]  # was Literal[1, 2]
    categoryId: str
    storyDate: str
    narratorMeta: NarratorMeta
