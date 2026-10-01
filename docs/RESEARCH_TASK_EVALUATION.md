# 公開安全研究任務評測

> 適用版本：v1.0.0（套件 `1.0.0`）；功能與限制見 [1.0 說明](V1_RELEASE.md)。


`alr_tw.evaluation.research_tasks` 提供一組可離線執行的研究任務評測收據流程。
內建 manifest 是 36 題、六個法律領域各六題，包含：

- 精確法條／官方來源核對
- 有界快速類案查找
- 帶有合成草稿與標記主張的草稿核查
- 明示 `YYYY-MM-DD` 的歷史時點版本核對
- 指定法律問題的反方、限制或不同事實前提材料
- 帶有合成主張、抗辯、理由、主文段落的角色限制核查

題目只描述公開安全的研究輸入與評核面向，頂層及每題都標為
`authored_unreviewed`。題目不含標準答案、專家答案、真實評測分數、私人資料或
預填模型答案。這個狀態是任務作者狀態，不是專家審閱結論。

內建 manifest 直接存在 Python package 的模組常數中。安裝 wheel 後執行預設命令
不會從 repository 路徑讀題目；若使用外部 manifest，必須明示 `--tasks` 路徑。
manifest hash 是對 canonical JSON（排除自帶 hash 欄位）計算的 SHA-256，會綁定
每次 run 和 review。

## 1. 匯出 gold-free inputs

```bash
python -m alr_tw.evaluation.research_tasks manifest
python -m alr_tw.evaluation.research_tasks \
  export-agent-inputs \
  --output /tmp/alr-tw-research-agent-inputs.jsonl
```

每列輸入只有 manifest identity、題目 identity、領域、任務型態、具體繁中 prompt
與執行限制。`answer`、`gold_*`、專家評核、模型答案等欄位都不在 schema 中，
extra 欄位也會被拒絕。上游 runner 應將兩個 mode 使用同一份輸入，不能在 prompt
或 manifest hash 上自行變更。

`constraints` 也使用限定欄位與型別：公開安全／官方驗證／範圍限制等布林控制、
任務標籤、1–20 件候選預算及可選 ISO 日期。未知或巢狀評核欄位不得透過這個
字典夾帶到模型輸入。這是結構隔離；題目文字本身仍須由作者與專家檢查，
不宣稱能自動識別藏在自然語言裡的答案。

這些 `constraints` 是評測執行限制，不是 MCP 工具的輸入契約，不可整個複製
到 `execute_legal_research`。接 MCP 的 runner 應先讀取 `tools/list` 所回傳的
`inputSchema`，再明示映射支援的欄位。`validate_legal_answer` 使用
`answer_text`，不是 `answer` 或 `draft_text`；必須帶同次研究的 `run_id`、
新的 `operation_id` 及真實證據綁定。亦可使用
[已接線的命令列流程](RESEARCH_WORKFLOWS.md)。格式錯誤與重試仍須計入試測
工具預算，不能事後移除失敗呼叫再宣稱成效。

## 2. 採集兩個 mode

runner 不由本模組執行。對每個 task 建立最多兩個 `research-eval-run/v1` JSONL
紀錄：

```json
{
  "schema_version": "alr-tw.research-eval-run/v1",
  "run_id": "run-RT-01-01-with",
  "manifest_hash": "<manifest sha256>",
  "task_id": "RT-01-01",
  "question_hash": "<prompt sha256>",
  "model_identity": "<pinned model identity>",
  "model_config": {"temperature": 0, "seed": 7},
  "harness_mode": "with_harness",
  "run_status": "completed",
  "response_text": "<runner output>"
}
```

另一列應使用獨立的 `run_id` 和實際 runner output，並將 `harness_mode` 設為
`without_harness`；model identity、完整 `model_config`、manifest hash 與
question hash 必須相同。`run_digest` 可由 runner 一併保存；若提供，模組會驗證
它等於所有評測內容的 canonical digest。digest 會
包含 response、mode、模型 identity、設定、題目與 run ID，因此同一 run ID 替換
答案後，舊 review 不能繼續套用。

