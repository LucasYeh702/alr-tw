# Architecture

ALR-TW v0.6.0 將「agent 決定下一步」與「server 決定何者可信」分開。外部 agent 可以提出查詢、逐步呼叫工具並起草答案，但不能注入正式證據或跳過 obligations。

```text
MCP client / external agent
        |
        v
ResearchService
  - ResearchRun state machine
  - ordered obligations
  - idempotent operations
  - final validation
        |
        v
ProviderObligationExecutor
  +--------------------+----------------------+-------------------+
  | OfficialLaw        | OfficialJudgment     | Constitutional    |
  | MOJ JSON + webpage | formal citation/JID  | decisions/rulings |
  +--------------------+----------------------+-------------------+
                            ^
                            |
                  TLR candidate-only recall
                  (hybrid_verified + privacy gate)
        |
        v
SqliteStore
  - runs / obligations / operations
  - source records / evidence spans
  - retrieval candidates / TTL cache
        |
        v
validated | qualified | blocked
```

## Civil-law model

- 法規是主要規範來源，必須保留名稱、條號、現行／廢止與時間限制；
- 普通裁判不是一律等同拘束先例，需保留法院、日期、案號、主文、法院理由與當事人主張角色；
- 憲法法庭主文／理由、協同意見、不同意見分開；
- `as_of_date` 無法完成歷史版本核對時，不用現行條文假裝回答歷史問題；
- counter-authority coverage 不足必須揭露。

## Trust boundaries

1. Caller boundary：caller arguments、answer text 與 source-tier metadata 均不可信。
2. External recall boundary：TLR 只產生 candidate，查詢先經本地 privacy gate。
3. Official boundary：HTTPS allowlist、timeout、size/schema checks、內容 snapshot 與 expiry。
4. Storage boundary：只有 server-owned source/evidence 能進 final validation；秘密不持久化。
5. Presentation boundary：只有 `validated` 或 `qualified` 可回 answer body；`blocked` 必須移除。

## Compatibility

`alr_tw.*` 是 v0.6 中立 contracts、providers、research 與 storage 的主命名空間。`tw_legal_rag_mcp.*` 保留舊 synthetic／trace 工具並承載 MCP stdio server。兩者共用 source tier 與 fail-closed invariants；新功能不得反向依賴 client-controlled provenance。

## Operational limits

本 repo 不包含 production corpus、永久官方快取、向量 shard、LLM、私有 ranking 參數或使用者資料。Live providers 是有界即時查詢，不保證外部服務可用或全域完整召回。
