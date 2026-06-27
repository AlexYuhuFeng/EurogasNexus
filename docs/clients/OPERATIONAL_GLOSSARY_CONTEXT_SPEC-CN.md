# 杩愯涓婁笅鏂囨湳璇〃瑙勬牸

## 鐩殑

鏈琛ㄤ笉鏄潤鎬佸府鍔╂枃鏈紝鑰屾槸浜ゆ槗鍛橀┚椹惰埍鐨勪竴閮ㄥ垎銆傜敤鎴烽€夋嫨鏈鏃讹紝
绯荤粺蹇呴』鍚屾椂璇存槑璇ユ湳璇殑鍚箟锛屽苟灞曠ず杩愯搴撲腑璁╄鏈鍏锋湁鍟嗕笟鎰忎箟鐨?
涓婁笅鏂囷細瀹归噺銆佸閲忎娇鐢ㄩ噺銆佷环鏍笺€佸疄鏃舵爣璁般€佽矾绾块€夐」銆佸悎鍚屻€佹潵婧愩€侀璀?
鍜屾暟鎹川閲忋€?

## 鏉冨▉ API

`GET /api/glossary/{term}/context` 鏄繍琛屼笂涓嬫枃鏈琛ㄧ殑鍞竴鏉冨▉鎺ュ彛銆?
Web銆乄indows銆丆LI 鍜?SDK 璋冪敤鏂瑰繀椤婚€氳繃 API 鎴?SDK 浣跨敤璇ヨ兘鍔涖€備换浣曞鎴?
绔兘涓嶅緱鐩存帴杩炴帴 PostgreSQL锛屼篃涓嶅緱鐩存帴璇诲彇鍚庣鏈湴鏁版嵁鏂囦欢銆?

鏀寔鐨勬煡璇㈠弬鏁帮細

- `lang=en|zh|zh-CN`
- `duration_start_utc`
- `duration_end_utc`

## 蹇呴』杩斿洖鐨勭粨鏋?

鍝嶅簲蹇呴』淇濈暀鏃㈡湁瀛楁锛屽苟鍖呭惈 V1 鍒嗙粍涓婁笅鏂囧瓧娈碉細

- `description`銆乣description_en`銆乣description_zh_cn`
- `requested_duration`
- `entity_summary`
- `matched_entities`
- `capacity`
- `capacity_usage`
- `metrics`
- `related_prices`
- `live_market_marks`
- `related_routes`
- `related_contracts`
- `context_sections`
- `related_sources`
- `data_quality`
- `warnings`
- `research_only=true`
- `human_review_required=true`

`capacity_usage` 蹇呴』鏀寔鐢ㄦ埛閫夋嫨鐨勬椂闂存銆傚鏋滀竴涓椂闂存鍐呭尮閰嶅埌澶氭潯娴侀噺
璁板綍锛孉PI 蹇呴』杩斿洖骞冲潎浣跨敤閲忋€佸嘲鍊间娇鐢ㄩ噺銆佷娇鐢ㄧ巼鐧惧垎姣斻€佸嘲鍊间娇鐢ㄧ巼鐧惧垎姣斻€?
鏉ユ簮寮曠敤鍜岃娴嬫暟閲忋€傚鏋滄祦閲忓崟浣嶄负 `mcm/d`锛屽閲忓崟浣嶄负 `MWh/d`锛孷1 鍙互浣跨敤
鏄庣‘璁板綍鐨勬崲绠楀亣璁?`1 mcm = 10,550 MWh`锛岀洿鍒板悗缁増鏈帴鍏ユ寜鐑€兼崲绠楃殑鑳藉姏銆?

## 鍖归厤瑙勫垯

瑙ｆ瀽鍣ㄥ繀椤绘槸纭畾鎬х殑锛屽苟涓斾互鏁版嵁搴撲负鍏堛€?

1. 浠庣敤鎴疯姹傜殑鏈寮€濮嬨€?
2. 鍔犲叆鍖归厤鍒扮殑鏈鍚嶇О銆佸埆鍚嶃€佺浉鍏虫湳璇拰鏉ユ簮寮曠敤銆?
3. 鍖归厤浠ヤ笅杩愯搴撹〃涓殑璁板綍锛?
   - `capacity_profiles`
   - `flow_observations`
   - `market_observations`
   - `live_market_marks`
   - `route_candidates`
   - `upstream_resource_contracts`