```bash
python -m alr_tw.evaluation.research_tasks \
  validate-runs \
  --runs /absolute/path/runs.jsonl
```

schema 與 scope 驗證會拒絕未知題目、題目 hash 不符、manifest hash 不符、重複
run ID、同一 task/mode 重複、非有限數字和其他 extra 欄位。缺少的 slot 不會被
補成一筆零錯誤資料。

`run_status` 可為 `completed`、`failed` 或 `canceled`。失敗或取消的採集會在
report 中統計，但不會進入 completed paired comparison，也不能被當成完成路徑的
準確率。

## 3. 匯入外部專家評核

先產生模板：

```bash
python -m alr_tw.evaluation.research_tasks \
  export-review-template \
  --runs /absolute/path/runs.jsonl \
  --output /tmp/alr-tw-research-reviews.jsonl
```

模板的 provenance 預設為 `unverified`／`unreviewed`，所有五項評核值都是缺省。
完成外部評核後，每列應提供：

- `citation_errors`：引用錯誤數
- `material_omissions`：重要遺漏數
- `false_accepts`：不應放行卻放行的數量
- `false_refusals`：有足夠支持卻錯誤拒答的數量
- `review_time_seconds`：人工複核時間

並保留與 run 完全相符的 `manifest_hash`、`task_id`、`run_id`、`run_digest` 和
`harness_mode`。`provenance.provenance_status`、`human_confirmation`、
`source_ref`、`reviewer_label` 是匯入聲明 metadata；它們不是身份認證或簽章。
只有 `external_imported`、`confirmed` 且 `source_ref` 與 `reviewer_label` 都非空
時，review 才進入已審閱 population。人類確認未完成、來源或 reviewer label
缺少時一律保持 `unreviewed`，即使 JSON 填了數字也不能計分。

整數指標必須是非負的 strict integer，不能用 `true` 或字串冒充數字；複核時間
必須是有限、非負數。負數、NaN、Infinity、重複 review、未知 run、run digest
不符或 case/mode 不符都 fail closed。

## 4. 評分與公平配對

```bash
python -m alr_tw.evaluation.research_tasks \
  score \
  --runs /absolute/path/runs.jsonl \
  --reviews /absolute/path/reviews.jsonl \
  --output /absolute/path/report.json
```

paired comparison 只使用同一 task、同一 manifest hash、同一 question hash、同一
model identity、同一完整 model config，且兩筆 run 都是 `completed` 的配對。模型
身份或設定不一致會留下 `model_identity_mismatch` 或 `model_config_mismatch`，
不會以 task ID 強行配對。

report 對每個 harness mode 和每項指標都明示：

- `denominator`：該 mode 的 manifest 題數
- `run_present`、`review_present`、`review_missing`
- `unreviewed`：沒有通過外部／人類確認條件的 review
- `metric_missing`：已確認 review 但該欄位沒有值
- `scorable` 與 `coverage`
- 已有值時的 `value_sum`、`mean_value`，錯誤指標另有非零比例

paired metrics 另以成對題數為 denominator，列出雙方可比較數量、缺資料或未審閱
數量、coverage，以及 `without_harness - with_harness` 的平均差。任何 population
沒有可評分值時，value、mean、delta 保持 `null`；`0` 只表示已確認且確實記錄
為零，不表示缺資料或未審閱。

這套報告能量測引用錯誤、重要遺漏、錯誤放行、錯誤拒答和複核時間的資料覆蓋，
但不自行判斷法律答案是否正確，也不執行模型、外部 API 或付費評測。內建題目仍
是 `authored_unreviewed`，專家標註、runner 完整執行、模型身份 pin、真實樣本
coverage 與任何成效結論都必須由主流程另外提供證據。`examples/research_eval/`
內的 runs/reviews 是合成 smoke fixture，只驗證 schema、hash、配對及報表流程，
不能當成專家已審閱資料或研究成效。
