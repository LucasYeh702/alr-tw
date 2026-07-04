# 公開版發布審核規程（Release Audit Procedure）

本規程定義 ALR-TW 公開 repo 在發布、變更可見性或合併資料相關變更前，必須執行的完整審核步驟。它擴充 `SECURITY.md` 的 Release Checks 與 `docs/AGENTIC_HARNESS_ACCEPTANCE.md` 的 release evidence，把散落的檢查整合成一份可重複執行、可留紀錄的規程。

原則：**fail closed**。任何一步無法確認，就延後發布；寧可不發布，不可帶疑慮發布。

## 適用時機

必須完整執行：

- 建立 release tag 前
- 變更 repository visibility 前（例如 private 轉 public）
- 匯入大量變更或歷史（squash、subtree、大型 rebase）後
- 接受任何涉及 fixture、demo data、examples 的外部 PR 前

建議執行（可只跑 A、C、D）：

- 每次合併回 main 後

## A. 工作樹審核

```bash
git status --short --branch
git ls-files | sort
python3 scripts/check_no_forbidden_files.py
python3 scripts/check_public_boundary.py
uv run --extra dev ruff check .
uv run --extra dev pytest
uv run --extra dev alr-tw-demo
uv run --extra dev python examples/agentic_mcp_client_demo.py
```

檢核點：

- `git status` 乾淨：無未預期的 modified 或 untracked 檔案。`ASK_YOUR_AI_AGENT_FULL_RAG.zh-TW.md` 依規格維持 untracked 且 excluded，除非另行明確核准。
- `git ls-files` 逐行掃過一遍：不應出現資料庫、壓縮包、log、cache、非預期的大檔或非 UTF-8 檔。
- 兩支守門腳本與全部測試通過。

## B. Git 歷史審核

工作樹乾淨不代表歷史安全。以下每項都要看：

```bash
# 曾被刪除的檔案（刪掉不等於離開歷史）
git log --all --diff-filter=D --name-only --pretty=format: | sort -u

# 作者身分：不得出現個人機器主機名、內網網域或非預期信箱
git log --all --format='%an %ae' | sort -u

# 歷史內容掃描（首次公開或 visibility change 時必跑全歷史）
gitleaks detect --source . --log-opts="--all"
```

檢核點：

- 曾刪除檔案清單中不得有任何真實資料、私有模組或憑證類檔名；若有，該歷史**不得發布**，需以全新乾淨歷史重建（本 repo 即以獨立首發 commit 建立，與任何私有開發歷史無共同祖先——維持這個做法）。
- 作者信箱只允許 GitHub noreply 或已核准的公開信箱。
- gitleaks（或等效工具）無真實命中；對守門腳本自身 pattern 定義的誤報要逐筆確認為誤報。

## C. Fixture 合成性審核

「synthetic only」是本 repo 的核心保證，逐檔檢視 `demo_data/`、`examples/agentic_runs/`、`examples/reports/`、測試 fixture：

- 裁判 id 必須落在合成命名空間：`DEMO` 前綴或 `TSTV` 法院碼或字別「測」，且日期為未來日期。
- 所有 URL 必須是 `example.test` 或其他保留網域；不得出現任何真實官方網域的完整可解析連結（文件中描述官方資料來源時使用文字名稱，不放深層連結）。
- 不得出現：真實形狀的裁判字號（六段逗號格式而不在合成命名空間內）、身分證樣式、真實當事人姓名、真實案件事實。
- 新增 fixture 的 PR 必須在描述中聲明資料為合成，reviewer 逐筆抽查。

## D. 宣稱一致性審核

對照文件與程式，確認「說的沒有大於做的」：

| 檢核點 | 依據 |
|---|---|
| README 與 AGENTIC_WORKFLOW 含「本 repo 不含 LLM / agent，agent 角色由外部呼叫端供給」聲明 | NEXT_FIX_SPEC G2 |
| 不出現「no ranking weights」式絕對句；demo 公式標示為 illustrative | NEXT_FIX_SPEC G3 |
| THREAT_MODEL 與 TRUST_MODEL 可分辨「repo 已強制」與「部署者責任」 | NEXT_FIX_SPEC G4 |
| `docs/AGENTIC_HARNESS_ACCEPTANCE.md` 的 Not Claimed 清單沒有被新文件或 README 措辭違反 | ACCEPTANCE |
| 新增 MCP tool 或 schema 都已文件化且有測試 | v0.2.1 F5 / F7 |

## E. 閘門預設審核

任何觸及 `verification/`（source policy、citation validator、trust gates）的變更：

- **預設行為只能變嚴，不能變鬆。** 任何鬆綁（新的可過閘路徑、新的替代欄位）必須是顯式 opt-in、預設 OFF，並有 fail-closed 測試證明預設路徑行為不變。
- 自我宣告的 metadata（呼叫端傳入的字串）不得單獨成為 allow_final 的充分條件；必須有 resolver 或等效驗證步驟。
- 對每個新增的過閘路徑，補一條「捏造輸入必須被拒」的負向測試。

## F. 發布操作

- 發布用的 clone 只掛公開 repository 的 remote 與 refs；不得在同一個 clone 內混掛任何含未公開歷史的 remote。禁止使用 `git push --all` 與 `git push --mirror`，一律顯式推 `main` 與 tag。
- tag 前重跑 A 節全部指令。
- release notes 記錄本規程的執行結果（執行日期、執行人、B 節工具版本、發現與處置）。

## 例外處理

- 發現疑似真實資料、密鑰或私有路徑：**不開公開 issue**，依 `SECURITY.md` 的私下回報路徑處理；已推送者視同外洩，撤下並重建歷史，不以「後續 commit 刪除」了事。
- 對任何一步的判斷有疑慮：延後發布，先解決疑慮。
