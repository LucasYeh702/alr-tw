import json

import pytest

from alr_tw.cli import main
from alr_tw.research.workflow_guidance import (
    build_error_guidance,
    build_research_guidance,
    build_validation_guidance,
)
from alr_tw.workflow_cli import MAX_DRAFT_BYTES, read_draft


@pytest.mark.parametrize("status,count,mode,expected", [
    ("in_progress", 0, "refusal_only", "in_progress"),
    ("blocked", 0, "refusal_only", "no_verified_material"),
    ("blocked", 3, "refusal_only", "research_blocked"),
    ("ready_for_draft", 5, "conditional", "bounded_material_ready"),
    ("unexpected", None, "conditional", "unknown"),
])
def test_progress_is_not_an_answer_and_does_not_invent_zero(status, count, mode, expected):
    result = build_research_guidance({
        "status": status, "verified_source_count": count, "answer_mode": mode,
        "answer_text": "PRIVATE_DRAFT", "verified_sources": [{"url": "https://invalid.test"}],
    }, depth="quick")
    assert result["scenario"] == expected
    assert result["verified_source_count"] == count
    assert result["answer_authorized"] is False
    assert "PRIVATE_DRAFT" not in json.dumps(result)
    assert "invalid.test" not in json.dumps(result)


@pytest.mark.parametrize("decision,safe", [("validated", True), ("qualified", True),
                                           ("blocked", False), ("validated", "true")])
def test_validation_guidance_cannot_grant_authority(decision, safe):
    result = build_validation_guidance({
        "decision": decision, "safe_to_present": safe, "answer_text": "PRIVATE_DRAFT",
        "blockers": ["CLAIM_CITATION_BINDING_REQUIRED"],
    })
    assert result["answer_authorized"] is False
    assert result["scenario"] == (decision if safe is True else "draft_blocked")
    assert "PRIVATE_DRAFT" not in json.dumps(result)


def test_expiry_does_not_change_the_requested_legal_date():
    result = build_error_guidance("RESEARCH_RUN_EXPIRED")
    assert "保留原問題要求的法律適用日期" in result["next_steps"][0]
    assert result["verified_source_count"] is None


@pytest.mark.parametrize("payload", [
    {"answer_text": "PRIVATE_DRAFT", "claim_bindings": [], "evidence": []},
    {"answer_text": "PRIVATE_DRAFT", "claim_bindings": None},
    {"answer_text": "   ", "claim_bindings": []},
])
def test_draft_rejects_trust_injection_without_echoing_text(payload, tmp_path, capsys):
    path = tmp_path / "draft.json"
    path.write_text(json.dumps(payload))
    assert main(["validate-draft", "--run", "unused", "--input", str(path)]) == 2
    output = capsys.readouterr().out
    assert "PRIVATE_DRAFT" not in output
    assert json.loads(output)["error"] == "DRAFT_INPUT_INVALID"


def test_bounded_draft_read(tmp_path):
    path = tmp_path / "large.json"
    path.write_bytes(b" " * (MAX_DRAFT_BYTES + 1))
    with pytest.raises(ValueError, match="DRAFT_INPUT_TOO_LARGE"):
        read_draft(str(path))


@pytest.mark.parametrize("codes", [None, "CLAIM_SUPPORT_UNCHECKED", {}, [None, 3]])
def test_malformed_blocker_projection_has_safe_fallback(codes):
    result = build_validation_guidance({"decision": "blocked", "blockers": codes})
    assert result["scenario"] == "draft_blocked"
    assert result["answer_authorized"] is False


def test_multiple_duplicate_and_unmapped_blockers_do_not_echo_input():
    result = build_validation_guidance({
        "decision": "blocked", "blockers": [
            "CLAIM_SUPPORT_UNCHECKED", "CLAIM_SUPPORT_UNCHECKED",
            "CLAIM_ROLE_ERROR", "PRIVATE_OR_UNKNOWN_REASON",
        ],
    })
    assert len(result["missing_items"]) == 2
    assert len(result["next_steps"]) == 2
    assert "PRIVATE_OR_UNKNOWN_REASON" not in json.dumps(result)


@pytest.mark.parametrize("count", [None, "unknown", -1, True])
def test_unknown_blocked_count_is_not_invented_as_zero_or_positive(count):
    result = build_research_guidance({
        "status": "blocked", "verified_source_count": count,
    }, depth="standard")
    assert result["verified_source_count"] is None
    assert result["scenario"] == "research_blocked"
    assert "已有" not in result["missing_items"][0]


def test_standard_ready_guidance_does_not_claim_quick_success():
    result = build_research_guidance({
        "status": "ready_for_draft", "verified_source_count": 1,
    }, depth="standard")
    assert result["scenario"] == "material_ready"
    assert result["answer_authorized"] is False
