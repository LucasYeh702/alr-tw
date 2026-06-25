# 台灣法律 RAG / MCP 信任基礎設施

語言版本：繁體中文 | [English](README.en.md)

這是一個用於建構台灣法律 RAG 與 MCP 系統的資料庫框架與法學資料工具參考實作。它的目標是讓法律 AI 在回答前，能先查找資料、辨識來源、檢查引用，並在資料不足時停止產生看似肯定的答案。

在一個台灣法律 AI 產品中，這個框架可以扮演「法律資料底座」：上層的聊天機器人、研究助理或法務工作流不直接相信模型記憶，而是透過這個資料層取得法條、裁判、憲法法庭資料、來源狀態與引用檢查結果。

本專案不是開箱即用的完整法律資料庫，也不提供法律意見。它展示的是一套可自行接入政府開放資料、官方 API、外部語意召回服務與本地 verified cache（已驗證快取）的框架，並提供一組可測試的法學資料工具：檢索、引用驗證、來源分級、覆蓋率檢查、版本時間軸、審級關係圖與答案信任閘門。

> [!IMPORTANT]
> 本專案是技術框架與參考實作，內建資料均為 synthetic data（合成資料），僅供開發、測試與流程展示使用。本專案不提供真實法律資料庫內容，也不提供法律意見。

換句話說，這個 repo 的目標不是「內建所有台灣法律資料」，而是示範如何把台灣法律資料整理成 AI 可以安全查詢、可追溯引用、可控風險的 RAG 基礎設施。

## 可以怎麼作為台灣法律 RAG

在實際系統中，這個框架可以放在 LLM（大型語言模型）或 AI agent（AI 代理）後方，作為法律資料檢索與驗證層：

```text
使用者問題
-> 台灣法律資料庫 / 外部語意召回 / 官方 API
-> 候選資料召回
-> 法規、裁判、憲法法庭資料、法學知識卡片整理
-> citation validation
-> trust gate
-> 提供給 LLM 生成回答或輔助研究摘要
```

它支援的 RAG 用途包括：

- 讓使用者用白話問題查找可能相關的法條、裁判或法學資料
- 把語意搜尋找到的結果先當成「候選資料」，再回官方來源或 verified cache 驗證
- 對 AI 回答中的引用逐筆檢查：是否存在、是否可引用、是否只能當候選線索
- 告訴 AI 目前資料覆蓋是否充分，避免在資料不足時裝作有把握
- 在沒有可確認引用時阻擋答案，改為提示需要官方核對或人工判斷

例如，使用者問「租約到期後房東不退押金可以怎麼處理？」時，上層 AI 可以先透過本框架查找可能相關的民法條文、租賃爭議裁判與資料覆蓋狀態，再把查到的候選資料交給模型整理，而不是直接讓模型憑印象作答。

## 可以怎麼作為 AI 輔助工具

這個框架可以支援律師、法務、研究者或法律科技產品中的 AI 輔助流程，例如：

- 問題初步分流：辨識查詢較接近租賃、侵權、勞動、刑事或憲法等議題
- 法條與裁判候選召回：整理可能相關的法條、裁判或憲法法庭資料
- 引用安全檢查：確認某個 citation 是官方、verified cache、candidate-only 或 unknown
- 研究摘要前處理：先整理 issue brief、版本時間軸、審級關係，再交給 LLM 摘要
- 風險提示：當資料來源不足、只找到外部候選或 coverage 低信心時阻擋答案
- 工具化介面：用 MCP tools 暴露搜尋、exact lookup、citation validation 與 trust gate

它可以用在法律 AI 的「回答前準備」階段：先找資料、先檢查引用、先標記風險，再讓模型整理成摘要、研究備忘錄或下一步查核清單。它不取代法律專業判斷，而是提供「AI 在回答前必須先查證與自我約束」的資料工具層。

## 提供哪些法學資料工具

目前 reference implementation（參考實作）以 synthetic data（合成資料）示範下列工具：

