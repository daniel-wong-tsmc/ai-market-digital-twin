# gpu_agent/narrator/store.py
"""Story artifacts: store/<category>/story/YYYY-MM-DD.json."""
from __future__ import annotations

import json
import os
from pathlib import Path

from gpu_agent.narrator.schema import StoryArtifact


class StoryStore:
    def __init__(self, root: Path):
        self.root = Path(root)

    def _path(self, category_id: str, story_date: str) -> Path:
        return self.root / category_id / "story" / f"{story_date}.json"

    def write(self, artifact: StoryArtifact) -> Path:
        p = self._path(artifact.categoryId, artifact.storyDate)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(artifact.model_dump_json(indent=2), encoding="utf-8")
        os.replace(tmp, p)
        return p

    def read(self, category_id: str, story_date: str) -> StoryArtifact | None:
        p = self._path(category_id, story_date)
        if not p.exists():
            return None
        try:
            return StoryArtifact.model_validate_json(
                p.read_text(encoding="utf-8"))
        except Exception:
            return None

    def recent_headlines(self, category_id: str, before: str,
                         limit: int = 7) -> list[dict]:
        d = self.root / category_id / "story"
        if not d.exists():
            return []
        out = []
        for p in sorted(d.glob("*.json"), reverse=True):
            date = p.stem
            if date >= before:
                continue
            art = self.read(category_id, date)
            if art:
                out.append({"date": date, "headline": art.headline,
                            "fellBack": art.narratorMeta.fellBack})
            if len(out) == limit:
                break
        return out
