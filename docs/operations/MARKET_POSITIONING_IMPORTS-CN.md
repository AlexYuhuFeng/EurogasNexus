# 甯傚満鎸佷粨瑙傚療瀵煎叆

## 鐩殑

Eurogas Nexus V1 鍙互鍦ㄤ氦鏄撳憳椹鹃┒鑸变腑灞曠ず澶栭儴灞忓箷璁㈠崟瑙傚療鍜屾寚绀烘€х粍鍚?
PnL 蹇収銆俁19 澧炲姞浜嗗彈娌荤悊鐨勫唴閮ㄥ鍏ヨ矾寰勶紝鐢ㄤ簬鎶婅繖浜涜瀵熻褰曞啓鍏?
PostgreSQL銆俁21 鍦ㄨ璺緞鍓嶅鍔犲唴閮ㄦ搷浣滃憳 token 鍜屾樉寮?principal 鏍￠獙銆?

杩欎笉鏄笅鍗曘€佽鍗曡矾鐢便€佷氦鏄撴崟鑾枫€佺粨绠椼€佷細璁°€佹彁鍚嶆垨鑷姩浜ゆ槗銆傚鍏ヨ褰曞彧鏄?
澶栭儴绯荤粺鐘舵€佺殑鍙鍐崇瓥鏀寔瑙傚療銆?

## 璺敱

浠呭唴閮?profile 鏆撮湶锛?

```text
POST /api/internal/portfolio/import-observations
```

蹇呴渶璇锋眰澶达細

```text
X-Eurogas-Internal-Token: <鐢辨搷浣滃憳绠＄悊鐨?token>
X-Eurogas-Principal: <鎿嶄綔鍛樻垨鍚庣浠诲姟鏍囪瘑>
```

鍚庣杩愯鐜蹇呴』閰嶇疆 `EUROGAS_NEXUS_INTERNAL_API_TOKEN`銆傚鏋滅幆澧冨彉閲忔湭閰嶇疆銆?
璇锋眰鏈甫 token銆乼oken 涓嶅尮閰嶏紝鎴?`X-Eurogas-Principal` 涓虹┖锛岃矾鐢变細鍦ㄨ闂?
鏁版嵁搴撳墠澶辫触鍏抽棴銆傝繖鏄?V1 鍐呴儴鎿嶄綔鍛?token 闂ㄧ锛屼笉鏄叕鍙?SSO/OIDC銆倀oken
涓嶅緱琚棩蹇楁墦鍗般€丄PI 杩斿洖銆佹彁浜ゅ埌浠撳簱锛屾垨淇濆瓨鍦?Web銆乄indows銆丼DK銆丆LI 瀹㈡埛绔€?

姝ｅ紡瀹㈡埛绔户缁鍙栵細

```text
GET /api/portfolio/screen-orders
GET /api/portfolio/pnl-snapshots
GET /api/portfolio/live-summary
```

## 鏉冮檺瑕佹眰

瀵煎叆璺敱榛樿澶辫触鍏抽棴銆傚鍏ュ墠锛孭ostgreSQL 蹇呴』瀛樺湪宸叉巿鏉冪殑
`entitlement_decisions` 璁板綍锛岃鐩栨瘡涓€涓潵婧愬拰鏁版嵁闆嗙粍鍚堬細

| 瑙傚療绫诲瀷 | 鏁版嵁闆?|
| --- | --- |
| 灞忓箷璁㈠崟 | `screen-orders` |
| 缁勫悎 PnL 蹇収 | `portfolio-pnl` |

绀轰緥鎺堟潈缁勫悎锛?

```text
ICE_OCM / screen-orders
INTERNAL_PNL / portfolio-pnl
```

濡傛灉鎺堟潈缂哄け锛屾暣涓壒娆′細琚嫆缁濓紝涓嶅啓鍏ヤ换浣曡瀵熻褰曘€?

## 瀹¤鍜岃繍琛岃褰?

姣忎竴涓垚鍔熸垨鎷掔粷鐨勬壒娆￠兘浼氬啓鍏ワ細

- 涓€鏉?`ingestion_runs`锛?
- 涓€鏉?`audit_events`銆?

鎷掔粷鎵规璁板綍 `status=failed` 鍜?`outcome=denied`銆傛垚鍔熸壒娆¤褰?
`status=succeeded` 鍜?`outcome=succeeded`銆?

## Payload 瑙勫垯

姣忎釜鎵规蹇呴』鍖呭惈锛?

- `batch_id`
- `source_reference`
- `screen_orders`
- `pnl_snapshots`
- `research_only=true`
- `human_review_required=true`

灞忓箷璁㈠崟瑙傚療蹇呴』鍖呭惈鏉ユ簮銆佷氦鏄撳満鎵€銆佷拱鍗栨柟鍚戙€佷骇鍝併€佷氦浠樼獥鍙ｃ€佷环鏍笺€佹暟閲忋€?
宸叉垚浜ら噺銆佸墿浣欓噺銆佺姸鎬併€佽瀵熸椂闂淬€佹潵婧愬紩鐢ㄥ拰娌荤悊鏍囪銆?

PnL 蹇収蹇呴』鍖呭惈缁勫悎銆佷及鍊兼椂闂淬€佸凡瀹炵幇/鏈疄鐜?鎸囩ず鎬?PnL銆佹彁鍓嶅洖鏀剁幇閲戜环鍊笺€?
甯傚満浠峰€笺€佹暟閲忋€佷及鍊煎熀纭€銆佹潵婧愬紩鐢ㄣ€侀璀﹀垪琛ㄥ拰娌荤悊鏍囪銆?

## 瀹㈡埛閮ㄧ讲瑙勫垯

瀹㈡埛鐗瑰畾鐨?EEX銆両CE OCM銆乀rayport銆佺粡绾晢銆並pler銆丳latts 鎴栧唴閮?PnL 閫傞厤鍣?
搴斿厛鏍囧噯鍖栦负璇?payload锛屽啀鐢卞彈娌荤悊鐨勫悗绔换鍔¤皟鐢ㄥ唴閮ㄨ矾鐢辨垨浠撳偍鍑芥暟銆俉eb銆?
Windows銆丼DK 鍜?CLI 姝ｅ紡瀹㈡埛绔笉寰楃洿鎺ュ啓杩欎簺琛ㄣ€?
