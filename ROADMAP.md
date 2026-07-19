# Roadmap

## 已完成

- `v0.1`：synthetic data、source trust policy、citation validation、CI guards。
- `v0.2`：deterministic execution graph、MCP stdio、trace、validation report。
- `v0.3`：claim grounding、role-aware semantic checks、fail-closed scenarios。
- `v0.4`：opt-in identifier-backed judgment cache resolver 與 hash verification。
- `v0.5`：externally driven MCP traces、agent client guide、release hardening。
- `v0.6`：server-owned research service、統一短期 SQLite、官方法規／普通裁判／憲法 provider、clean-room TLR candidate recall、MCP tools、purge 與 public-preview release audit。

## v0.6 公開預覽限制

- 完整指定日期法規版本尚未提供；
- 普通裁判不承諾全域召回率，完整審級圖尚未提供；
- 程序裁定、附件與 OCR 依官方頁面可取得程度處理；
- 普通裁判全文 live lookup 直接使用司法院裁判書查詢與全文頁，不需要 Judicial Yuan API token；
- 沒有內建 LLM、法律答案生成器或 production corpus。

## 後續候選

- time-law release 與 amendment lineage；
- 本地官方裁判 catalog／tombstone governance；
- 行政函釋、地方自治法規與命令的 provider contracts；
- citation graph、審級關係與裁判效力 metadata；
- privacy-preserving local recall 與可評測的 Taiwan legal reranker；
- enterprise RBAC、audit trail 與 deployment policy packs。

後續功能不得改變 `candidate != evidence`、官方移除要同步治理、角色不可混用與 blocked 不洩漏草稿等核心 invariant。
