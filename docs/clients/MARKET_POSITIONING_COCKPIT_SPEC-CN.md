# 甯傚満鎸佷粨椹鹃┒鑸辫鑼?- CN

## 鐩殑

鏈鑼冨畾涔?V1 鐨勫彧璇昏鍗?PnL 椹鹃┒鑸辨墿灞曘€傚畠鐢ㄤ簬甯姪澶╃劧姘斾氦鏄撲汉鍛樺湪鍦板浘浼樺厛
宸ヤ綔鍙颁腑鏌ョ湅澶栭儴灞忓箷娲诲姩銆佺粍鍚堜及鍊笺€佽矾绾跨粡娴庢€у拰绛栫暐杈撳嚭锛屼絾涓嶄細鎶?Eurogas
Nexus 鍙樻垚璁㈠崟鎵ц銆佽鍗曡矾鐢便€佹彁鍚嶆彁浜ゆ垨 ETRM 绯荤粺銆?
## 缁濆鏁版嵁杈圭晫

杩愯鏃朵簨瀹炴潵婧愭槸鍚庣 API 鑳屽悗鐨?PostgreSQL銆傚鎴风鍙兘浣跨敤锛?
```text
Web/Windows/SDK -> /api/v1/portfolio/* -> 鍚庣浠撳偍 -> PostgreSQL
```

瀹㈡埛绔笉寰楃洿鎺ヨ繛鎺?PostgreSQL锛屼笉寰椾繚瀛樿鍗?PnL 鏂囦欢锛屼笉寰楃洿鎺ヨ皟鐢ㄤ氦鏄撴墍锛?涔熶笉寰楄鍙栧悗绔師濮嬫暟鎹枃浠躲€傚閮ㄨ鍗曡褰曞彧鏄鍏ョ殑瑙傚療鏁版嵁锛屼笉鏄氦鏄撴崟鑾疯褰曪紝
V1 涓嶅厑璁镐粠瀹㈡埛绔慨鏀规垨鎾ら攢杩欎簺璁㈠崟銆?
## 宸插惎鐢?API

- `GET /api/v1/portfolio/screen-orders`
- `GET /api/v1/portfolio/pnl-snapshots`
- `GET /api/v1/portfolio/live-summary`

鎵€鏈夌鐐归兘杩斿洖 `research_only=true` 鍜?`human_review_required=true`銆?
## 宸插惎鐢ㄦ暟鎹簱琛?
- `screen_order_observations`
- `portfolio_pnl_snapshots`

杩欎簺琛ㄧ敱 Alembic 鐗堟湰 `0009_market_positioning` 寮曞叆銆?
## Web/Windows UX 瑙勫垯

- 棣栭〉蹇呴』淇濇寔鍦板浘浼樺厛銆?- 濡傛灉鑺傜偣涓婁笅鏂囪冻澶燂紝鍦板浘蹇呴』鐢ㄥ姩鐢婚珮浜睍绀哄綋鍓嶈鍗?PnL 鐩稿叧璺嚎銆?- 褰撳疄鏃剁洴甯傜粨鏋滃皻鏈骇鐢熸椂锛屽湴鍥句笂鏂规寚鏍囨潯蹇呴』浣跨敤杩愯鏃惰瀵熸暟鎹睍绀烘寚绀烘€?  PnL銆?- 渚ф爮蹇呴』灞曠ず璁㈠崟鐘舵€併€佸凡鎴愪氦鏁伴噺銆佸墿浣欐暟閲忋€佸悎绾︿唬鐮併€佹寚绀烘€?PnL銆佹彁鍓嶅洖娆?  浠峰€煎拰鏈畬鎴愬睆骞曡鍗曟暟閲忋€?- 鐣岄潰鏂囨涓嶅緱浣跨敤 鈥滀笅鍗曗€濄€佲€滆矾鐢辫鍗曗€濄€佲€滄壒鍑嗏€濄€佲€滄彁鍚嶁€?鎴?鈥滅珛鍗充氦鏄撯€?绛夋墽琛岀被
  琛ㄨ堪銆?
## 楠屾敹娴嬭瘯

- `tests/api/test_portfolio_api.py`
- `tests/contract/test_market_positioning_models.py`
- `tests/sdk/test_portfolio_client.py`
- `tests/contract/test_client_release_surface.py`

## 涓嬩竴姝ユ墿灞?
Milestone 2 搴斿鍔犵敱瀵煎叆鍣ㄦ帶鍒剁殑瀹㈡埛璁㈠崟/PnL upsert 璺緞銆佸甫鎺堟潈杩囨护鐨勬煡璇€?浠ュ強鍙璁?lineage銆傞櫎闈炰骇鍝佽竟鐣屾寮忓彉鏇达紝瀹㈡埛绔〃闈粛蹇呴』淇濇寔鍙銆?## R19 鍐呴儴瀵煎叆璺緞

R19 宸插疄鐜伴涓唴閮ㄥ鍏ヨ矾寰勶細

```text
POST /api/internal/portfolio/import-observations
```

璇ヨ矾鐢变粎渚涘唴閮?鎿嶄綔鍛樹娇鐢ㄣ€傞櫎闈?`entitlement_decisions` 瀵规瘡涓€涓潵婧愬拰鏁版嵁闆嗙粍鍚堟巿鏉冿紝
鍚﹀垯鎵规榛樿澶辫触鍏抽棴銆傛垚鍔熷拰鎷掔粷鐨勬壒娆￠兘浼氬啓鍏?`ingestion_runs` 涓?`audit_events`銆?Web銆乄indows銆丼DK 鍜?CLI 姝ｅ紡瀹㈡埛绔繀椤荤户缁娇鐢ㄥ彧璇?`/api/v1/portfolio/*` 璺敱銆?
