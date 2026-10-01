# Public / Private Traceability

> 適用版本：v1.0.0（套件 `1.0.0`）；功能與限制見 [1.0 說明](V1_RELEASE.md)。


| Local capability | Public counterpart | Public status | Exclusion reason |
|---|---|---|---|
| Law Chroma | synthetic law fixture + adapter schema | partial | production DB excluded |
| Judgment SQLite shards | synthetic judgment fixture + trace schema | schema only | index excluded |
| TLR local verification | candidate-only policy + mock traces | policy only | service/index excluded |
| Citation validation | public validator | full | safe to publish |
| Trust gate | public trust gate | full | safe to publish |
| User/private matter workflows | none | excluded | private data excluded |

