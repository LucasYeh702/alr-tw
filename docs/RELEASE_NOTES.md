# ALR-TW v0.9.1 版本說明

## 安全修正

- Legacy `answer_with_validation()` 將所有 raw citation mappings 視為
  caller-controlled。Caller 自稱 `official`、提供任意 URL／hash／verified time，
  或偽造 `identifier_resolution=hash_match`，均不能取得最終引用或答案呈現資格。
- `support=not_checked` 不再被標成 `source_verified`；legacy metadata helper
  固定回報未檢查 claim support，且不能授權法律答案呈現。
- `SyntheticOfficialAdapter` 保留 Python 相容名稱，但內容改為
  `synthetic`／`demo_only`。Legacy synthetic agentic flow 仍可展示 trace 與
  evidence shape，但 final action 為 `refuse`，answer body 為 `null`。

## 相容性

- 公開 MCP `validate_citation` 原有 caller-attestation fail-closed 行為不變。
- `alr_tw.research.service` 的 server-owned evidence、claim binding 與
  `validate_legal_answer` 路徑不受影響，仍是唯一的法律答案呈現授權邊界。
- Legacy answer-validation schema shape 維持 `v1`；本次只收緊其安全語意。
