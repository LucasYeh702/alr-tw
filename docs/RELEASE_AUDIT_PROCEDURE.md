# v0.12.0 公開版發布審核規程

原則：fail closed。程式 regression、公開邊界、build artifact 或 live dependency 狀態必須分開記錄；外部服務暫時不可用不應被掩飾，也不應直接誤判為程式 regression。

## 0. 私人審核暫存區

Release candidate 可以先放在與公開來源庫分離、長期維持 private 的獨立審核
repository；它不得建立成公開來源庫的 GitHub fork。
每個私人候選記錄當時的公開基線；私人 `main` 可以包含已整合的審核結果，但不得
當作公開發布的 ancestry。每個候選以
`review/vX.Y.Z-rc.N` 分支、private pull request 與 `vX.Y.Z-rc.N` tag 審核。

私人可見性只提供存取控制，不改變資料邊界：不得放入 credentials、production
corpus、真實使用者 query／answer／trace、未匿名化案件事實、local cache 或私有部署
參數。審核者可能 clone 並保留副本，因此不能把 private repository 當成秘密保管庫。
相同限制也適用於 private PR／Issue 留言、附件、review、Actions log 與 artifact；不得
貼入真實案例重現、終端輸出或 runner 環境內容。

推送前須把私人 repository 設為 staging clone 唯一的 push remote，並只推送逐一指名
且已掃描的 commit／branch／tag；不得使用 `git push --all`、`--mirror` 或裸
`--tags`。另須檢查精確 changed-path allowlist、候選 commit range 與 annotated tag
object、commit／tag message、submodule、Git LFS、git notes 及 replace refs。Commit 與
tagger 使用公開 no-reply 身分，訊息不得包含私有案例、路徑或內部識別碼。

通過審核後，從公開 `main` 建立乾淨工作樹，只匯入 allowlisted、已清理的最終
snapshot／patch，並重新執行本規程 A–G。不得把私人 repository 改為 public，亦不得
把其完整 history、private PR／Issue、Actions log 或 RC tag mirror 到公開 repository。
公開版使用新的正式 commit 與 tag；私人審核 findings 只有在移除私有輸入與識別資訊
後，才可摘要進公開文件。

## A. 工作樹與公開邊界

```bash
git status --short --branch
git diff --check
git ls-files | sort
python3 scripts/check_no_forbidden_files.py
python3 scripts/check_public_boundary.py
```

逐筆檢查未追蹤與修改檔。Repo 不得包含 real query／answer／trace、官方全文、SQLite／vector shards、TLR response cache、credential、private endpoint、local sensitive path 或未匿名化案件事實。Official endpoint constants 與合成 fixture 中必要的 URL 例外必須可由程式用途解釋。
兩支 checker 是互補檢查，不能互相取代；發布必須同時執行，也須對解包後的
wheel 與 sdist 執行。sdist 必須以套件根目錄計算禁止路徑，不得被外層目錄遮蔽。

## B. 靜態檢查與完整回歸

```bash
uv run ruff check .
uv run mypy src
uv run pytest -q
```

至少覆蓋：v0.12.0 六種 domain profiles、complete／issue-limited scope、
server-owned analysis references、legacy tool regression、caller-attested
source rejection、candidate-only blocking、role mismatch、historical-law
block、source expiry、privacy downgrade、idempotency、TTL、WAL/SHM/temp purge，
以及 quick prompt routing、1–5 件 verification budget、verified-subset
qualification、autonomous retry stop、conformance CLI 與 ChronoLex gold isolation。
另須明示執行 `tests/integration/test_v012_release_gates.py` 與
`tests/unit/test_v012_snapshot_receipts.py`：Lane A 記錄攻擊分類與 false-refuse
numerator／denominator，Lane B 驗證內建同 run receipt 的簽發、持久化、重算、
forgery/mismatch fail-closed 與 purge cascade，Lane C 記錄 verified-profile 通過／
拒絕雙路徑的實際耗時、blocker message 與 safe next actions。

## C. Packaging 與 base-install smoke

```bash
VERSION=0.12.0
uv build
python scripts/check_release_artifacts.py --version "$VERSION" dist/*.whl dist/*.tar.gz
python -m zipfile -l "dist/alr_tw-${VERSION}-py3-none-any.whl"
```