| 工具 | 作用 |
|---|---|
| `legal_search` | 法律資料檢索入口，整合 query understanding、coverage、ranking 與 trust gate |
| `validate_citation` | 檢查 citation 狀態與來源是否可作 final citation |
| `exact_law_lookup` | 依法律名稱與條號做精確查找 |
| `exact_judgment_lookup` | 依裁判 `jid` 做精確查找 |
| `exact_constitutional_lookup` | 依憲法法庭 synthetic id 做精確查找 |
| `source verification batch` | 批次驗證來源，去重並統計 final / candidate-only |
| `authority recall` | 只召回可作 final citation 的可引用來源；此處 authority 指來源真實性與引用資格 |
| `stateful coverage report` | 回傳資料覆蓋狀態、原因與 evidence count |
| `law version timeline` | 示範法規版本時間軸結構 |
| `appellate lineage graph` | 示範裁判審級關係圖 |
| `search baseline / snapshot / soak` | 示範檢索基準、快照比對與長時間穩定性檢查 |
| `retriever cache` | 示範不落地的 in-memory retriever cache |

這些工具大致對應到 RAG 流程中的三段：`legal_search` 與 exact lookup 負責找資料，`validate_citation`、`source verification batch` 與 `authority recall` 負責檢查來源，coverage report 與 trust gate 負責判斷 AI 能不能安全作答。

這些工具目前都使用 synthetic data。實務上可以替換 adapter，接入司法院開放資料、法務部法規資料、憲法法庭資料、企業內部法務資料或其他合規資料源。

## 為什麼需要這個專案

法律 AI 的風險不只是回答錯，而是錯得很有信心，而且難以追溯。常見失敗包括：

- 把語意相似的資料當成可引用來源，或把可驗證來源誤讀成有通案拘束力的法律見解
- 混用官方來源、未驗證資料集與檢索候選結果
- 產生看似可信但沒有根據的引用
- 在檢索覆蓋不足時仍然給出肯定答案
- 在官方驗證前就把 staging data 推進可引用索引
- 把含有敏感資訊的使用者 query 送往外部召回系統

本 repo 用可重現的 synthetic data（合成資料）示範法律檢索與法律代理工具周邊所需的信任基礎設施：source trust（來源信任）、citation verification（引用驗證）、privacy masking（隱私遮罩）與 fail-closed answer validation（不安全就拒絕展示的答案驗證）。

## 提供的能力

核心元件：

- MCP-style legal retrieval tools（MCP 風格法律檢索工具）
- query understanding：隱私遮罩、引用解析、議題標籤、意圖判斷
- source trust policy：官方、verified cache、staging、external semantic recall、synthetic、unknown 來源分級
- citation validation：`exists`、`not_found`、`unverifiable` 三態；其中 `unverifiable` 在 trust gate 中應比照 `not_found`，不得作為 final citation，除非另有人工審查流程
- answer trust gate：沒有 final citation 時 fail closed，也就是不安全就拒絕展示答案
- stateful coverage flags：用 `present`、`absent`、`not_checked`、`low_confidence` 表示資料覆蓋狀態

以 synthetic data 示範的進階模式：

- source verification batch
- authority recall：只保留可作 final citation 的可引用來源；此處 authority 指 source authenticity / citation eligibility
- search baseline / snapshot / soak checks：檢索基準、結果快照與穩定性檢查
- in-memory retriever cache
- appellate lineage graph（審級關係圖）
- law version timeline（法規版本時間軸）
- legal knowledge layer scaffold
- judgment ranking evaluation
- exact law / judgment / constitutional lookup tools

## 架構概覽

```text
User Query
-> Privacy Masking
-> Query Normalization
-> Citation Parsing
-> Query Understanding
-> Candidate Retrieval
-> Authority Recall
-> Ranking / Coverage / Knowledge Layer
-> Source Trust Policy
-> Citation Validation
-> Trust Gate
-> Answer Wrapper
```

核心規則很簡單：檢索候選不是可引用來源。Final citation 必須來自官方來源，或是可回溯官方 URL、hash 與驗證時間的 verified cache。

