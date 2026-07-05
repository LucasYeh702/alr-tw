# ALR-TW 第二輪 Hardening 規格書（2026-07 審核落地）

> Status for v0.4.0: G1-G10 shipped together in v0.4.0. The planned
> v0.3.1/v0.4 split was collapsed into one release, and
> `feature/tlr-raw-backed-verifier` was converged into `main` and deleted.
> The historical planning body below is otherwise preserved.

本規格書彙整 2026-07 多代理安全審查（資料洩漏面、MCP 執行期面、定位與邊界面，含逐項對抗式覆核）的結果，作為下一輪公開版 hardening 的工程規格。上一輪規格（v0.2.1，F1-F10）已於 v0.2.1 / v0.3.0 出貨完畢，內容見 git history 與 `docs/RELEASE_NOTES.md`。

## 審查結論

- 經對抗式覆核，公開 repo **沒有 high / medium 安全缺口**。git 歷史乾淨、demo 資料確為合成、MCP JSON-RPC 攻擊面乾淨、prompt injection 宣稱在程式碼中成立。
- 存活的安全發現為 **3 項 low**，全部屬於「發布守門腳本的覆蓋缺口」：目前無實際洩漏，但削弱對未來人為失誤的防護（G5、G6、G7）。
- 主要應修的是 **3 處「文件宣稱大於程式實作」的落差**（G2、G3、G4）。
- `feature/tlr-raw-backed-verifier`（最小資料版）的識別碼替代規則**不應以無旗標的預設行為出貨**；意圖正當，載體需要修正（G1）。

目標版本切分：

| 版本 | 內容 | 性質 |
|---|---|---|
| `v0.3.1` | G2-G10 | 措辭校準、守門硬化、CI、規程，無行為變更 |
| `v0.4` | G1 | verified_cache 識別碼替代的 opt-in 行為變更 |

## 範圍

允許納入公開 repo 的內容不變（synthetic demo data、framework code、deterministic traces、tests、CI、docs、public-safe validation examples）。

不在本輪範圍：

- production corpus、真實法律全文、私有 cache 或 vector index
- 私有 ranking / chunking 調校值與 private evaluation holdouts
- 任何預設啟用的真實資料下載或自動申請官方 access 的功能
- credentials、user records、logs

## 審查發現統整

| 發現 | 覆核判定 | 修正項目 |
|---|---|---|
| 識別碼替代（identifier OR url）為所有使用者的出貨預設，且 identifier 是自我宣告 metadata，程式內無 resolve 或 rehash | 非新引入的安全漏洞（main 本就只做真值檢查），但屬品牌與信任風險；需護欄 | G1 |
| 文件稱 AI-agent-driven，但 repo 不含任何 LLM 呼叫；agent 角色須由外部 MCP client 供給一事未明文 | 採納：harness 名稱成立，agentic 措辭需校準 | G2 |
| 文件稱 no ranking weights，但 repo 實際出貨 demo ranking 公式與硬編碼 tier 分數 | 採納：措辭與實作對齊 | G3 |
| THREAT_MODEL 稱 final cache requires URL, hash, verification time，易被讀成已出貨位元組級重驗 | 採納：補交叉引用 | G4 |
| 兩支守門腳本 size cap 不一致（1MB 對 5MB），且 5MB 那支不掃密鑰賦值樣式 | 採納（low） | G5 |
| 非 UTF-8 檔案內容掃描被靜默略過；台灣資料常見 Big5，屬真實規避向量 | 採納（low） | G6 |
| 守門只查結構性標記，不查領域洩漏（真實裁判字號、身分證樣式、法院代碼、當事人名可通過） | 採納（low） | G7 |
| 公開版缺一份標示清楚的部署參數起點與可用的 ingestion adapter 骨架，實作者難以接上 | 採納（可用性，非安全） | G8 |
| 守門只掃工作樹不掃 git 歷史 | 已於 SECURITY.md 揭露為邊界；採納為 CI 縱深強化 | G9 |
| caller 宣告 source_tier 即被信任 | 駁回：已文件化且經契約測試的信任邊界（tier 由 adapter/verifier 層賦值） | 無 |
| privacy masking 為 demo heuristic、可繞過 | 駁回：v0.2.1 F1 已降級宣稱並文件化 known limitation | 無 |
| claim support 未接入即時閘門 | 駁回：`not_checked` 語意已誠實揭露 | 無 |

