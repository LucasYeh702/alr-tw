from tw_legal_rag_mcp.legal_nlp.privacy import external_recall_safety_gate, mask_sensitive_text


def test_masks_email_phone_taiwan_id_and_address_phrase():
    synthetic_id = "A" + "123456789"
    text = f"王小明 {synthetic_id} email a@example.com 電話 0912-345-678 地址 台北市中正區重慶南路1段"

    masked = mask_sensitive_text(text, mask_names=True)

    assert "a@example.com" not in masked
    assert "0912-345-678" not in masked
    assert synthetic_id not in masked
    assert "台北市中正區重慶南路1段" not in masked
    assert "[EMAIL]" in masked
    assert "[PHONE]" in masked
    assert "[TW_ID]" in masked
    assert "[ADDRESS]" in masked


def test_external_recall_gate_blocks_sensitive_query():
    synthetic_id = "A" + "123456789"
    result = external_recall_safety_gate(f"請查 {synthetic_id} 在租賃押金案件的判決")

    assert result["allowed"] is False
    assert "[TW_ID]" in result["masked_query"]
    assert "[TW_ID]" in result["sensitive_markers"]


def test_external_recall_gate_allows_non_sensitive_query():
    result = external_recall_safety_gate("請查民法第184條侵權行為相關裁判")

    assert result["allowed"] is True
    assert result["sensitive_markers"] == []
