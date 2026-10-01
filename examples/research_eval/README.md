# ALR-TW research-task evaluation smoke

此目錄只放公開安全的 smoke fixture（合成回覆與合成評核），不代表專家已審閱，
也不代表模型品質、法律正確率或 production readiness。36 題任務 manifest 由
`alr_tw.evaluation.research_tasks` 內建，因而安裝 wheel 後不依賴 repository 路徑。
`diagonal_pilot_tasks.json` 固定列出六域各一題的 bounded pilot 選擇；它仍是
`authored_unreviewed`，不包含任何模型輸出或專家分數。

先輸出不含 gold answer 的 agent inputs：

```bash
python -m alr_tw.evaluation.research_tasks \
  export-agent-inputs \
  --output /tmp/alr-tw-research-agent-inputs.jsonl
```

實際 runner 應以每題輸入建立兩筆 `research-eval-run/v1`：相同 manifest hash、題目
question hash、model identity 與 `model_config`；兩列使用不同 `run_id` 和各自的
實際 output，只將 `harness_mode` 分別設為 `with_harness` 或 `without_harness`。
runner 的回覆不可自行加入 expert review
或把模型自報資料當成 provenance。

收集後先做 schema、manifest、題目與 slot 檢查：

```bash
python -m alr_tw.evaluation.research_tasks \
  validate-runs \
  --runs /path/to/runs.jsonl
```

產生專家評核模板。模板預設是 `unverified`／`unreviewed`，填入數值不會自動變成
已確認評核；只有外部匯入且明示人類確認的 review 才會進入分數：

```bash
python -m alr_tw.evaluation.research_tasks \
  export-review-template \
  --runs /path/to/runs.jsonl \
  --output /tmp/alr-tw-research-reviews.jsonl
```

專家或評核主持人完成審閱後，應保留 `provenance`、人類確認狀態及五項欄位：
`citation_errors`、`material_omissions`、`false_accepts`、`false_refusals`、
`review_time_seconds`。欄位內容是宣告性 metadata，不是身份認證。最後執行：

```bash
python -m alr_tw.evaluation.research_tasks \
  score \
  --runs /path/to/runs.jsonl \
  --reviews /path/to/reviews.jsonl \
  --output /tmp/alr-tw-research-report.json
```

本目錄的 smoke fixture 可離線檢查流程：

```bash
python -m alr_tw.evaluation.research_tasks validate-runs \
  --runs examples/research_eval/smoke_runs.jsonl
python -m alr_tw.evaluation.research_tasks score \
  --runs examples/research_eval/smoke_runs.jsonl \
  --reviews examples/research_eval/smoke_reviews.jsonl \
  --output /tmp/alr-tw-research-smoke-report.json
```

fixture 只涵蓋前兩題和合成資料。報告中的 denominator、missing、unreviewed、
metric missing、coverage 與 paired coverage 必須一併讀取；沒有輸入資料時相應
指標是 `null`，不能解讀成零錯誤。模型身份或設定不一致的兩筆記錄會留下
non-paired rejection，不能拿來做公平比較。