## G1. Identifier-Backed Verified Cache 護欄與分支處置

目標版本：`v0.4`。

### 問題

`feature/tlr-raw-backed-verifier` 將 `classify_citation_use` 的 verified_cache 條件由「official_url 且 official_hash 且 verified_at」鬆綁為「(official_url 或 official_identifier) 且 official_hash 且 verified_at」。

- 鬆綁**無 feature flag、無 config**，是該分支所有使用者的出貨預設。
- `official_identifier` 僅作字串穿透：驗證層沒有任何「解析識別碼對應本地官方原始檔、重算 content hash」的邏輯；文件描述的五步 promotion flow 只存在於散文。
- 新增測試斷言「任意 identifier 字串 + 任意 hash + 任意時間即得 allow_final」，等於用測試把自我宣告 metadata 固化為可過閘的證據。
- 分支已領先 main 並開始漂移，onboarding 路徑與合規警語只保護分支使用者。

裁判類資料以穩定字號為鍵、逐筆 URL 不耐久，這個動機是對的；問題在預設行為與可驗證性。

### 需求

- 識別碼替代必須是**顯式 opt-in，預設 OFF**：新增能力開關（例如 `identifier_backed_verified_cache`），未開啟時行為與 v0.3 完全相同（嚴格 URL + hash + time）。
- **限縮適用範圍**：僅 `source_tier == verified_cache` 且裁判類 record 可用識別碼替代；法規與憲法類 record 仍要求 official_url。
- **讓識別碼可驗證而非自我宣告**：定義 resolver extension point 介面——輸入 official_identifier，解析到本地下載的官方原始 record，重算 content hash，與宣告的 official_hash 比對；不符或無法解析一律 reject，並回專屬 error code（例如 `IDENTIFIER_UNRESOLVED`、`IDENTIFIER_HASH_MISMATCH`）。公開 repo 內建 synthetic resolver 示範 match 與 mismatch 兩種路徑。
- **schema 語意升級**：識別碼路徑不得只靠裸字串；record 需同時攜帶 resolver 產出的驗證證據欄位（例如 `identifier_resolution` 含 hash_algo 與 resolution 狀態），讓 schema 本身表達「單靠識別碼不足」。
- **分支處置**：將 opt-in 版實作與文件併入 main 後，刪除長期存活的 feature branch。若 opt-in 實作暫緩，先只併入 docs（`docs/TLR_CANDIDATE_MODE.md` 的 recipe 與合規警語），並將分支上的預設鬆綁還原。
- 口徑修正：對外稱「裁判類的較低摩擦驗證 recipe」，不稱「半開箱即用」。使用者仍須自行取得官方 access 並下載原始月檔，這一點在文件中維持顯著。

### 驗收條件

- 預設模式：identifier-only 的 verified_cache（無 official_url，任意 hash 與時間）**不得** allow_final，fail closed 並帶 error code。
- opt-in 模式 + synthetic resolver 命中且 hash 相符：allow_final。
- opt-in 模式 + resolver 未命中或 hash 不符：reject，error code 明確。
- opt-in 模式 + 法規或憲法類 record 使用 identifier-only：reject。
- CI 有一條斷言：未經 resolver 驗證的 identifier-only verified_cache 在任何預設路徑都到不了 allow_final。
- `docs/TOOL_CONTRACT.md`、`docs/TLR_CANDIDATE_MODE.md`、`docs/source_policy.md`、`docs/TRUST_MODEL.md` 與 opt-in 語意一致。
- 長期 feature branch 不再存在（內容已併入或還原）。

## G2. Agentic 定位明文

目標版本：`v0.3.1`。

### 問題

repo 的 runtime 依賴只有 `mcp`，全 codebase 無任何 LLM 呼叫；`run_agentic_demo` 與 `agentic_legal_research` 是確定性管線。文件已揭露 deterministic 性質，但「LLM / agent 角色必須完全由外部 MCP client 供給、本 repo 出貨零 agent 推理」從未平白寫出，且 README 使用「AI-agent-driven」「agent 可以做 trust-gate decision」等語，工具又名為 `agentic_legal_research`，讀者容易誤以為 repo 內含某種 agent。

