import json
import pathlib
import pytest
from pydantic import ValidationError
from gpu_agent.manifest import HUGGINGNEWS_TAG_SLUGS, CoverageManifest

def _base(**over):
    d = {"version": "1", "categoryId": "chips.test", "asOf": "2026-07"}
    d.update(over)
    return d

def test_valid_tags_load():
    m = CoverageManifest.model_validate(_base(huggingnewsTags=["ai-compute-chips"]))
    assert m.huggingnewsTags == ["ai-compute-chips"]

def test_second_category_reaches_source_with_zero_new_code():
    # spec acceptance 5: the desk-wide criterion — a different category declares
    # different slugs and the same field/validator serves it
    m = CoverageManifest.model_validate(_base(
        categoryId="models.frontier-closed",
        huggingnewsTags=["ai-model-releases", "ai-research-evals"]))
    assert m.huggingnewsTags == ["ai-model-releases", "ai-research-evals"]

def test_absent_field_defaults_empty():
    assert CoverageManifest.model_validate(_base()).huggingnewsTags == []

def test_unknown_slug_fails_loud():
    with pytest.raises(ValidationError, match="huggingnews"):
        CoverageManifest.model_validate(_base(huggingnewsTags=["ai-compute-chipz"]))

def test_allowlist_matches_published_tree():
    # the slug tree published in huggingnews.com/SKILL.md v0.0.2 (spec §What HuggingNews is)
    assert {"ai-compute-chips", "ai-model-releases", "ai-open-models",
            "ai-research-evals", "ai-fundraising", "ai-policy-regulation",
            "ai-sector-impact"} <= HUGGINGNEWS_TAG_SLUGS

def test_real_gpu_manifest_declares_chips_tag():
    raw = json.loads(pathlib.Path("manifests/chips.merchant-gpu.json").read_text("utf-8"))
    m = CoverageManifest.model_validate(raw)
    assert m.huggingnewsTags == ["ai-compute-chips"]
