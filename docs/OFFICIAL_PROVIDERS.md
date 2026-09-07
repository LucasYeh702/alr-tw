# Official Providers

ALR-TW v0.12.0 以三個獨立 provider 取得台灣中央法規、普通法院裁判與憲法法庭資料。官方即時內容通過結構、一致性與 freshness 檢查後，會固定成 server-owned evidence；呼叫端不能自行宣告某段文字為官方資料。內建 `ResearchService` 會依同一 run 中通過官方／可信快取閘門的精確 source／evidence 集合簽發並持久化 provider-neutral snapshot receipt，finalization 再從 server-owned store 重算 binding。receipt 與其他閘門均通過時 `ordinary` 才可達；缺失最高為 `conditional`，跨 run、過期或集合不符則 fail closed。

v0.12.0 也提供行政規則、行政解釋、訴願與立法資料的 provider-neutral
contracts／SDK。TLR adapter 可召回行政函釋候選，但不建立 source 或 evidence；
本 repo 仍不內附行政函釋官方 provider、corpus 或 index。部署者可用
`PublicLawProviderAdapter` 接入官方來源；所有升格結果仍須由 server metadata
binding 與既有 evidence／finalization gates 驗證。

立法院是例外的 locator-only connector：`lookup_legislative_history` 可在 live
data mode 明示呼叫 ID20、ID19、ID46、ID8 與 ID48 的官方 targeted JSON API，
但只回 candidate。它不下載 linked PDF／DOC、不產生 normative source，也不證明
正式公布版本；資料集缺少可驗證日期或唯一關聯時固定維持 partial／qualified。
ID46 沒有可直接用法規名稱穩定比對的欄位，因此委員會議案 locator 需要 caller
提供 `bill_no`，或先由同次 ID20 提案結果建立議案編號關聯；ID20 無法建立關聯時
不會猜測委員會議案。
官方 host 目前需要 OpenSSL 的 client-only legacy-server-connect 相容旗標；實作只
對固定 `data.ly.gov.tw` origin 建立該 TLS context，保留 CA／hostname 驗證並禁止
handshake 後 renegotiation。無法安全建立連線時會 fail closed。

## 法務部法規 Provider

- 來源：全國法規資料庫官方結構化資料與官方網頁；
- 能力：法規名稱、基本關鍵詞、精確條文、現行／廢止狀態；
- 結構化內容與官方網頁內容衝突時，來源降為 `verification_failed`，不得作正式證據；
- v0.12.0 不承諾指定歷史日期的完整版本、地方自治法規或所有附件解析。

## 司法院普通裁判 Provider

- 接受完整 JID、司法院官方全文網址，或包含法院、年度、字別、號次及可選民／刑事類別的正式裁判字號；TLR 提供的五段 doc ID 只能作官方解析輸入。官方頁若提供六段 canonical JID，前五段必須完全一致；舊頁若只明示相同五段 ID，則以 `legacy_five_part_jid` 保留並升格，不猜補版本尾碼；
- 正式字號透過 `qryresult.aspx` 精確查詢，解析結果頁的官方 JID，再直接讀取 `data.aspx` 全文；
- 關鍵詞查詢先取得進階搜尋表單及 ASP.NET 隱藏狀態，再以同一短期連線送出查詢並解析第一頁候選；
- 同一字號可能同時存在民事與刑事裁判。未提供類別且結果不唯一時會回 `AMBIGUOUS_FORMAL_CITATION`，不猜測；
- 六段請求若官方頁只能提供相符的五段標記，會回 `LEGACY_JUDGMENT_IDENTIFIER_AMBIGUOUS`；五段請求若頁面沒有可核對標記，會回 `LEGACY_JUDGMENT_IDENTIFIER_UNRESOLVED`；
- 普通裁判網站路徑不使用 JDoc API，也不需要司法院 API token；
- 官方回覆已移除或不公開時，結果帶有 `removal_required=true`，先前管理範圍內的內容應刪除；
- 主文、法院理由與可辨識的當事人主張分開。當事人主張不可被當成法院見解。

效能設計採單次操作內的連線與 cookie 重用、正式字號跨系統一次查詢、候選數量上限，以及 server-owned TTL 快取。連線結束即釋放 session，不保存搜尋 cookie。若遇到 WAF、驗證碼或拒絕頁面，會回 `OFFICIAL_SOURCE_BLOCKED` 並 fail closed；本版不內建規避機制或無限重試。

`hybrid_verified` quick judgment research 先呼叫 TLR／相容 candidate provider；
只有無可用候選或 provider 失敗才退回官方關鍵詞搜尋，並將排序後的 exact
verification 限制為 1–5 件。候選來源及 excerpt 不影響信任等級；每個入選
candidate 都須逐件通過上述 identity 與正文解析。類案 quick 固定保留 bounded
top-K qualification；mismatch／not-found 另加限制且不會進入 evidence，`0` 件成功
仍無法起草。

Counter-authority 不會把整段長自然語言問題原樣送入司法院搜尋。Server 會產生最多
四個 deterministic 短查詢，保留明示法條與爭點詞並加入「相反見解」／「不同見解」
標記；每個 query 最長 128 字。縮短只處理 lexical retrieval，不執行 semantic
opposition classification。

## 可選唯讀本機裁判 Provider

在明示的 live data mode 下，可用 `ALR_TW_LOCAL_PORTAL_ROOT` 指定絕對資料根目錄，
接入部署環境既有、相容的唯讀 `legal_data_pipeline` provider；套件不內附資料。
本機搜尋只回傳候選。精確查詢會檢查 catalog-bound receipt、coverage binding、
來源狀態與 trusted-text／provenance hash；全部符合時才由 server 採納並投影為
`verified_cache` 記錄。candidate-only 快取不會升格；任一條件不符時，以
canonical JID／正式字號回查官方來源。
資料不可用與查無結果保持分離，候選片段不會直接成為 evidence。

此設定不會在 `synthetic` mode 載入本機資料。部署者應自行治理所接入的 provider
與 catalog；既有 evidence、時點、角色、claim binding 及答案驗證規則仍適用。

## 憲法法庭 Provider

- 支援釋字、憲判字、憲裁字、憲暫裁字與審裁字的正規化；
- 索引判決、實體裁定與舊制解釋，提供精確查詢及基本關鍵詞搜尋；
- 主文／解釋文、法院理由、協同意見與不同意見分開；
- 個別大法官意見不得冒充法庭多數意見；
- 官網未提供可解析正文的程序裁定或附件，會以不完整／不可用狀態呈現，不臆造文字。

## 共通安全規則

- 僅允許 HTTPS allowlist（允許清單）主機，redirect 也重新驗證；
- 官方 HTTPS 預設以 `truststore` 使用作業系統憑證庫；`alr-tw doctor --live` 會實際
  探測三個官方 provider，並以 `LIVE_TRUSTSTORE_REQUIRED` 或
  `OFFICIAL_TLS_VERIFICATION_FAILED` 明示部署問題；
- 有明確 timeout、回應大小上限與 schema guard；
- 網路失敗不等於查無資料；
- 每個 source 保存官方識別碼、網址、內容 hash、取得與驗證時間、到期時間；
- 到期或驗證衝突的 evidence 不可支援 final answer；
- `as_of_date`／修法前查詢在本版無法完整支援時會 fail closed。
