import re
from gpu_agent.gathering.ingest import _doc_id, normalize_documents
from gpu_agent.gathering.dedup import content_hash

URL = "https://www.runpod.io/pricing"
AS_OF = "2026-07"


def _blob(content, url=URL):
    return {"source": "RunPod", "url": url, "date": "2026-07-25",
            "entity": "runpod", "content": content}


def test_same_content_same_id():
    a = _doc_id(URL, AS_OF, content_hash("B200 $3.29/hr"))
    b = _doc_id(URL, AS_OF, content_hash("B200  $3.29/hr"))  # whitespace folded
    assert a == b


def test_changed_content_new_id():
    a = _doc_id(URL, AS_OF, content_hash("B200 $3.29/hr"))
    b = _doc_id(URL, AS_OF, content_hash("B200 $2.99/hr"))   # the v15 price move
    assert a != b
    # same slug: strip "-{AS_OF}" (AS_OF itself contains a hyphen, e.g. "2026-07") then
    # strip the trailing "-{digest}" segment — a plain rsplit(-, 2) would leave the
    # (differing) digest attached to the remainder since AS_OF has an internal hyphen.
    a_prefix = a[: -len(AS_OF) - 1].rsplit("-", 1)[0]
    b_prefix = b[: -len(AS_OF) - 1].rsplit("-", 1)[0]
    assert a_prefix == b_prefix
    assert a.endswith(AS_OF) and b.endswith(AS_OF)           # same vintage


def test_distinct_urls_never_merge():
    h = content_hash("identical body")
    assert _doc_id(URL, AS_OF, h) != _doc_id("https://lambda.ai/pricing", AS_OF, h)


def test_id_shape_unchanged():
    got = _doc_id(URL, AS_OF, content_hash("x"))
    assert re.fullmatch(r"www-runpod-io-[0-9a-f]{8}-2026-07", got)


def test_normalize_documents_threads_content(tmp_path):
    out1 = normalize_documents([_blob("B200 $3.29/hr")],
                                primary_sources=[], as_of=AS_OF)
    out2 = normalize_documents([_blob("B200 $2.99/hr")],
                                primary_sources=[], as_of=AS_OF)
    assert out1.documents[0].id != out2.documents[0].id
    out3 = normalize_documents([_blob("B200 $3.29/hr")],
                                primary_sources=[], as_of=AS_OF)
    assert out1.documents[0].id == out3.documents[0].id
