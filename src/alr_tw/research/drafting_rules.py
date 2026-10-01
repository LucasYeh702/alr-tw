"""Server-controlled drafting instructions; no source text or authority effects."""

from typing import Any

RULE_VERSION = "alr-tw.drafting-rules/v2"
RULES = {
    "whole_clause": "每個實質子句（包括短結論）須由一項主張綁定完整涵蓋，不可用零碎文字拼湊覆蓋。",
    "verified_annotation": "僅通過來源、精確位置與主張關聯核對的純引用標記可排除；括號內的法律結論仍須綁定驗證。",
    "same_run": "使用同次研究的 evidence_ids 與正式引用文字；完整綁定仍須通過支持、角色、時點及最終驗證。",
    "offsets": "引用位置使用原始 answer_text 的 Unicode 碼點，零起算、結尾不包含；改稿後重新定位並使用新的操作編號。",
    "citation_label": "citation_text 必須是對應來源的 source.citation 正式引用名稱（裁判可用已核對的同文書等價名稱），不是 evidence.exact_text 條文或裁判原文；答案沒有引用標記時可省略 citation_occurrences，仍須完整 claim_bindings。",
    "same_clause": "引用與主張放在同一子句；或完整主張後立即接單一純引導引用句（參見／參照／見／依），不得跨段、夾帶結論或有歧義。",
}
BINDING_DESCRIPTION = "Bind evidence IDs from the same research run. " + " ".join(RULES.values())


def drafting_guidance(*, full: bool = True) -> dict[str, Any]:
    result: dict[str, Any] = {"rule_version": RULE_VERSION, "answer_authorized": False}
    if full:
        result["rules"] = dict(RULES)
    else:
        result["next_step"] = "完整規則見 get_legal_research_capabilities；預檢後仍須嚴格驗證。"
    return result


def lineage_guidance(*, blocked: bool = False, truncated: bool = False,
                     failed_count: int = 0, upper_count: int = 0) -> dict[str, Any]:
    conditions = []
    if blocked:
        conditions.append("來源或研究前置條件未滿足；請查看 reason_codes，不得解讀為查無。")
    if truncated:
        conditions.append("檢查因節點預算截斷，未檢查部分仍屬未知。")
    if failed_count:
        conditions.append("部分相關裁判官方驗證失敗，不能當作不存在。")
    if not blocked and not upper_count:
        conditions.append("本次來源與檢索範圍內未取得上級審紀錄，不能據此判斷裁判是否確定。")
    return {"answer_authorized": False, "establishes_finality": False,
            "limitations": conditions,
            "next_step": "依來源、檢索範圍及錯誤說明限制；有上級審紀錄也不等於已證明裁判確定。"}