### 需求

- README（三語）與 `docs/AGENTIC_WORKFLOW.md` 頂部加入明文聲明，語意等同：「本 repo 不包含 LLM，也不包含 agent。規劃與選工具的 agent 角色由呼叫端（外部 MCP client 或 LLM runtime）提供；ALR-TW 提供工具介面、確定性閘門圖與 trace / 報告契約，用來約束該外部 agent。」
- 措辭替換：trust-gate decision 由確定性 harness 做出，不由 agent 做出；「AI-agent-driven」改為「constrains an external agent」或等義表述。
- `docs/TRACE_SCHEMA.md` 與 README 明確綁定：`agentic_legal_research` 與 `run_agentic_demo` 的輸出是確定性合成管線結果，`examples/agentic_runs/*.json` 不是 agent 推理的執行錄影。
- 可選：為 `agentic_legal_research` 補上工具描述註記（canned deterministic demo），或於未來版本更名；本輪不強制改工具名。

### 驗收條件

- 三份 README 與 `docs/AGENTIC_WORKFLOW.md` 均含上述聲明。
- `docs/AGENTIC_HARNESS_ACCEPTANCE.md` 的 Not Claimed 清單增列「an LLM or agent implementation shipped in this repo」。
- 新增或擴充一條 docs-consistency 測試：關鍵聲明字串存在於 README 與 AGENTIC_WORKFLOW。

## G3. Ranking 參數宣稱校準

目標版本：`v0.3.1`。

### 問題

README 與 `docs/ARCHITECTURE_CONTRACT.md` 平白寫「不提供 ranking weights / ranking formula」，但 repo 實際出貨一個具體 demo 公式：`retrieval/judgment_ranking.py`（authority 分數與 issue-tag、lexical 權重）、`retrieval/authority_ranker.py`（硬編碼 source-tier 分數表）、`retrieval/rrf.py`（固定 k 值）。宣稱與實作字面矛盾。

### 需求

- 措辭改為：「**調校後的 production ranking 參數**不公開；repo 內含的是**示範用 demo 公式與通用預設**（RRF、tier 分數表），不代表閉源 runtime 的實際配置。」
- `DATA_POLICY.md` 的 deployment-specific tuning 清單同步加註。
- 在 demo ranking 模組的 docstring 標明 demo / illustrative 性質。

### 驗收條件

- 全 repo 不再出現「no ranking weights」式的絕對句。
- `judgment_ranking.py`、`authority_ranker.py`、`rrf.py` docstring 標明 demo 性質。

## G4. 驗證責任交叉引用

目標版本：`v0.3.1`。

### 問題

`docs/THREAT_MODEL.md` 的「Verified cache poisoning → final cache requires URL, hash, and verification time」易被讀成公開 repo 已出貨位元組級重驗。實際上 `classify_citation_use` 只檢查欄位存在性；內容重驗屬部署者 promotion pipeline（`docs/ARCHITECTURE_CONTRACT.md` 的 extension point）。

### 需求

- THREAT_MODEL 該列補一句：欄位存在性由本 repo 檢查；位元組級內容重驗由部署者的 promotion pipeline 執行，交叉引用 ARCHITECTURE_CONTRACT 對應段落。
- `docs/TRUST_MODEL.md` 若有同型句子，一併補註。

### 驗收條件

- 讀者從 THREAT_MODEL 任一句都能分辨「repo 已強制」與「部署者責任」。

## G5. 守門腳本一致化

目標版本：`v0.3.1`。

### 問題

`scripts/check_no_forbidden_files.py` 上限 5MB，但不掃密鑰賦值樣式；`src/alr_tw/scripts/check_public_boundary.py` 掃密鑰賦值樣式，但只掃 1MB 以下檔案的內容。兩者之間存在 1MB-5MB 的密鑰樣式盲區，且超過上限的檔案內容被靜默跳過。

### 需求

- 兩支守門共用同一個 size 上限常數。
- 將密鑰賦值偵測（`api[_-]?key`、`token`、`secret` 後接賦值符號的樣式）加入 `check_no_forbidden_files.py`。
- 超過上限的文字檔不得靜默跳過：以分塊串流掃描，或直接回報違規（本 repo 為全文字小檔 repo，超大文字檔本身即異常）。

