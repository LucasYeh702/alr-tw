# ChronoLex-TW adapter

ALR-TW 提供一個 public-safe、離線、資料集版本固定的 ChronoLex-TW adapter。它不內附
501 題資料、不自動下載 Hugging Face 檔案，也不把模型自稱的版本日期當成歷史法規證據。

## 固定資料版本

- dataset：[`lianghsun/chronolex-tw`](https://huggingface.co/datasets/lianghsun/chronolex-tw)
- config／split：`default`／`test`
- revision：`2c9e5e280579209522a23acef7fdeb4b4b61ce94`
- rows：501
- strata：158 `Shifted`、343 `Stable`

本 revision 有 501 列，但原始 `id` 只有 465 個唯一值：35 組 `id` 重複，且最多三列共用
一個 `id`。adapter 不會用原始 `id` 直接 join；它使用不含 answer、gold 欄位及
`question_unmasked` 的穩定 row fingerprint，建立 `<id>#<fingerprint>` 形式的唯一
`case_key`。因此 subset 或重新排序不會改變題目 identity。

## 準備 gold-free agent 輸入

先另行取得 pinned `chronolex_tw.csv`，再執行：

```bash
alr-tw-chronolex prepare --dataset /absolute/path/chronolex_tw.csv > agent-inputs.jsonl
```

輸出只包含 `case_key`、masked `question`、A–D、`legal_date` 與資料集 identity。
`answer`、`gold_law`、`gold_article`、`gold_version_date`、`tau`、
`question_unmasked` 與其他 evaluator-only 欄位不會送給 agent。

Agent 每題回傳一列 JSONL：

```json
{
  "schema_version": "alr-tw.chronolex-agent-run/v1",
  "case_key": "CLTW-2012-criminal-41#<gold-free-fingerprint>",
  "tool_calls": [
    {
      "tool_name": "historical_law_lookup",
      "law_name": "刑法",
      "article": "第122條",
      "as_of_date": "2012-08-01",
      "lookup_status": "found"
    }
  ],
  "final_answer": "D",
  "terminated": true
}
```

## 三項主要指標

### `historical_article_hit`

Trajectory-level 指標。只在同一次 tool call 同時符合 gold 法規、gold 條號與原始
`legal_date` 時命中；使用今天日期不算命中。`刑法` 與 `中華民國刑法` 視為同一法規，
`第185條之3` 與 `185-3` 會正規化為相同條號。

### `version_correctness`

版本日期不能由模型自行認證。它必須來自獨立的
`alr-tw.chronolex-adjudication/v1` server stream，並同時滿足：

1. `HistoricalLawValidationResult.decision == accepted`；
2. source 是被接受的 `HISTORICAL_STATUTE`／`NORMATIVE_RULE`；
3. `ApplicabilityValidationResult.decision == accepted` 且 source 被選為指定時點版本；
4. adjudication 綁定實際 trajectory call；
5. server source 的 promulgation date 等於 `gold_version_date`。

缺少 provider、來源或任一驗證時，結果是 `not_scoreable`，不是猜測的 true／false。
彙總同時回報：

- `score`：correct／全部題目；
- `scorable_accuracy`：correct／可評分題目；
- `coverage`：可評分題目／全部題目。

因此歷史 provider 全數 unavailable 時，`score` 為 0、`coverage` 為 0，且
`scorable_accuracy` 為 `null`；不能宣稱版本正確率已被測出。

### `final_answer_correctness`

只有 run 已終止且 A／B／C／D 與官方答案相同才算正確。它和前兩項分開計算；答對選項
不會掩蓋條文或版本錯誤。

## 評分

```bash
alr-tw-chronolex score \
  --dataset /absolute/path/chronolex_tw.csv \
  --runs /absolute/path/agent-runs.jsonl \
  --adjudications /absolute/path/server-adjudications.jsonl
```

若尚無 server adjudication stream，可省略 `--adjudications`；所有
`version_correctness` 會維持 `not_scoreable`。報告分別提供整體、`Shifted`、`Stable`
三組彙總，並保留每題 reason code（原因碼）。

`--adjudications` 必須由評測端從 ALR server result（伺服器結果）另行產生，並放在
agent 不可寫入的位置。JSON schema（資料格式）驗證只檢查結構，不能把 agent 自行產生的
檔案變成可信的 server evidence（伺服器證據）。

## 邊界

- `legal_date` 是每年 8 月 1 日代理值；靠近修法邊界的題目不能作精確日期黃金真值。
- gold article 是出題者原始引用條文，不代表唯一可能的答題路徑。
- 公開考古題可能已進入模型訓練資料；答案正確率不得單獨解讀為歷史檢索能力。
- adapter 是評測與治理層，不等於 ALR-TW 已內附完整歷史法規 corpus 或 production provider。
