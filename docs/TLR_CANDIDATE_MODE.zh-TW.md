# TLR 候選模式

語言：[English](TLR_CANDIDATE_MODE.md) | 繁體中文

本公開 repo 將 TLR-like（類 TLR）或外部語意召回資料視為有用的候選探索來源，而不是 final citation authority（最終引用權威來源）。

## 規則

外部語意召回可以協助找到可能相關的法律資料，但它不是 final citation authority（最終引用權威來源）。在 ALR-TW 中，它會以 `source_tier: "external_semantic_recall"` 與 `citation_use: "allow_candidate_only"` 進入 trace（追蹤紀錄）。

TLR 可以被建議作為高 recall（高召回率）的資料源，用來尋找候選裁判與相關線索。但建議的 verification cache（驗證快取）仍應由司法院或其他官方來源下載的原始檔建立。

## 官方存取前提

本 repo 不提供司法院 API credential（憑證）、access approval（存取核准），也不提供已下載的官方資料。Operator（部署或維運者）必須自行取得司法院官方 access（存取權限），或以其他合法方式下載公開原始檔後，才能建立本地 verification cache（驗證快取）。

## 若已接上 TLR，為何仍要下載官方資料？

TLR 降低 discovery（探索）成本，但不取代本地 authority layer（權威驗證層）。在這個分支中，TLR 用來快速找出候選裁判；但 final citation gate（最終引用閘門）仍依賴官方來源或本地已驗證紀錄。

當 operator（部署或維運者）需要下列能力時，仍必須下載司法院原始檔：

- final citation eligibility（最終引用資格），而不是只能作為 candidate-only recall（僅候選召回）
- 對實際作為證據的原始紀錄計算本地 content hash（內容雜湊）
- 將結果綁定到已知本地資料快照，確保可重現
- 對敏感後續驗證與審查維持本地操作
- 在外部 recall service（召回服務）不可用或 ranking（排序）改變時仍可驗證

若沒有本地官方資料快取，TLR 命中仍只是 `external_semantic_recall`，不能滿足 final-citation requirements（最終引用要求）。

## 升級要求

候選資料只有在獨立 verifier（驗證器）將其映射回下列來源後，才能支援最終答案：

- `official` source（官方來源）；或
- 具有官方 URL、content hash（內容雜湊）與 verification time（驗證時間）的 `verified_cache` 紀錄。

對 TLR-style（TLR 類型）裁判候選資料，最小 raw-backed（原始檔支撐）升級流程是：

1. 將 TLR 結果視為 `external_semantic_recall`。
2. 擷取穩定裁判識別碼，例如 JID。
3. 用該識別碼對照 operator（部署或維運者）透過自有官方 access（存取權限）下載的司法院裁判月檔原始資料。
4. 從匹配到的原始紀錄計算 content hash（內容雜湊），例如 raw JSONL line（原始 JSONL 行）或其他已文件化的 canonical source representation（標準化來源表示）。
5. 只將本地匹配成功的紀錄升級為 `verified_cache`；未匹配的 TLR 候選資料仍保持 candidate-only（僅候選）。

在 ALR-TW 程式碼中，這條識別碼支撐路徑是 opt-in capability（選擇性啟用能力，環境變數 `ALR_TW_IDENTIFIER_BACKED_VERIFIED_CACHE`，預設關閉），僅適用於裁判類紀錄，並由 resolver（解析驗證器）強制執行：識別碼必須解析到本地保存的官方原始紀錄，且重算的 content hash（內容雜湊）與宣告的 hash 相符。單靠識別碼加上自行宣告的 hash 永遠不足；識別碼無法解析或 hash 不符時一律 fail closed（保守拒答）。這份 recipe 降低裁判驗證的導入摩擦，但不是開箱即用：operator（部署或維運者）仍須自行取得官方 access 並下載原始檔。

本地 `verified_cache` 至少應保存：

- 官方來源 URL 或穩定官方識別碼
- 從已下載官方原始檔計算出的 content hash（內容雜湊）
- `retrieved_at` 或等價下載時間戳
- verifier（驗證器）確認 cache record（快取紀錄）後的 `verified_at` 時間戳
- 可區分官方原始檔快取與語意召回的 source label（來源標籤）

在完成上述要求前，trust gate（信任閘門）必須將它視為 candidate-only（僅候選），且在沒有其他 final citation（最終引用）時 fail closed（保守拒答）。

## 公開邊界

本 repo 不包含 production TLR data（正式 TLR 資料）、private recall indexes（私有召回索引）、ranking parameters（排序參數）、user queries（使用者查詢）或真實法律全文。內建 examples（範例）僅使用 synthetic records（合成資料）。