### 驗收條件

- 單元測試：1MB-5MB 合成文字檔內含密鑰賦值樣式時，至少一支守門攔下。
- 單元測試：超過上限的文字檔被回報（違規或掃描完成），不被靜默跳過。

## G6. 非 UTF-8 檔案守門處置

目標版本：`v0.3.1`。

### 問題

`check_no_forbidden_files.py` 對 UnicodeDecodeError 直接 continue，非 UTF-8 檔案的**全部內容檢查**被靜默略過。台灣法律資料常見 Big5 編碼，構成真實的規避向量（無論有意或無意）。

### 需求

- 二擇一（建議後者）：
  - 對解碼失敗檔案改用位元組層回退掃描 ASCII 可表示的標記。
  - 直接將任何非 UTF-8 的追蹤文字檔判為違規：全文字公開 repo 沒有正當理由存在非 UTF-8 檔。
- 允許清單機制保留給未來確有需要的二進位資產（目前無）。

### 驗收條件

- 單元測試：以 tmp 目錄建立 Big5 與 UTF-16 合成檔，守門必須回報（違規或攔到內容標記），不得靜默通過。

## G7. 領域洩漏守門

目標版本：`v0.3.1`。

### 問題

守門只查結構性標記（絕對使用者路徑、密鑰樣式等），不查**領域洩漏**：真實形狀的裁判字號（六段逗號格式：法院代碼,年度,字別,號,日期,序號）、台灣身分證樣式（一大寫字母 + 1 或 2 + 八碼數字）、真實法院代碼、當事人姓名都能通過。repo 自己的 `legal_nlp/privacy.py` 已有身分證與姓名 regex，卻只接到執行期查詢遮罩，沒接到發布守門。「synthetic only」這條核心保證對最該防的內容類型反而沒有機械防線。

### 需求

- 發布守門加入領域規則，採「demo 命名空間白名單 + 真實樣式黑名單」雙軌：
  - 白名單：demo 裁判 id 必須落在合成命名空間（`DEMO` 前綴、`TSTV` 法院碼、字別「測」、未來日期），fixture 檔案中出現六段逗號格式而不符合命名空間者即違規。
  - 黑名單：身分證樣式 regex（重用 `privacy.py` 的定義）出現在任何追蹤檔即違規。
- 真實法院代碼表與姓名偵測可列為 known limitation，不強制本輪完成；先把「有 regex 可查的」接上。
- 更新 `SECURITY.md` 的 release checks 段落，說明守門已涵蓋領域樣式。

### 驗收條件

- 單元測試：含真實形狀裁判字號或身分證樣式的合成 fixture 會被攔下；現有 demo fixtures 全部不誤報。
- `demo_data/` 與 `examples/` 現有內容通過新守門。

## G8. 部署起點文件與 ingestion 骨架

目標版本：`v0.3.1` 或 `v0.4`。

### 問題

repo 刻意不出貨調校參數（正確），但完全不給起點，實作者難以把 harness 接上真實資料；`ingestion/staging.py` 目前僅是數行 stub。「參考實作」的可用性低於其文件品質。

### 需求

- 新增 `docs/DEPLOYMENT_STARTING_POINTS.md`：提供**標示為 illustrative、非生產配置、不代表閉源 runtime**的公開安全起點——chunk 大小與 overlap 的量級與選型準則、開源 embedding 模型的選項與維度考量、向量索引參數的意義與 trade-off、RRF 與 tier 分數的示範值即 repo 內 demo 公式。每一項寫「怎麼自己量測決定」，不寫「我們生產環境用多少」。
- 把 `ingestion/staging.py` 從 stub 擴成可繼承的 adapter 骨架：明確的介面、TODO hooks、synthetic 範例實作，與 `docs/ARCHITECTURE_CONTRACT.md` 的資料流契約對齊。
- 私有調校值與 private evaluation holdouts 維持不公開。

### 驗收條件

- 文件每節都有 illustrative 免責標示；boundary 守門通過。
- synthetic adapter 範例可跑通 staging 到 citation validation 的最小路徑（沿用現有 synthetic fixtures）。

