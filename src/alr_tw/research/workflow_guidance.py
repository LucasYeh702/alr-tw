"""Traditional Chinese progress guidance; never an answer authorization.

Adapted from the isolated AGY implementation proposal. Only fixed descriptions
and verified counts are projected; draft text, URLs and raw messages stay out.
"""

from __future__ import annotations

from typing import Any

from .drafting_rules import drafting_guidance


_REMEDIES = {
    "CLAIM_SUPPORT_UNCHECKED": (
        "主張尚未連結到可檢查的證據段落。",
        "核對同次研究的段落編號及來源角色，補足綁定後重新驗證。",
    ),
    "CLAIM_CITATION_BINDING_REQUIRED": (
        "核心主張尚未綁定證據段落。",
        "為每項核心主張填入同次研究的 evidence_ids，再驗證草稿。",
    ),
    "CLAIM_ROLE_ERROR": (
        "引用段落的角色不符合主張，例如將當事人主張當作法院見解。",
        "核對段落角色，選取法院自身理由或修正主張的歸屬。",
    ),
    "CLAIM_CONTRADICTED": (
        "主張與綁定段落存在規則可辨識的相反內容。",
        "閱讀官方原文，修正主張或引用後重新驗證。",
    ),
    "CLAIM_SUPPORT_NEEDS_REVIEW": (
        "段落支持不足或存在尚待釐清的證據衝突。",
        "比較綁定段落的適用範圍與角色；補足證據或交由人工複核。",
    ),
    "CLAIM_UNSUPPORTED": (
        "綁定段落尚不足以支持主張。",
        "縮小主張範圍或查找直接相關的官方段落，再重新驗證。",
    ),
    "CLAIM_OVERSTATED": (
        "主張省略限制條件或超出證據範圍。",
        "保留原文例外、條件及個案範圍，修正後重新驗證。",
    ),
    "OFFICIAL_TLS_VERIFICATION_FAILED": (
        "官方來源的安全連線驗證失敗，不能解讀為查無資料。",
        "執行 alr-tw doctor --live 檢查官方連線，再重試。",
    ),
    "OPERATION_FAILED": (
        "先前操作因例外失敗，不能重播為成功。",
        "讀取目前進度並排除原因，再用新的操作編號繼續；不沿用失敗操作的答案。",
    ),
    "OPERATION_RESULT_STALE": (
        "先前驗證結果的授權條件已改變。",
        "重新核對來源及保存期限，用新的操作編號驗證草稿。",
    ),
    "OPERATION_REQUEST_MISMATCH": (
        "操作編號已綁定不同請求，或舊紀錄缺少請求摘要。",
        "確認操作種類與草稿內容；修改後使用新的操作編號，不能沿用舊驗證結果。",
    ),
    "OPERATION_IN_PROGRESS": (
        "同次研究仍有未完成操作，尚不能安全重播或重疊執行。",
        "等待活躍程序完成；新版程序中斷後使用新操作編號繼續。舊版未受管理紀錄仍需重新建立研究。",
    ),
    "STORAGE_PATH_UNSAFE": (
        "研究儲存位置的檔案型別或擁有者不符合安全要求。",
        "使用本人擁有的獨立目錄，移除設定中的符號連結；不要修改連結目標的權限。",
    ),
    "STORAGE_PATH_CHANGED": (
        "研究儲存目錄或資料庫已被替換。",
        "停止使用此研究狀態，確認目錄來源後重新啟動；不要覆寫替代目標。",
    ),
    "RESEARCH_RUN_EXPIRED": (
        "研究保存期限已到，舊驗證紀錄不能繼續使用。",
        "重新建立研究，保留原問題要求的法律適用日期並重新查證。",
    ),
}


def _guidance(scenario: str, headline: str, count: int | None,
              missing: list[str], actions: list[str]) -> dict[str, Any]:
    return {
        "schema_version": "alr-tw.workflow-guidance/v1",
        "scenario": scenario,
        "drafting": drafting_guidance(full=False),
        "headline": headline,
        "verified_source_count": count,
        "missing_items": list(dict.fromkeys(missing)),
        "next_steps": list(dict.fromkeys(actions)),
        # Guidance itself never carries or authorizes the legal answer.
        "answer_authorized": False,
    }


def build_research_guidance(brief: dict[str, Any], *, depth: str) -> dict[str, Any]:
    count = brief.get("verified_source_count")
    if type(count) is not int or count < 0:
        count = None
    status = brief.get("status")
    if status == "in_progress":
        return _guidance("in_progress", "研究尚在進行", count,
                         ["部分研究步驟尚未完成，尚不能呈現法律答案。"],
                         ["讀取研究進度，依待辦步驟繼續研究；遇到外部查詢失敗先排除原因。"])
    if status == "blocked" or brief.get("answer_mode") == "refusal_only":
        if count == 0:
            return _guidance("no_verified_material", "本次尚未取得可用的已驗證材料", 0,
                             ["有限範圍內未取得材料，不代表相關法源不存在。"],
                             ["檢查阻擋原因；確認法規條號、正式案號或調整搜尋詞後重新研究。"])
        return _guidance("research_blocked", "研究仍有未排除的限制", count,
                         ["尚未滿足本次研究的起草條件；材料數量請依研究簡報確認。"],
                         ["依研究簡報的阻擋原因與補救步驟補資料，必要時交由人工處理。"])
    if status == "ready_for_draft":
        return _guidance("bounded_material_ready" if depth == "quick" else "material_ready",
                         "已完成本次材料查證流程，草稿仍須驗證", count,
                         ["尚未驗證草稿；快速查詢也不證明全域召回、裁判確定或實務一致。"],
                         ["使用同次研究的證據段落起草，為核心主張建立證據綁定後驗證。",
                          "需要更廣的類案或反面見解時，另行擴大研究範圍。"])
    return _guidance("unknown", "研究狀態尚待確認", count,
                     ["目前資訊不足以判斷下一階段是否可執行。"],
                     ["重新讀取研究狀態；保存期限已到時建立新研究。"])


def build_validation_guidance(result: dict[str, Any]) -> dict[str, Any]:
    decision = result.get("decision")
    if result.get("safe_to_present") is True and decision in {"validated", "qualified"}:
        qualified = decision == "qualified"
        return _guidance(str(decision), "草稿通過既定驗證，須併附限制" if qualified
                         else "草稿通過既定驗證", None,
                         ["未執行完整法律語義或個案涵攝正確性判斷。"],
                         ["只使用驗證回應中的答案與引用，完整呈現附帶限制，並依個案複核。"])
    raw_codes = result.get("blockers", [])
    if not isinstance(raw_codes, list):
        raw_codes = []
    codes = [code for code in raw_codes if isinstance(code, str)]
    remedies = [_REMEDIES[code] for code in codes if code in _REMEDIES]
    return _guidance("draft_blocked", "草稿尚未通過驗證", None,
                     [item[0] for item in remedies] or ["本次研究或草稿仍有未滿足的驗證條件。"],
                     [item[1] for item in remedies] or
                     ["查看研究簡報及驗證原因，補足材料或修正草稿後重新驗證。"])


def build_error_guidance(code: str) -> dict[str, Any]:
    missing, action = _REMEDIES.get(code, (
        "本次操作未完成。", "檢查輸入格式與研究狀態，再依錯誤代碼處理。",
    ))
    return _guidance("operation_failed", "操作尚未完成", None, [missing], [action])