Final citation 只表示「來源可驗證、可引用」，不表示該資料中的法律見解具有通案拘束力或最高法律效力。實務導入時應另行標示 `legal_effect_type` 或 `normative_weight`，區分現行法規、憲法法庭主文、憲法法庭理由、協同或不同意見、大法庭裁定、最高法院或最高行政法院裁判、下級審個案判決與外部候選資料。

## Demo Data

本 repo 內建資料全部是 synthetic data。這些資料只用來測試檢索、驗證與 trust gate 流程，不散布 production legal corpus、官方全文快取、使用者 log 或私有 eval set。

Synthetic data 可以用來展示 demo 裡「找得到一筆資料」，但它永遠是 `demo_only`，不得被當成台灣現行法律。

## 資料來源接入

本專案不內建 production data，也不替使用者下載官方資料。實際使用時，使用者應依自己的研究、產品或合規需求，向政府開放資料平台或各主管機關取得資料，再自行實作 adapter（接入器）與 ingestion pipeline（匯入流程）。

接入政府開放資料或官方 API 時，除技術實作外，使用者也應遵守政府資料開放授權條款、各機關資料開放宣告、來源標示義務與相關使用限制。

建議為每個資料來源保留最小 `source_manifest`，讓系統能在 UI、匯出結果或下游文件中呈現來源與授權資訊：

```yaml
provider: "資料提供機關"
dataset_name: "資料集名稱"
dataset_version: "資料集版本或發布日期"
license_name: "授權條款名稱"
license_url: "授權條款 URL"
attribution_text: "建議來源標示文字"
source_url: "官方資料來源 URL"
retrieved_at: "取得時間"
terms_reviewed_at: "使用條款檢視時間"
redistribution_allowed: false
```

不同機關的資料開放宣告可能不同，不能假設所有政府資料都適用完全相同的重製、散布或商業使用條件。

建議接入流程：

```text
政府開放資料 / 官方 API / 官方下載檔
-> source adapter
-> staging index
-> official verification
-> source trust policy
-> promotion manifest
-> retriever / MCP tools
```

本專案公開的是可替換的資料流介面與驗證邊界，而不是正式環境的調校細節。`src/tw_legal_rag_mcp/contracts.py` 與 `tests/integration/test_synthetic_contract_pipeline.py` 使用合成資料示範資料來源描述、接入結果、候選召回、引用驗證、信任閘門與答案驗證如何銜接；正式導入時的切片策略、排序權重、embedding 模型、索引參數與真實資料則由使用者依資料規模、硬體條件與合規需求自行設定。

接入後仍應保留本專案的核心邊界：

- 未驗證資料先進 staging，不直接進 final citation index
- 官方來源或 verified cache 才能成為 final citation 候選
- 外部語意召回只回傳 candidate，不提供引用權威
- 對刪除、撤回、異動或不可公開資料要有更新與移除機制
- 不把 token、cache、全文資料或私人查詢紀錄 commit 進 repo

## 導入法規、判決與憲法法庭資料

Demo 流程只示範工具怎麼運作；實務導入時，應把不同法律資料拆成不同 adapter，再用同一套 source trust policy 與 citation validation 管理。

### 法規資料

法規資料適合做 exact lookup、條文版本比對與 RAG 的基礎引用來源。導入時建議保留：

- 法規名稱、條號、項次、款目與條文文字
- 公布日期、修正日期、施行日期與版本狀態
- 官方來源 URL、抓取時間、內容 hash 與資料來源識別
- 廢止、停止適用或歷史版本標記
- `legal_effect_type` 或 `normative_weight`，例如現行有效法規、歷史法規或廢止法規

法規資料進入系統後，應先建立法規名稱與條號的標準化索引，再建立版本時間軸。AI 回答引用法條時，應優先走 `exact_law_lookup` 與 `validate_citation`，避免只靠語意相似度找到錯誤條文。

### 判決資料

判決資料適合支援案例召回、爭點整理、裁判見解比較與審級關係追蹤。導入時建議保留：

- 裁判 `jid`、法院、年度、字別、案號、裁判日期與案由
- 主文、理由、裁判結果與可公開全文狀態
- 審級、前後審關係、關聯裁判與異動狀態
- 官方來源 URL、抓取時間、內容 hash 與資料來源識別
- `legal_effect_type` 或 `normative_weight`，例如大法庭裁定、最高法院裁判、最高行政法院裁判或下級審個案判決

