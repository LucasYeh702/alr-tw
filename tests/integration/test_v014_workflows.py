"""Exercise discovery, research, preflight, correction and strict refusal via MCP."""
from copy import deepcopy

from alr_tw.research.drafting_rules import RULES, RULE_VERSION
from alr_tw.workflow_cli import call_tool
from test_v012_release_gates import _mcp_session


def test_mcp_guided_research_repair_and_refusal(tmp_path):
    session = _mcp_session(tmp_path)
    listed = session.handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    for tool in listed["result"]["tools"]:
        if tool["name"] in {"validate_legal_answer", "complete_legal_research"}:
            assert all(rule in tool["inputSchema"]["properties"]["claim_bindings"]["description"]
                       for rule in RULES.values())
    capabilities = call_tool(session, "get_legal_research_capabilities", {})
    assert capabilities["workflow_guidance"]["drafting"]["rule_version"] == RULE_VERSION
    result = call_tool(session, "execute_legal_research", {
        "query": "示範責任法第7條", "constraints": {"research_depth": "quick"},
    })
    assert result["workflow_guidance"]["drafting"]["rules"] == RULES
    evidence = result["evidence_bundle"]["items"][0]["evidence"][0]
    claim = "行為人違反示範義務時，應負合成測試責任"
    citation = "示範責任法第7條"
    answer = claim + "（" + citation + "）。"
    payload = {"run_id": result["run_id"], "answer_text": answer, "claim_bindings": [{
        "claim_id": "claim", "claim_text": claim, "claim_type": "law_rule",
        "evidence_ids": [evidence["evidence_id"]],
        "citation_occurrences": [{"evidence_id": evidence["evidence_id"],
            "citation_text": citation, "start_offset": answer.index(citation) + 1,
            "end_offset": answer.index(citation) + len(citation) + 1}],
    }]}
    preview = call_tool(session, "review_legal_draft", payload)
    assert not preview["safe_to_present"]
    assert "CITATION_OCCURRENCE_TEXT_MISMATCH" in preview["blockers"]
    payload["claim_bindings"][0]["citation_occurrences"] = [
        preview["citation_preparation"]["proposals"][0]["proposed"]]
    corrected = call_tool(session, "review_legal_draft", payload)
    assert corrected["unbound_claim_count"] == 0
    assert not corrected["blockers"] and not corrected["safe_to_present"]
    valid = call_tool(session, "complete_legal_research", {**payload, "operation_id": "corrected"})
    assert valid["safe_to_present"]
    assert valid["validation"]["answer_text"] == answer
    bad = deepcopy(payload)
    bad["answer_text"] += "無罪。"
    rejected = call_tool(session, "validate_legal_answer", {**bad, "operation_id": "tail"})
    assert not rejected["safe_to_present"] and rejected["answer_text"] is None
    # Editing input must not silently replay the old successful operation.
    import pytest
    with pytest.raises(ValueError, match="OPERATION_REQUEST_MISMATCH"):
        call_tool(session, "complete_legal_research", {**bad, "operation_id": "corrected"})