4. 鏍规嵁鏈鍜岃繍琛岃褰曟帹鏂?`context_type`锛?
   - 鍏ュ彛鐐规湳璇垨鍏ュ彛鐐硅繍琛岃褰曚负 `entry_point`锛?
   - 鍑哄彛鐐硅繍琛岃褰曚负 `exit_point`锛?
   - 鏋㈢航鏈涓?`hub`锛?
   - 甯傚満/浜ゆ槗鍦烘墍鏈涓?`venue`锛?
   - 浠锋牸鏈鎴栧尮閰嶄环鏍艰褰曚负 `price_assessment`锛?
   - 鏈尮閰嶅埌鏇村己绫诲瀷浣嗘湁瀹归噺/娴侀噺鐐硅褰曟椂涓?`capacity`锛?
   - 鍙湁鍦ㄦ病鏈夋洿寮烘湳璇垨杩愯搴撲俊鍙锋椂鎵嶄娇鐢?`generic`銆?
5. 鍙湁鍦ㄦ病鏈変笓鐢?profile 涓旀病鏈変换浣曡繍琛屽簱鍖归厤鏃讹紝鎵嶈繑鍥?
   `TERM_CONTEXT_MAPPING_PARTIAL`銆?

`Easington Entry Point` 杩欐牱鐨勭‖缂栫爜绀轰緥鍙互缁х画浣滀负鎻愮ず锛屼絾鍔熻兘涓嶅緱灞€闄愪簬
Easington/Bacton銆傚彧瑕佸鎴峰湪 PostgreSQL 涓姞杞戒簡鏈銆佸閲忋€佹祦閲忋€佷环鏍笺€佽矾绾?
鍜屽悎鍚岃褰曪紝`St Fergus Entry Point` 绛夊叾浠栫偣涔熷繀椤昏兘澶熺敓鎴愪笂涓嬫枃銆?

## 绀轰緥琛屼负

瀵逛簬 `Easington Entry Point`锛屼笂涓嬫枃搴斿睍绀猴細

- 鑻卞浗 NTS/娴锋哗浜や粯璇存槑锛?
- 鐢ㄦ埛閫夋嫨鐨勬椂闂存锛?
- 瀹归噺妗ｆ锛?
- 浠?MWh/d 鎴?mcm/d 琛ㄧず鐨勫閲忎娇鐢ㄩ噺鍙婄櫨鍒嗘瘮锛?
- 鐩稿叧 NBP銆両CE OCM 鍜?ICIS Heren 浠锋牸锛?
- 瀹炴椂 bid/ask/last 灞忓箷鏍囪锛?
- 璺嚎鍊欓€夛紱
- 鍏宠仈涓婃父鍚堝悓锛?
- 棰勮鍜屾暟鎹川閲忓厓鏁版嵁銆?

瀵逛簬 `ICIS Heren`锛屼笂涓嬫枃搴斿睍绀猴細

- 鎺堟潈浠锋牸璇勪及璇存槑锛?
- 瀹㈡埛鎺堟潈鎴栨搷浣滃憳褰曞叆鐨勮繍琛屽簱浠锋牸璁板綍锛?
- 閫氳繃鐩稿叧鏈杩炴帴鐨?ICE OCM/NBP 绛夊睆骞曟爣璁帮紱
- 鍦ㄦ湭鏄庣‘瀛樺湪鎺堟潈涓庡鎴峰姞杞界殑鎺堟潈鏁版嵁鍓嶏紝蹇呴』鍖呭惈
  `ICIS_HEREN_REQUIRES_CUSTOMER_LICENSED_DATA`銆?

## Web 鍜?Windows 浣撻獙瑙勫垯

Web 宸ヤ綔鍙版槸鍞竴 UI 婧愶紝Windows 瀹㈡埛绔寘瑁呮瀯寤哄悗鐨?Web 瀹㈡埛绔€傛湳璇〃闈㈡澘
蹇呴』灞曠ず锛?

- 楂樹环鍊兼湳璇殑蹇嵎涓婁笅鏂囨寜閽紱
- 鑾峰彇涓婁笅鏂囧墠鐨勬椂闂存閫夋嫨鍣紱
- 鍖归厤瀹炰綋鏍囩锛?
- 鎸囨爣鍗＄墖锛?
- 瀹归噺銆佷环鏍?瀹炴椂鏍囪銆佽矾绾裤€佸悎鍚屽拰鏁版嵁璐ㄩ噺鍒嗙粍锛?
- 瀵圭敤鎴峰彲瑙佺殑棰勮銆?

鏈姛鑳戒粎鐢ㄤ簬鍐崇瓥鏀寔銆備笉寰楀垱寤鸿鍗曘€佹彁浜ゆ彁鍚嶃€佹墽琛屽鎵广€佹彁渚涙硶寰嬫剰瑙侊紝
涔熶笉寰楃敓鎴愬畼鏂逛氦鏄撳缓璁€?
