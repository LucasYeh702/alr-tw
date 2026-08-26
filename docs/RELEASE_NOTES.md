# ALR-TW v0.10.1 版本說明

## 修正

- 將「是否找到已驗證反面裁判」與「搜尋涵蓋是否完整」拆成獨立狀態；
  已驗證的 `opposing` relation receipt 現可完成 counter-authority obligation，
  即使查證預算截斷仍保留 `coverage=partial`。
- 外部 reasoning owner 可對同一 run 的已驗證裁判提出 `supporting`、
  `opposing`、`distinguishing`、`unrelated` 或 `uncertain` 關係分析；ALR-TW
  會驗證 source、evidence、資格、期限與 hash 後保存不可變 receipt。
- `unrelated` 裁判不再被誤判為反面裁判；不存在、過期、不合格或跨來源的
  evidence 會 fail closed，且不產生 relation receipt。
- Finalization 現分別消費 counter-authority obligation 狀態與 bounded coverage，
  不再因「找到任何已驗證裁判」本身固定降為 partial／refusal-only；全國一致或
  不存在反面見解的主張仍要求完整且有界的搜尋涵蓋。

## 保留的安全邊界

- 本版仍是 public preview，不提供完整台灣法律資料庫、語義蘊含判斷或
  production SLA。
- `ResearchService.validate_legal_answer` 仍只接受 server-owned source／evidence
  與同一 research run 的 claim binding；bounded scoped miss 不能推論全國不存在
  反面見解或實務一致。
