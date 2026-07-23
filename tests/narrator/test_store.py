from gpu_agent.narrator.schema import StoryArtifact
from gpu_agent.narrator.store import StoryStore
from tests.narrator.test_schema import _answer

CAT = "chips.merchant-gpu"


def _art(date, headline="H", fell_back=False):
    return StoryArtifact.model_validate({
        "schemaVersion": 1, "categoryId": CAT, "storyDate": date,
        **_answer(headline=headline),
        "narratorMeta": {"model": "opus", "promptHash": "x", "retries": 0,
                          "fellBack": fell_back, "wroteAt": f"{date}T09:00:00"}})


def test_write_read_roundtrip(tmp_path):
    st = StoryStore(tmp_path)
    p = st.write(_art("2026-07-23"))
    assert p == tmp_path / CAT / "story" / "2026-07-23.json"
    assert st.read(CAT, "2026-07-23").headline == "H"
    assert st.read(CAT, "2026-01-01") is None


def test_read_corrupt_artifact_returns_none(tmp_path, capsys):
    st = StoryStore(tmp_path)
    p = st._path(CAT, "2026-07-23")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{not valid json", encoding="utf-8")
    assert st.read(CAT, "2026-07-23") is None
    assert "unreadable" in capsys.readouterr().err


def test_same_date_overwrites(tmp_path):
    st = StoryStore(tmp_path)
    st.write(_art("2026-07-23", headline="first"))
    st.write(_art("2026-07-23", headline="second"))
    assert st.read(CAT, "2026-07-23").headline == "second"


def test_recent_headlines_window(tmp_path):
    st = StoryStore(tmp_path)
    for d in ["2026-07-15", "2026-07-16", "2026-07-22", "2026-07-23"]:
        st.write(_art(d, headline=f"H {d}", fell_back=(d == "2026-07-16")))
    heads = st.recent_headlines(CAT, before="2026-07-23", limit=7)
    assert [h["date"] for h in heads] == ["2026-07-22", "2026-07-16", "2026-07-15"]
    assert heads[1]["fellBack"] is True