## G9. Git 歷史掃描 CI

目標版本：`v0.3.1`。

### 問題

守門只掃工作樹。`SECURITY.md` 已誠實揭露「乾淨的工作樹不代表歷史安全」並建議 gitleaks / trufflehog，但這些只是建議，沒有機械執行。

### 需求

- CI 新增歷史掃描 job（gitleaks 或 trufflehog，擇一），對 push 與 PR 執行；首次導入時做一次全歷史基線掃描。
- `SECURITY.md` release checks 段落由「建議」改為引用 CI job。

### 驗收條件

- CI 綠燈包含歷史掃描 job。
- 在測試分支塞入合成密鑰可觸發 CI 失敗（驗證後移除）。

## G10. Repo 衛生與發布規程

目標版本：`v0.3.1`。

### 問題

- 分支上有未追蹤檔案待決（`docs/TLR_CANDIDATE_MODE.zh-TW.md` 應提交；`ASK_YOUR_AI_AGENT_FULL_RAG.zh-TW.md` 依 v0.2.1 規格維持 untracked 且 excluded，除非另行核准）。
- 發布前檢查散落在 `SECURITY.md` 與 `docs/AGENTIC_HARNESS_ACCEPTANCE.md`，缺一份可重複執行的完整規程。

### 需求

- 新增 `docs/RELEASE_AUDIT_PROCEDURE.md`（隨本規格書一併提交），內容涵蓋：工作樹審核、git 歷史審核、fixture 合成性審核、宣稱一致性審核、閘門預設審核、發布操作原則。
- `SECURITY.md` 與 `docs/AGENTIC_HARNESS_ACCEPTANCE.md` 交叉引用該規程。
- README 規格文件清單加入該規程連結。
- 處理上述未追蹤檔案。

### 驗收條件

- 規程文件存在且被 SECURITY.md 引用。
- `git status --short` 在 release tag 時乾淨。

## 建議實作順序

1. G2 Agentic 定位明文（最小成本、最大誠實度收益）
2. G3 Ranking 宣稱校準
3. G4 驗證責任交叉引用
4. G5 守門一致化
5. G6 非 UTF-8 處置
6. G7 領域洩漏守門
7. G10 規程與衛生
8. G9 歷史掃描 CI
9. G8 部署起點與 ingestion 骨架
10. G1 識別碼替代 opt-in（獨立為 `v0.4`，含分支收斂）

G2-G7 與 G10 原規劃在下一個 release tag（`v0.3.1`）前完成；G1 原規劃獨立進入 `v0.4`。實際發布時已收斂為 v0.4.0，一次完成 G1-G10；`feature/tlr-raw-backed-verifier` 已不再作為 onboarding 路徑。

## 必跑驗證

任何 follow-up push 前必須通過：

```bash
git diff --check
python3 scripts/check_no_forbidden_files.py
python3 scripts/check_public_boundary.py
uv run --extra dev ruff check .
uv run --extra dev pytest
uv run --extra dev alr-tw-demo
uv run --extra dev python examples/agentic_mcp_client_demo.py
```

若有 MCP changes，另需跑 stdio smoke，覆蓋 initialize、initialized notification、tools/list、tools/call。發布前另依 `docs/RELEASE_AUDIT_PROCEDURE.md` 執行完整審核。

## Definition Of Done

本輪 hardening 完成時，必須滿足：

- 預設 citation 行為與 v0.3 相同：verified_cache 未經 opt-in 與 resolver 驗證，identifier-only 一律 fail closed
- 三處「宣稱大於實作」全部消除：no-LLM 聲明、ranking 措辭、驗證責任交叉引用
- 守門測試覆蓋密鑰樣式盲區、非 UTF-8 檔、領域洩漏樣式三類案例
- CI 含 git 歷史掃描
- `docs/RELEASE_AUDIT_PROCEDURE.md` 存在並被 SECURITY.md 引用
- 長期 feature branch 收斂（併入或還原）
- public safety checks 與 full tests 通過
- `ASK_YOUR_AI_AGENT_FULL_RAG.zh-TW.md` 除非另行明確核准，否則維持 untracked 且 excluded
