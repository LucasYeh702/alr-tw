# ALR-TW：台灣法律 Agentic RAG / MCP Harness

繁體中文 | [English](README.en.md)

ALR-TW v0.6.0 是台灣法律研究安全 harness 的公開預覽版。外部 agent／LLM 可透過 MCP 建立研究 run；來源取得、研究義務、證據升格、答案驗證與清除則由 server 掌控。架構採台灣大陸法系角度：現行法規與法律時點優先，普通裁判依審級及段落角色處理，憲法法庭多數理由、協同意見與不同意見分離。

本專案已整合並在 `hybrid_verified` 模式使用 [TLR（Taiwan Legal RAG）](https://github.com/aa0101181514/tw-legal-rag)尋找普通裁判候選，再由 ALR-TW 回查司法院官方全文；TLR 結果本身不是正式引用證據。

本專案不是法律意見服務，也不是完整法律資料庫。

本 repo 不包含 LLM，也不包含 agent 實作。規劃、工具選擇與自然語言推理由外部呼叫端提供；ALR-TW 只負責可稽核工具與確定性閘門。Repo 內的示範 ranking 參數僅供測試，不是 production ranking 設定。

## v0.6.0 的安全模型

```text
外部 agent 提問／起草
  -> server-owned research obligations
  -> official providers + optional TLR candidate recall
  -> server-owned evidence snapshots
  -> claim / role / time / privacy / citation validation
  -> validated | qualified | blocked
```

- 呼叫端宣告 `official` 不會自動取得正式引用資格；
- TLR 只提供 `external_semantic_recall` 候選，必須回官方來源驗證；
- 當事人主張、案件事實、協同／不同意見不能冒充法院多數見解；
- 歷史時點、來源到期、角色或主張支持無法確認時 fail closed；
- `blocked` 不回傳 answer body。

## 三種資料模式

| 模式 | 行為 |
|---|---|
| `synthetic` | 預設、完全離線，供 demo 與 CI |
| `official_only` | 只連官方法規、普通裁判與憲法法庭來源 |
| `hybrid_verified` | privacy gate 通過後送 TLR 找候選，再回官方驗證 |

啟用 `hybrid_verified` 時，查詢文字可能傳送至 TLR。不得輸入個人秘密、未公開個案事實、私有契約、訴訟策略、證據弱點或談判底線。詳見 [TLR Provider](docs/TLR_PROVIDER.md)。

## 安裝與設定

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[all]'

alr-tw doctor
```

真實官方模式：

```bash
export ALR_TW_DATA_MODE=official_only
export ALR_TW_RETENTION=24h
alr-tw doctor --live
```

普通裁判不需要司法院 API token。啟用 live mode 後，搜尋詞與篩選條件會直接送到司法院裁判書查詢網站；不得以未公開案情、個人秘密或受保密義務保護的資料作為搜尋詞。也不要把 TLR API key 或真實查詢寫入 repo。

## v0.6 MCP tools

| Tool | 用途 |
|---|---|
| `research_legal_question` | 建立研究 run，不生成答案 |
| `continue_legal_research` | 以 idempotent `operation_id` 執行一個下一步 |
| `get_legal_research_state` | 唯讀讀取 run 狀態 |
| `lookup_legal_source` | 精確查詢法規、憲法字號、JID／正式裁判字號 |
| `validate_legal_answer` | 只用該 run 的 server-owned evidence 驗證草稿 |
| `purge_research_storage` | 清除單一 run 或全部 managed storage |

舊版 synthetic／trace tools 暫時保留相容性。新整合應使用上述 server-owned research flow。

支援 MCP protocol `2025-11-25`、`2025-06-18`、`2025-03-26`、`2024-11-05`。

## 官方 providers

- 法務部法規：官方結構化資料優先，官方網頁作一致性檢查；
- 司法院普通裁判：解析官方搜尋頁取得 JID，再直接由官方 `data.aspx` 取得並解析全文；
- 憲法法庭：判決、實體裁定、舊制解釋及可取得的個別意見。

第一版不承諾完整歷史法規版本、普通裁判全域召回率、所有程序裁定或完整審級關係。詳見 [Official Providers](docs/OFFICIAL_PROVIDERS.md)。

## Final decision

- `validated`：來源、角色、時點與 claim support 通過；
- `qualified`：草稿有已驗證證據，但召回覆蓋有明示限制；
- `blocked`：不可展示草稿，只回 blockers。

精確查到來源不等於答案已驗證。Final answer 仍必須通過 `validate_legal_answer`。

## Retention 與 purge

預設 managed SQLite 位於 `~/.cache/alr-tw`，保存 `24h`，上限 `7d`。單次 run 可設定 `retention: "ephemeral"`，在 final validation 後同步刪除。

```bash
alr-tw purge --run RUN_ID --confirm
alr-tw purge --all --confirm
```

清除本機資料不能撤回已傳送給外部服務的查詢或伺服器日誌。詳見 [Storage and Purge](docs/STORAGE_AND_PURGE.md)。

## 驗證

```bash
uv run ruff check .
uv run mypy src
uv run pytest -q
python3 scripts/check_no_forbidden_files.py
python3 scripts/check_public_boundary.py
uv build
```

## 重要文件

- [架構](ARCHITECTURE.md)
- [資料政策](DATA_POLICY.md)
- [安全說明](SECURITY.md)
- [信任模型](docs/TRUST_MODEL.md)
- [工具契約](docs/TOOL_CONTRACT.md)
- [TLR Provider](docs/TLR_PROVIDER.md)
- [官方 Providers](docs/OFFICIAL_PROVIDERS.md)
- [Storage and Purge](docs/STORAGE_AND_PURGE.md)
- [v0.6.0 實際發行稽核](docs/V060_RELEASE_AUDIT.md)
- [Changelog](CHANGELOG.md)

## 法律聲明

本專案僅供軟體架構、研究與測試，不構成法律意見、律師服務或任何個案結論，也不保證法律資料完整、正確、即時或適用。
