"""F105: a malformed answer envelope must fail loud, never validate as an empty result.

The v19 headless run's brain returned bare FindingDraft objects without the
{"drafts":[...]} wrapper; ExtractionResult (extra keys ignored, drafts defaulted to [])
accepted it as EMPTY and extract --recorded reported "0 findings, 0 dropped" with exit 0.
"""
import json
import pytest
from pydantic import ValidationError
from gpu_agent.llm.client import LLMError
from gpu_agent.llm.recorded import RecordedClient
from gpu_agent.extraction.extractor import ExtractionResult, extract_findings
from gpu_agent.schema.raw_document import RawDocument

def _doc():
    return RawDocument(id="doc-1", source="NVIDIA 10-Q", url="u", date="2026-05",
                       tier="primary", entity="nvidia", content="DC revenue grew 8% QoQ.")

def _good_draft():
    return {"statement": "DC growth flattened", "kind": "measured",
            "value": {"number": 8.0, "unit": "% QoQ"}, "trend": "rising", "why": "digestion",
            "impact": {"targets": ["chips.merchant-gpu"], "direction": "mixed", "mechanism": "caps DMI"},
            "evidence": [{"source": "NVIDIA 10-Q", "url": "u", "date": "2026-05-01", "excerpt": "8%"}],
            "confidence": {"level": "high", "basis": "filing"}, "indicatorId": "D2",
            "polarityDemand": 1, "polaritySupply": 0, "magnitude": 2,
            "entity": "NVDA", "observedAt": "2026-05-01"}

def _kwargs():
    return dict(as_of="2026-06", captured_at="2026-06-12T00:00:00Z", extraction_model="claude-opus-4-8")

def test_bare_draft_without_envelope_fails_loud():
    # the exact v19 shape: a FindingDraft object where {"drafts":[...]} belongs
    client = RecordedClient([json.dumps(_good_draft())])
    with pytest.raises(LLMError):
        extract_findings(_doc(), client, **_kwargs())

def test_missing_drafts_key_rejected():
    with pytest.raises(ValidationError):
        ExtractionResult.model_validate({})

def test_extra_keys_rejected():
    with pytest.raises(ValidationError):
        ExtractionResult.model_validate({"drafts": [], "findings": []})

def test_explicit_empty_drafts_still_valid():
    # an explicit "no findings in this doc" answer remains legitimate
    assert ExtractionResult.model_validate({"drafts": []}).drafts == []