判決資料應先進 staging index，經官方來源核對後才能升級為 `official` 或 `verified_cache`。外部語意召回找到的判決只能作為候選線索，不能直接成為 final citation。

### 憲法法庭資料

憲法法庭資料適合支援憲法議題檢索、裁判主文與理由摘要、法規違憲審查脈絡整理。導入時建議保留：

- 裁判或解釋識別碼、年度、字號、案名與作成日期
- 主文、理由、不同意見或協同意見的公開狀態
- 涉及法規、憲法條文、爭點標籤與關聯資料
- 官方來源 URL、抓取時間、內容 hash 與資料來源識別
- `citation_role` 或 `opinion_role`，例如主文、多數理由、協同意見、不同意見或程序裁定

台灣憲法裁判資料同時包含舊制「司法院大法官解釋」（例如釋字）與新制「憲法法庭裁判」（例如憲判字、憲裁字），導入時的 normalization 應同時相容兩套識別碼結構，避免 exact lookup 因字號格式不同而失敗。

憲法法庭資料的引用風險通常比一般檢索結果更高，因此應明確區分「找到相關資料」與「可作為正式引用」。在本框架中，應透過 `exact_constitutional_lookup`、source trust policy 與 trust gate 共同判斷是否能交給 AI 作為回答依據。Trust gate 也應避免把協同意見或不同意見包裝成憲法法庭主文或多數理由。

### 建議導入順序

```text
法規資料
-> 建立 exact lookup 與版本時間軸
-> 判決資料
-> 建立案例召回與審級關係
-> 憲法法庭資料
-> 建立憲法議題與關聯資料索引
-> 統一 citation validation 與 trust gate
```

導入完成後，AI 不應直接讀取原始資料檔作答，而應透過 MCP tools 或 retriever 取得已標示來源狀態、覆蓋率與引用資格的結果。

### 為什麼不內建切片與索引參數

本 repo 刻意不提供固定的 chunk size、overlap、embedding model、向量維度、HNSW 參數或 SQLite FTS 設定。這不是缺漏，而是為了保留使用者依自己需求調整精度、召回率、儲存空間與部署成本的彈性。

如果本地硬體條件足以支撐高精度語意切分、向量索引與重建流程，使用者可以選擇完全以本地索引層完成語意召回，不需要另外安裝或串接外部語意層。外部語意層在本框架中只是雙軌方案的一種：當本地硬體、儲存空間或運算時間不足時，可以用來補足召回能力，但仍必須經過來源驗證與 trust gate。

法律資料的最佳切片與索引策略會受多個因素影響：

- 資料類型：法規條文、判決理由、憲法法庭意見書的段落結構不同
- 使用情境：法條 exact lookup、案例召回、語意探索、研究摘要需要的粒度不同
- 精度需求：越細的切片可能提高定位能力，但也可能犧牲上下文完整性
- 空間容量：向量數量、全文索引大小與快取策略會直接影響儲存成本
- 更新頻率：資料異動越頻繁，索引重建與版本管理成本越需要控制
- 部署環境：本機工具、團隊內部服務與雲端產品可承受的 latency 與成本不同

因此，本專案只定義資料來源、驗證、引用資格與 trust gate 的框架；實際切片、索引與 ranking 參數應由使用者依資料規模、硬體資源、精度要求與合規政策自行設定。

## 可選外部語意召回

本框架中的 `external_semantic_recall` source tier（外部語意召回來源層）是為了表達一種常見架構：系統可以利用外部語意檢索服務提高召回率，但不能把外部召回結果直接當成 final citation。

如果使用者有外部語意召回的需求，可以考慮使用 Taiwan Legal RAG / TLR 生態系中的開源專案，並依其授權與服務條款自行串接。本框架在此列出來源，是為了保留 attribution（來源標示）並明確區分外部候選召回與本框架的 final citation 驗證流程：