正式 release 授權前，`pyproject.toml`、`src/alr_tw/_version.py`、MCP
`initialize` 回報與測試中的 package identity 必須同步到同一個 release target；
在同步完成前，工作樹只能視為未發布狀態，不能建立正式 tag 或宣稱已發布。

在新的 virtual environment 安裝 wheel：

- base install 不應強迫安裝 browser 或 live provider dependencies；
- `python -c 'import alr_tw, tw_legal_rag_mcp'` 成功且版本與 `VERSION` 一致；
- `alr-tw doctor` 在 synthetic default 成功；
- synthetic MCP initialize／tools/list 成功；
- live extra 可安裝，沒有把秘密包進 artifact。

## D. MCP smoke

以 stdio 驗證：

- current protocol `2025-11-25`；
- legacy supported protocol `2024-11-05`；
- unsupported protocol fail closed；
- tools/list 包含 v0.12.0 server-managed 與 interoperability MCP tools；
- capabilities 與 tools/list 包含 `alr-tw.legal-analysis/v1`、六種 profiles
  與 `validate_legal_analysis`；
- synthetic run 可推進到 ready-for-draft，沒有 evidence 時 final validation blocked 且 answer body 為 null；
- `/quick` 與 `快速模式：` 都選到 quick plan；`execute_legal_research` 一次完成
  synthetic obligations、回 elapsed telemetry，且 final-answer validation 維持 pending；
- MCP purge 與 CLI purge parity。

可用 MCP Inspector 作額外驗證，但它不是 unit/integration tests 的替代品。

## E. Optional live smoke

只用公開、非個案、無個資的測試詞，分開記錄：

- 一條中央法規；
- 一件憲法裁判；
- 一次普通裁判關鍵字搜尋、正式字號解析 JID 與官方全文下載；
- 一次 TLR health 與安全 query；
- 以 release-scope 的通用契約法 fixture 測一次 quick single-roundtrip，記錄候選數、
  官方驗證數、truncation、finalization posture 與 elapsed time，不保存全文；
- 一次官方 unavailable／WAF-blocked／not-found 分類。

普通裁判 live smoke 直接連線 `judgment.judicial.gov.tw`，不需要 API token；報告不得保存真實敏感搜尋詞或判決全文。

## F. 文件與宣稱

- README 三語、Architecture、Data Policy、Security、TLR、Official Providers、Storage/Purge、Tool Contract、Error Codes、Threat Model 與 Changelog 與程式一致；
- 清楚揭露 `hybrid_verified` 將 privacy-screened query 送到 TLR；
- TLR 明確是 candidate-only，不是 final citation；
- 公開預覽限制、司法院網站依賴、WAF failure 與 purge 限制有揭露；
- 不宣稱完整歷史法規、全域裁判召回、完整審級關係、法律意見或 production readiness。
- 明示 `ready_for_draft` 只代表 workflow completion，並檢查 sufficiency、Coverage v2、
  finalization、structured refusal 與 snapshot receipt 不被 caller 偽造。

## G. Git 歷史與發布操作

首次公開、visibility change 或大量 history import 時，另跑全歷史 secret scan（例如 gitleaks）並檢查刪除檔與作者資訊。發布 clone 不得混掛 private history remote；不要使用 `git push --all` 或 `--mirror`。

公開 remote 不得存在 `v*-rc*` tag；private-only policy／governance／review artifact path 必須由公開
邊界 checker 拒絕。正式 public commit 必須直接以當時的 public `main` 為 parent，且
不得與 private RC commit 共用 SHA。

Tag 前重新執行 A–F，並在
[V0120_RELEASE_GATE_RESULTS.md](V0120_RELEASE_GATE_RESULTS.md) 記錄日期、commit、
工具版本、tests count、Lane A–C、live dependency 狀態、已知限制與任何未執行項目。
本機凍結後的 commit、tree、allowlist 與套件 SHA-256 另存於未追蹤的發布交接封包；
公開 PR 合併後，須核對實際 merge commit 的 tree 並重跑 CI，再建立正式 tag。
「閘門通過但結論仍可能錯」必須留在限制欄，不得改寫為測試通過或失敗。未經
使用者明確要求，不由自動化自行 commit、push、tag 或發布。
