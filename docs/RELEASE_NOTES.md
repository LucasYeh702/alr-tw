# ALR-TW v0.9.0 版本說明

## 新增

- 裁判 attribution、主文 disposition、審級／程序 lineage 與歷史法規 provider
  contracts；法條版本與立法資料分離，無法唯一確認時 fail closed。
- optional semantic verifier plugin contract；只回報 supports、contradicts、
  uncertain 或 not_evaluated，不建立 evidence、不改變 source trust、不授權
  finalization。
- 六個 LegalAnalysisEnvelope 分支的 issue-level burden、defense、procedural
  posture 與 refusal constraints；既有民法 element-level schema 維持相容。
- provider conformance 與 receipt-aware adapter；統一處理 official／candidate-only
  source、evidence、scope、retry、privacy 與 snapshot receipt binding。
- optional semantic sidecar registration 與 deployer provider boundary；模型、
  corpus、credentials、private data 與 deployment parameters 不進入公開套件，
  sidecar 不得成為 evidence、trust 或 final-decision owner。
- 補上公開發布用的 repository-scoped secret-scan policy，將 synthetic redaction
  fixture 的例外範圍限制在單一測試檔案。
