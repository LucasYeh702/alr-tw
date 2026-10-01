import json

from test_v012_release_gates import _mcp_session, _LAW_TEXTS
from alr_tw.workflow_cli import call_tool
from alr_tw.cli import main
import alr_tw.workflow_cli as workflow_cli


def test_research_explore_and_complete_via_cli(tmp_path, monkeypatch, capsys):
    session = _mcp_session(tmp_path)
    monkeypatch.setattr(workflow_cli, "McpSession", lambda **kwargs: session)
    execution = call_tool(
        session,
        "execute_legal_research",
        {
            "query": "示範責任法第7條",
            "constraints": {"research_depth": "quick"},
        },
    )
    run_id = execution["run_id"]
    evidence_id = execution["evidence_bundle"]["items"][0]["evidence"][0]["evidence_id"]
    path = tmp_path / "draft.json"
    path.write_text(
        json.dumps(
            {
                "answer_text": _LAW_TEXTS["7"],
                "claim_bindings": [
                    {
                        "claim_id": "claim-7",
                        "claim_text": _LAW_TEXTS["7"],
                        "claim_type": "law_rule",
                        "evidence_ids": [evidence_id],
                    }
                ],
            }
        )
    )
    assert main(["review-draft", "--run", run_id, "--input", str(path)]) == 0
    workspace = json.loads(capsys.readouterr().out)["data"]
    assert workspace["draft_text"] == _LAW_TEXTS["7"]
    assert not workspace["safe_to_present"]
    assert (
        main(
            [
                "complete-research",
                "--run",
                run_id,
                "--input",
                str(path),
                "--operation-id",
                "complete-positive",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)["data"]
    assert result["validation"]["decision"] == "validated"
    assert result["validation"]["answer_text"] == _LAW_TEXTS["7"]
    assert result["safe_to_present"]
    path.write_text(json.dumps({"answer_text": "不受支持的合成推論。", "claim_bindings": []}))
    assert (
        main(
            [
                "complete-research",
                "--run",
                run_id,
                "--input",
                str(path),
                "--operation-id",
                "complete-negative",
            ]
        )
        == 1
    )
    blocked = json.loads(capsys.readouterr().out)["data"]
    assert not blocked["safe_to_present"] and blocked["validation"]["answer_text"] is None


def test_corrected_draft_can_pass_after_block_without_rewriting_old_decision(tmp_path):
    session = _mcp_session(tmp_path)
    execution = call_tool(
        session,
        "execute_legal_research",
        {
            "query": "示範責任法第7條",
            "constraints": {"research_depth": "quick"},
        },
    )
    run_id = execution["run_id"]
    evidence_id = execution["evidence_bundle"]["items"][0]["evidence"][0]["evidence_id"]
    rejected = call_tool(
        session,
        "complete_legal_research",
        {
            "run_id": run_id,
            "operation_id": "bad-draft",
            "answer_text": "不受支持的推論。",
            "claim_bindings": [],
        },
    )
    assert rejected["validation"]["decision"] == "blocked"
    corrected = call_tool(
        session,
        "complete_legal_research",
        {
            "run_id": run_id,
            "operation_id": "corrected-draft",
            "answer_text": _LAW_TEXTS["7"],
            "claim_bindings": [
                {
                    "claim_id": "corrected",
                    "claim_type": "law_rule",
                    "claim_text": _LAW_TEXTS["7"],
                    "evidence_ids": [evidence_id],
                }
            ],
        },
    )
    assert corrected["validation"]["decision"] == "validated"
    assert (
        session.research_service().store.get_operation(run_id, "bad-draft")
        == rejected["validation"]
    )
