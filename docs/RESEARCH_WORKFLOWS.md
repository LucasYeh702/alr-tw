# 快速查案與草稿驗證

> 適用版本：v1.0.0（套件 `1.0.0`）；功能與限制見 [1.0 說明](V1_RELEASE.md)。


這兩條流程共用 MCP 的工具權限、官方查證與答案驗證規則。
命令列只是操作入口，不另行建立證據或授權答案。預設仍為 `synthetic`
合成示範模式；真實研究須明示 `official_only` 或 `hybrid_verified`。

## 快速找類案

```bash
export ALR_TW_DATA_MODE=official_only
alr-tw quick-research --query '請查找定型化契約條款效力的相關裁判' > research.json
```

已有 TLR 設定時可選擇 `hybrid_verified` 提高候選召回；查詢仍須經隱私檢查，
候選仍逐件回官方查證。不要將未公開案情或秘密作為外部搜尋詞。

可用 `--max-judgments 3` 將官方裁判回查預算改為三件，最大五件；
`--max-steps` 為 1–32，預設 12。指定歷史問題時使用 `--as-of-date YYYY-MM-DD`，
歷史版本缺漏不會由現行法規補作歷史證據。

回應重點：

| 欄位 | 如何使用 |
|---|---|
| `data.run_id` | 後續讀取進度、驗證草稿時使用同一編號 |
| `data.state.workflow_guidance` | 繁中進度、缺少項目與下一步；沒有法律答案 |
| `data.state.research_brief` | 已驗證材料定位、研究步驟與阻擋原因 |
| `data.evidence_bundle.items` | 完成流程時提供的有限證據段落；保留每段的 `evidence_id` |
| `data.stop_reason` | 判斷已到起草階段、需要重試或步驟預算用完 |

`ready_for_draft` 不代表完整研究或已授權答案。快速類案研究維持有限範圍的限制。
未取得證據、官方連線失敗與「相關裁判不存在」是不同事情。

```bash
alr-tw research-status --run RUN_ID
```

此命令只讀既有狀態，不發出新的研究查詢或延長保存期限。需要繼續未完成的
同次研究時，由 MCP 呼叫 `continue_legal_research`，使用新的 `operation_id`。

## 驗證已寫好的草稿

先確認草稿的來源已在同次研究中查證。外部查到的資料須透過現有精確法源查詢
或研究計畫提交定位資訊，完成官方驗證，不能把網址直接填成證據。

建立本機 `draft.json`，只包含草稿文字及段落綁定：

```json
{
  "answer_text": "填入待驗證的草稿文字。",
  "claim_bindings": [
    {
      "claim_id": "claim-1",
      "claim_text": "填入草稿中完全相同的核心主張文字。",
      "claim_type": "court_view",
      "importance": "core",
      "evidence_ids": ["填入同次研究提供的真實 evidence_id"]
    }
  ]
}
```

這只是輸入格式範例，佔位文字不能通過正式驗證。法規主張使用 `law_rule`，
裁判主張使用 `court_view`；其他可用類型見既有主張綁定契約。

```bash
alr-tw validate-draft --run RUN_ID --input draft.json
```

每次省略 `--operation-id` 都會產生新編號。明示使用同一編號且操作種類、草稿與綁定內容相同，才代表重播先前操作；內容不同會回 `OPERATION_REQUEST_MISMATCH`，
修正草稿後應使用新編號。研究與驗證必須使用相同的保存位置；若指定
`--storage-path`，每次命令都使用同一路徑。

| 結果 | 呈現規則 |
|---|---|
| `validated` | 草稿通過既定檢查，仍須複核法律推理與個案適用 |
| `qualified` | 只能併同 `required_qualification` 的限制呈現 |
| `blocked` | `answer_text` 為空，不展示草稿；依 `workflow_guidance` 補正 |

拒答時可展示進度與補救說明。`workflow_guidance.answer_authorized` 永遠為
`false`，因為說明本身不是法律答案，也不能取代驗證回應的 `safe_to_present`。

命令退出碼：`0` 代表操作成功（快速查詢仍可能尚未取得足夠材料）；
`validate-draft` 的 `1` 代表草稿未通過；`2` 代表輸入或操作錯誤。
輸入檔上限 1 MiB，不接受額外的 evidence、source 或 trust 欄位。
無效輸入只回固定錯誤代碼，不把草稿內容帶入格式錯誤訊息。

## 已驗證範圍

整合測試覆蓋透過命令列進行查證、讀取狀態、段落綁定草稿通過與未綁定草稿拒答。
測試的法規及官方回應是合成資料，驗證的是程式行為，不是法律答案正確率。
研究品質與人工複核工時應另依 [研究任務評測](RESEARCH_TASK_EVALUATION.md) 採集。

## 中斷與儲存位置

同一研究的受管操作不允許重疊執行。可攔截的例外會將本次取得的操作標為失敗，
讀取進度並排除原因後可用新編號重試；失敗編號回 `OPERATION_FAILED`。
程序遭強制終止或儲存無法存取時，可能留下未完成紀錄。`OPERATION_IN_PROGRESS` 表示仍有執行中或
中斷後未完成的操作，不能當作成功。先確認原程序是否仍在執行；確定中斷時，
以原問題與原法律適用日期重新建立研究，重新查證，不重用舊答案授權。
不再需要的舊研究可用既有 purge 命令移除。此版不提供自動接管執行中的工作。

新版本會為操作紀錄補上請求摘要欄位；舊紀錄無摘要時不能證明是同一請求，
改用新的操作編號。摘要不保存草稿正文，但既有結果的保存政策仍適用。

儲存目錄與資料庫須為本人擁有的實體目錄／一般檔案，不接受符號連結、
資料庫硬連結或異常附屬檔案。路徑遭替換時停止操作。此防護目前要求 POSIX
的安全開檔能力；不支援的平台明確拒絕，不靜默降級。它不是隔離惡意同帳號
程序的沙箱，也不承諾抵抗在每次檢查間快速替換再還原路徑的攻擊。

## 草稿修訂與本機資料包

先取得同次研究證據，再用 `review-draft` 檢視內部草稿；`complete-research` 接續研究並嚴格驗證。修訂稿使用新的操作編號，舊結果保持不變。資料包匯入、啟用與顧問接線見 [1.0 操作與限制](V1_RELEASE.md)。

## 0.14 引用定位與起草規則

先取得能力協商的 `workflow_guidance.drafting`；研究完成會附同一版本規則。
`review-draft` 回傳 `citation_preparation` 的草稿摘要、原位置、候選位置與原因。
核對摘要後更新原 `claim_bindings` 中對應引用，重新預檢，再以新操作編號完整驗證。
預檢不自動套用修正，不授權答案；查無、歧義、跨子句及錯誤來源須修稿。
詳見 [1.0 操作與限制](V1_RELEASE.md) 與 [公開面盤點](V1_RELEASE.md)。