- [`aa0101181514/tw-legal-rag`](https://github.com/aa0101181514/tw-legal-rag)：Taiwan Legal RAG CLI，連接法律偵探（Legal Detective / Dr.Lawbot）建置的台灣裁判語意檢索服務。
- TLR / Legal Detective 的語意召回能力可協助找到候選裁判或相關資料，但在本框架裡仍被歸類為 `external_semantic_recall`。

為避免混淆，本 repo 是獨立框架，不內建 TLR endpoint、不代理 TLR 服務、不散布 TLR response cache，也不保證或維護任何第三方外部服務的可用性。本 repo 也不宣稱外部語意召回結果本身具有法律引用權威。若使用者自行串接 TLR、tw-legal-rag 或其他外部語意層，建議維持以下邊界：

> [!WARNING]
> 本 repo 與 TLR、Legal Detective、Dr.Lawbot 或其他第三方語意召回服務沒有官方合作、授權或背書關係。使用者自行串接外部服務前，應確認服務條款、授權範圍、頻率限制與隱私政策。Privacy masking 只是 best-effort risk reduction，不保證完全匿名化，也不保證滿足保密或個資法合規要求；高敏感案件應預設不外送，或採 local-only fallback。

- 外部語意層只提供 candidate recall
- final citation 仍需回到官方來源或 verified cache
- 使用外部服務前應確認合法基礎、當事人同意或保密義務，並檢查 log retention、資料處理契約與外送限制
- 應保留外部服務來源 attribution 與使用限制說明
- 不應將外部服務回傳內容 commit 進公開 repo

## 司法院裁判書資料來源：線上 API 與下載資料集

司法院裁判書資料不應只用一種 ingestion path（匯入路徑）理解。實作 production adapter 時，建議至少區分「線上裁判書開放 API」與「資料集 / 檔案下載 API」兩類來源，兩者用途、同步策略與風險不同。

### 1. 線上裁判書開放 API：增量同步與 JID 回查

線上裁判書開放 API 適合用於定期同步異動、查詢特定 `jid` 的裁判書內容、追蹤更新或移除狀態。依官方規格，API 使用「司法院資料開放平臺」帳號密碼驗證，取得有效時間 6 小時的 token；後續取得異動清單與裁判書內容時需帶入 token。

官方規格重點：

- API 型態：RESTful
- 資料格式：JSON
- 驗證 API：`POST https://data.judicial.gov.tw/jdg/api/Auth`
- 異動清單 API：`POST https://data.judicial.gov.tw/jdg/api/JList`
- 裁判書內容 API：`POST https://data.judicial.gov.tw/jdg/api/JDoc`
- 依官方規格，JList 回傳的是當日往前第 7 日的裁判書異動清單，不是最近 7 日彙總
- 裁判書內容以 `jid` 查詢
- 裁判全文可能是文字，也可能是 PDF 或附件連結
- 依官方規格，本 API 提供服務時間為每日 0 時至 6 時；實作時應以最新官方規格為準
- 若裁判書移除或不再公開，使用者應移除先前取得的內容

Production adapter 應設計 checkpoint、backfill、retry、deletion handling 與 tombstone/removal manifest，避免漏抓異動或漏刪已移除裁判。JList 不應被當成歷史全量建庫來源；它比較適合做異動追蹤與本機資料的新鮮度維護。

### 2. 資料集 / 檔案下載 API：初始建庫與批次回補

司法院資料開放平臺也提供資料集查詢與檔案下載能力；裁判書資料在實務上可能以月份打包檔或資料集檔案形式提供。這類來源適合用於初始建庫、歷史資料 backfill（回補）、可重現研究快照與大批次索引建置。

這類下載流程應和 `Auth` / `JList` / `JDoc` 那組線上裁判書 API 分開實作：

- 不要假設兩者使用相同 endpoint、token 或排程限制
- 應先讀取資料集 metadata（中繼資料）、檔案格式、更新日期、授權與下載條件
- 每次下載應保存 `source_manifest`，至少包含資料集名稱、來源 URL、retrieved_at、license、attribution、checksum 或檔案大小
- 月包或下載檔匯入後，仍應和線上 API 的異動 / 移除狀態 reconciliation（對帳）
- 若官方資料集下架、撤回、標示不可公開或授權條件改變，本機資料應依 policy 降級、移除或停止散布

本 repo 不附司法院 API 帳密、token、裁判書全文、下載檔或快取。若要實作 production adapter，應把 credential 放在環境變數或秘密管理系統，並遵守司法院資料開放平臺的使用規範、服務時間、授權條款與來源標示義務。

官方參考：

- [司法院資料開放平臺](https://opendata.judicial.gov.tw/)
- [司法院資料開放平臺開發指引](https://opendata.judicial.gov.tw/DevelopmentGuide)
- [司法院裁判書開放 API 規格說明](https://opendata.judicial.gov.tw/api/Newses/42/file)

## 快速開始

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]

python examples/build_demo_index.py
python examples/basic_legal_search.py
python examples/validate_citation.py
python examples/trust_pipeline_demo.py
python examples/v02_sync_demo.py

python -m pytest
python scripts/check_no_forbidden_files.py
```

## Demo 流程

`examples/basic_legal_search.py` 示範 synthetic 租賃押金檢索：

```text
query
-> privacy masking
-> normalization
-> synthetic retrieval
-> coverage report
-> citation validation
-> demo-only answer wrapper
```

`examples/trust_pipeline_demo.py` 示範 trust pipeline：

```text
query understanding
-> classifier shadow / overlay
-> stateful coverage
-> synthetic issue brief
-> ranking evaluation
-> trust gate
```

`examples/v02_sync_demo.py` 示範 operational trust checks：

```text
source verification batch
-> authority recall
-> baseline / snapshot / soak checks
-> retriever cache
-> appellate lineage
-> law version timeline
-> exact lookup
```

## Source Trust Policy

| Source tier | 用途 | 可作 final citation |
|---|---|---|
| `official` | 官方來源 | Yes |
| `verified_cache` | 已依官方 URL、hash、驗證時間核對的快取 | Conditional |
| `staging` | 外部或未驗證資料集 | No |
| `external_semantic_recall` | TLR-like 語意召回候選 | No |
| `synthetic` | Demo 與 tests | No, demo-only |
| `unknown` | 無法分類來源 | No |

Candidate-only sources 可以用於召回、排序或人工審查流程，但不能作為 final legal citation。

`verified_cache` 只有在可回溯官方 URL、content hash、驗證時間，且來源未被撤回、移除或標示為不可公開時，才能作為 final citation 候選。

實務導入時應為每一類來源定義 source-specific freshness policy，例如 `verified_at` 最大可接受期限、final citation 前是否必須重新查官方狀態、官方異動清單漏抓時的 backfill 策略，以及 tombstone/removal manifest。Verified cache 是內部驗證機制，不代表可以重新散布官方全文，也不取代官方授權、來源標示或隱私義務。

## Repository Boundaries

本 repo 不包含：

- production legal datasets
- government open-data downloads
- judgment SQLite shards
- law Chroma databases
- vector indexes
- official full-text caches
- TLR response caches
- HF verified full datasets
- real user query logs
- complete proprietary thesauri
- private gold evaluation holdouts
- credentials、tokens、private endpoints 或本機敏感路徑

## 安全檢查

提交或公開前請至少執行：

```bash
python scripts/check_no_forbidden_files.py
```

建議額外執行：

- GitHub secret scanning
- gitleaks
- trufflehog
- manual git history review
- license text review

## 法律聲明

本專案僅用於法律 AI 架構展示與研究，不提供法律意見，不構成法律服務，也不保證任何法律資訊的完整性、正確性、即時性或適用性。

實際法律分析或引用應回到官方來源核對，並諮詢合格法律專業人士。

## English Summary

This is a reference implementation for Taiwan-focused Legal RAG and MCP trust infrastructure. It demonstrates source trust policy, citation verification, privacy masking, stateful coverage, authority recall, and fail-closed answer validation using synthetic demo data only.

It does not provide legal advice and does not include production legal datasets, official full-text caches, user logs, private evaluation sets, credentials, or local sensitive paths.
