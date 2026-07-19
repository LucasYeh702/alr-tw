# v0.6 公開版發布審核規程

原則：fail closed。程式 regression、公開邊界、build artifact 或 live dependency 狀態必須分開記錄；外部服務暫時不可用不應被掩飾，也不應直接誤判為程式 regression。

## A. 工作樹與公開邊界

```bash
git status --short --branch
git diff --check
git ls-files | sort
python3 scripts/check_no_forbidden_files.py
python3 scripts/check_public_boundary.py
```

逐筆檢查未追蹤與修改檔。Repo 不得包含 real query／answer／trace、官方全文、SQLite／vector shards、TLR response cache、credential、private endpoint、local sensitive path 或未匿名化案件事實。Official endpoint constants 與合成 fixture 中必要的 URL 例外必須可由程式用途解釋。

## B. 靜態檢查與完整回歸

```bash
uv run ruff check .
uv run mypy src
uv run pytest -q
```

至少覆蓋：20+ v0.6 scenarios、legacy tool regression、caller-attested source rejection、candidate-only blocking、role mismatch、historical-law block、source expiry、privacy downgrade、idempotency、TTL、WAL/SHM/temp purge。

## C. Packaging 與 base-install smoke

```bash
uv build
python -m zipfile -l dist/alr_tw-0.6.0-py3-none-any.whl
```

在新的 virtual environment 安裝 wheel：

- base install 不應強迫安裝 browser 或 live provider dependencies；
- `python -c 'import alr_tw, tw_legal_rag_mcp'` 成功且版本為 `0.6.0`；
- `alr-tw doctor` 在 synthetic default 成功；
- synthetic MCP initialize／tools/list 成功；
- live extra 可安裝，沒有把秘密包進 artifact。

## D. MCP smoke

以 stdio 驗證：

- current protocol `2025-11-25`；
- legacy supported protocol `2024-11-05`；
- unsupported protocol fail closed；
- tools/list 包含六個 v0.6 高階 tools；
- synthetic run 可推進到 ready-for-draft，沒有 evidence 時 final validation blocked 且 answer body 為 null；
- MCP purge 與 CLI purge parity。

可用 MCP Inspector 作額外驗證，但它不是 unit/integration tests 的替代品。

## E. Optional live smoke

只用公開、非個案、無個資的測試詞，分開記錄：

- 一條中央法規；
- 一件憲法裁判；
- 一次普通裁判關鍵字搜尋、正式字號解析 JID 與官方全文下載；
- 一次 TLR health 與安全 query；
- 一次官方 unavailable／WAF-blocked／not-found 分類。

普通裁判 live smoke 直接連線 `judgment.judicial.gov.tw`，不需要 API token；報告不得保存真實敏感搜尋詞或判決全文。

## F. 文件與宣稱

- README 三語、Architecture、Data Policy、Security、TLR、Official Providers、Storage/Purge、Tool Contract、Error Codes、Threat Model 與 Changelog 與程式一致；
- 清楚揭露 `hybrid_verified` 將 privacy-screened query 送到 TLR；
- TLR 明確是 candidate-only，不是 final citation；
- 公開預覽限制、司法院網站依賴、WAF failure 與 purge 限制有揭露；
- 不宣稱完整歷史法規、全域裁判召回、完整審級關係、法律意見或 production readiness。

## G. Git 歷史與發布操作

首次公開、visibility change 或大量 history import 時，另跑全歷史 secret scan（例如 gitleaks）並檢查刪除檔與作者資訊。發布 clone 不得混掛 private history remote；不要使用 `git push --all` 或 `--mirror`。

Tag 前重新執行 A–F，並在 release report 記錄日期、commit、工具版本、tests count、live dependency 狀態、已知限制與任何未執行項目。未經使用者明確要求，不由自動化自行 commit、push、tag 或發布。
