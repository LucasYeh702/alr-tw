from tw_legal_rag_mcp.mcp_server.schemas import ToolEnvelope, ToolError


def test_tool_error_envelope_has_stable_machine_readable_shape():
    payload = ToolEnvelope(
        ok=False,
        error=ToolError(
            code="citation_unverifiable",
            message="Citation cannot be used as a final source.",
            retryable=False,
            details={"citation_id": "tlr-candidate-demo-001"},
        ),
    ).model_dump()

    assert payload == {
        "ok": False,
        "data": None,
        "error": {
            "code": "citation_unverifiable",
            "message": "Citation cannot be used as a final source.",
            "retryable": False,
            "details": {"citation_id": "tlr-candidate-demo-001"},
        },
    }
