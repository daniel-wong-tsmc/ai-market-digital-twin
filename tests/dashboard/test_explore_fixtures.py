"""The one shared fixture every later Explore-layer test file imports (F101c Task 1)."""
import json

from gpu_agent.narrator.store import StoryStore
from gpu_agent.schema.finding import Confidence, Finding, Impact
from gpu_agent.wiki.page import WikiPage, dump_page

from tests.dashboard.test_story_model import _store
from tests.narrator.test_store import _art

CAT = "chips.merchant-gpu"


def _wiki_page(page_id: str, title: str) -> str:
    page = WikiPage(id=page_id, type="entity", title=title, category=CAT,
                     status="registered", state="steady", trajectory="flat",
                     salience=0.5, createdAsOf="2026-06", lastUpdatedAsOf="2026-07")
    body = (
        f"## Background\n\n{title} is a company tracked by this desk.\n\n"
        "## Recent activity\n\n"
        f"- {title} shipped new capacity\n"
        f"- {title} raised guidance\n"
    )
    return dump_page(page, body)


def _finding(fid: str, *, side: str, entity: str, polarity_demand: int = 0,
             polarity_supply: int = 0, magnitude: int = 2) -> dict:
    finding = Finding(
        id=fid, statement=f"{entity} finding {fid}", kind="observed", trend="flat",
        why="w", impact=Impact(targets=[entity], direction="positive", mechanism="m"),
        confidence=Confidence(level="medium", basis="b"), asOf="2026-07",
        indicatorId="D2" if side == "demand" else "S10", side=side,
        polarityDemand=polarity_demand, polaritySupply=polarity_supply,
        magnitude=magnitude, entity=entity, observedAt="2026-07-20",
        capturedAt="2026-07-20T00:00:00Z")
    return json.loads(finding.model_dump_json())


def _explore_store(tmp_path):
    root = _store(tmp_path)

    wiki_dir = root / "wiki" / "entity"
    wiki_dir.mkdir(parents=True, exist_ok=True)
    (wiki_dir / "nvidia.md").write_text(_wiki_page("nvidia", "Nvidia"), encoding="utf-8")
    (wiki_dir / "tsmc.md").write_text(_wiki_page("tsmc", "TSMC"), encoding="utf-8")

    findings_dir = root / "findings"
    findings_dir.mkdir(parents=True, exist_ok=True)
    fa = _finding("fa", side="demand", entity="nvidia", polarity_demand=1)
    fb = _finding("fb", side="supply", entity="tsmc", polarity_supply=-1)
    fc = _finding("fc", side="demand", entity="NVDA", polarity_demand=1, magnitude=1)
    for name, data in (("fa", fa), ("fb", fb), ("fc", fc)):
        (findings_dir / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")

    st = StoryStore(root)
    st.write(_art("2026-07-22", headline="Yesterday's H"))
    st.write(_art("2026-07-21", fell_back=True))

    return root
