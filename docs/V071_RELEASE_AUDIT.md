# ALR-TW v0.7.1 Release Audit

> Archived historical release record. It does not describe the current v0.9.1 capability surface.

Release candidate decision: **ACCEPTED FOR LOCAL v0.7.1 PUBLIC PREVIEW**

本文件記錄 v0.7.1 release candidate 的工程閘門；版本更新內容請見
[RELEASE_NOTES.md](RELEASE_NOTES.md)。本文件只記錄本機工程證據；實際發布
狀態以 `v0.7.1` Git tag 與同名 GitHub Release 為準。

## Candidate identity

- package: `alr-tw 0.7.1`
- branch: `main`
- release branch: `main`
- release identity: `v0.7.1` annotated tag 與同名 GitHub Release 必須指向
  同一 release commit

## Local verification

| Gate | Result |
|---|---|
| Full pytest | **PASS** — 355 tests |
| Ruff | **PASS** |
| mypy | **PASS** — 99 source files |
| `git diff --check` | **PASS** |
| Forbidden-file checker | **PASS** |
| Public-boundary checker | **PASS** |
| Gitleaks working tree | **PASS** |
| Gitleaks reachable `main` history | **REVIEWED** — 1 `generic-api-key` match in an older deterministic output-privacy test fixture; contextual inspection confirms it is synthetic test input, not a credential |
| Python 3.12 fresh-wheel import | **PASS** — both packages report `0.7.1` |
| Fresh-wheel `alr-tw doctor` | **PASS** |
| Fresh-wheel MCP stdio | **PASS** — server `0.7.1`, 23 tools |
| Capability smoke | **PASS** — six profiles; managed fact-state store is false |
| Wheel content scan | **PASS** — 105 entries, no forbidden path／secret pattern |

## External review

AGY CLI 使用 `gemini-3.6-flash-high`、high effort、plan／sandbox 模式進行
只讀外審。第一輪因 untracked 新測試未出現在普通 `git diff`，誤判缺少
測試；本機完整 pytest 已否定該項。另一項 capability limitations 仍殘留
舊民法／跨領域雙重描述則確認成立，已統一為單一 legal-analysis 描述並
加入回歸斷言。

第二輪提供完整 contract、verifier、capabilities 與新測試後，複審結論為
P0、P1、P2 均無。AGY 是外部 sidecar；最終判斷仍以上述本機程式碼、測試
與 artifact 證據為準。

## Fixed release boundary

- `LegalAnalysisEnvelope` 與六種 profiles 只提供 structural and trust
  validation；
- `validate_legal_analysis` 是唯一公開法律分析 validator，支援六個可併用
  分支，不執行 semantic entailment，也不授權 final
  answer；
- managed `ResearchService` 不保存 server-owned fact records；caller fact
  state 不能建立信任；
- TLR 維持 candidate-only，正式證據仍須由 ALR-TW 回查官方來源；
- 本版不是完整台灣法律資料庫、法律意見服務或 production SLA。

## Not established by this audit

- 真實法律問題的實體涵攝正確性；
- production legal-context provider 的資料完整性與時點正確性；
- 系統性 counter-authority search；
- 完整歷史法規版本與全域裁判召回率；
- 外部官方網站或 TLR 的 production SLA。
