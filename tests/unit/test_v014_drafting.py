import hashlib
import json
from pathlib import Path

import pytest

from alr_tw.contracts.interop import interoperability_capabilities
from alr_tw.contracts.providers import DataMode
from alr_tw.research.draft_workspace import review_draft
from alr_tw.research.drafting_rules import RULES, RULE_VERSION, lineage_guidance
from alr_tw.research.workflow_guidance import build_research_guidance
from test_v070_civil_analysis import _ready_service
from tw_legal_rag_mcp.mcp_server.server import _server_owned_tool_definitions


def draft(evidence_id, shift=0, prefix=""):
    claim = "行為人違反示範義務時，應負合成測試責任"
    citation = "示範責任法第7條"
    answer = prefix + claim + "（" + citation + "）。"
    start = answer.index(citation)
    return answer, [{"claim_id": "claim", "claim_text": claim, "claim_type": "law_rule",
                     "evidence_ids": [evidence_id], "issue_ids": ["issue-duty"],
                     "citation_occurrences": [{"evidence_id": evidence_id,
                         "citation_text": citation, "start_offset": start + shift,
                         "end_offset": start + len(citation) + shift}]}]


def test_tool_contract_and_template_share_full_rules():
    for tool in _server_owned_tool_definitions():
        if tool["name"] in {"review_legal_draft", "validate_legal_answer", "complete_legal_research"}:
            description = tool["inputSchema"]["properties"]["claim_bindings"]["description"]
            assert all(rule in description for rule in RULES.values())
    template = Path("templates/AGENTS.md").read_text()
    assert RULE_VERSION in template
    assert all(rule in template for rule in RULES.values())
    capabilities = interoperability_capabilities(DataMode.OFFICIAL_ONLY)
    assert capabilities.workflow_guidance["drafting"]["rules"] == RULES
    state_guidance = build_research_guidance({"status": "ready_for_draft"}, depth="quick")
    assert "rules" not in state_guidance["drafting"]
    assert len(json.dumps(state_guidance["drafting"], ensure_ascii=False).encode()) < 512


@pytest.mark.parametrize("shift", [-2, -1, 0, 1, 2])
def test_preparation_is_read_only_and_corrected_bindings_require_full_validation(tmp_path, shift):
    service, run_id, evidence, now = _ready_service(tmp_path)
    answer, bindings = draft(evidence.evidence_id, shift)
    original = json.dumps(bindings)
    before = service.store.validation_material_digest(run_id)
    result = review_draft(service.store, run_id, answer, bindings, now=now)
    prepared = result["citation_preparation"]
    assert prepared["draft_sha256"] == hashlib.sha256(answer.encode()).hexdigest()
    assert not result["safe_to_present"] and not prepared["answer_authorized"]
    assert json.dumps(bindings) == original
    assert service.store.validation_material_digest(run_id) == before
    proposed = prepared["proposals"][0]
    assert proposed["status"] == ("unchanged" if shift == 0 else "proposed")
    if shift:
        rejected = service.validate_answer(run_id, answer, "original", now=now,
                                           claim_bindings=bindings)
        assert not rejected["safe_to_present"]
    bindings[0]["citation_occurrences"] = [proposed["proposed"]]
    checked = service.validate_answer(run_id, answer, "corrected", now=now,
                                      claim_bindings=bindings)
    assert checked["safe_to_present"]


@pytest.mark.parametrize("kind,status", [
    ("duplicate", "ambiguous_text"), ("far", "outside_window"),
    ("separate", "requires_revision"), ("wrong_source", "requires_revision"),
    ("hidden_conclusion", "requires_revision"), ("missing", "text_not_found"),
])
def test_preparation_never_guesses_or_hides_unsupported_text(tmp_path, kind, status):
    service, run_id, evidence, now = _ready_service(tmp_path)
    answer, bindings = draft(evidence.evidence_id, 1)
    occurrence = bindings[0]["citation_occurrences"][0]
    if kind == "duplicate":
        answer += occurrence["citation_text"]
    elif kind == "far":
        occurrence["start_offset"] += 30
        occurrence["end_offset"] += 30
    elif kind == "separate":
        answer = answer.replace("（", "。另一未綁定主張。參見（")
    elif kind == "wrong_source":
        occurrence["evidence_id"] = "unbound"
    elif kind == "hidden_conclusion":
        occurrence["citation_text"] += "且無罪"
        answer = answer.replace("）。", "且無罪）。")
    else:
        occurrence["citation_text"] = "不在答案中的引用"
    result = review_draft(service.store, run_id, answer, bindings, now=now)
    proposal = result["citation_preparation"]["proposals"][0]
    assert proposal["status"] == status
    assert proposal["proposed"] is None
    assert not result["safe_to_present"]


def test_unicode_offsets_use_original_code_points(tmp_path):
    service, run_id, evidence, now = _ready_service(tmp_path)
    answer, bindings = draft(evidence.evidence_id, 2, prefix="😀Ａe\u0301。")
    result = review_draft(service.store, run_id, answer, bindings, now=now)
    proposal = result["citation_preparation"]["proposals"][0]["proposed"]
    assert answer[proposal["start_offset"]:proposal["end_offset"]] == proposal["citation_text"]
    changed = review_draft(service.store, run_id, answer + "！", bindings, now=now)
    assert changed["citation_preparation"]["draft_sha256"] != result["citation_preparation"]["draft_sha256"]


def test_lineage_guidance_distinguishes_absence_error_and_truncation():
    missing = lineage_guidance()
    blocked = lineage_guidance(blocked=True)
    limited = lineage_guidance(truncated=True, failed_count=1, upper_count=2)
    assert "未取得上級審紀錄" in missing["limitations"][0]
    assert "不得解讀為查無" in blocked["limitations"][0]
    assert len(limited["limitations"]) == 2
    for result in [missing, blocked, limited]:
        assert not result["establishes_finality"] and not result["answer_authorized"]
