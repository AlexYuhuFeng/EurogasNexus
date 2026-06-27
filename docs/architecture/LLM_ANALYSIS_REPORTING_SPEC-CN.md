# LLM 鍒嗘瀽涓庢姤鍛婅鏍?- CN

## V1 鍐崇瓥

DeepSeek 鏄?V1 绗竴涓敮鎸佺殑瀹炴椂 LLM Provider銆侽penAI銆乷ther 鍜屽叾浠?provider
淇濈暀涓哄嚟璇?閫傞厤鍣ㄦЫ浣嶏紝鍚庣画閲岀▼纰戝啀娣诲姞骞舵祴璇曘€?

瀵煎叆浠ｇ爜銆佹祴璇曘€乄eb銆乄indows銆丼DK 鍜?CLI 閮戒笉寰楃洿鎺ヨ皟鐢?LLM銆傚敮涓€鍏佽鐨勫疄鏃?
璺緞鏄細

```text
Client -> /api -> backend analysis route -> backend credential store -> DeepSeek
```

## 鍑瘉瑙勫垯

鐢ㄦ埛鍙互閫氳繃渚涘簲鍟嗗嚟璇?UI/API 杈撳叆 DeepSeek API Key銆傚悗绔皢鍏跺姞瀵嗗瓨鍌ㄥ湪
PostgreSQL 涓€傛槑鏂?key 鍙啓涓嶈锛屼笉寰楄繑鍥炵粰瀹㈡埛绔€佹棩蹇椼€佹姤鍛婃垨娴嬭瘯銆?

Provider ID锛?

- `DEEPSEEK`锛歏1 棣栭€?LLM provider锛?
- `LLM`锛氭棫鐗?閫氱敤 fallback 鍑瘉妲姐€?

## 鍒嗘瀽鑳藉姏

V1 鍒嗘瀽鏀寔锛?

- 鍩轰簬鍚庣蹇収鐨?DB inquiry锛?
- business logic ontology 瑙ｉ噴锛?
- glossary Q&A锛?
- PnL tracking readiness 鍜岄璀︼紱
- TSO operation status report锛?
- portfolio/resource/contract report锛?
- market movement synthesis锛?
- strategy run 鍜?shadow-run context summary銆?

LLM provider 涓嶆槸浜嬪疄鏉ユ簮銆備簨瀹炴潵婧愪粛鐒舵槸 PostgreSQL銆侾rovider 鍙兘鎺ユ敹缁撴瀯鍖?
蹇収锛屼笉寰楃洿鎺ヨ闂暟鎹簱銆?

## 鎶ュ憡鐢熸垚

鎶ュ憡蹇呴』鍖呭惈锛?

- 褰撳墠 portfolio 鎴栭€夊畾 resources/contracts锛?
- 姝ｅ湪杩愯鐨?strategy 鍜?strategy run 鐘舵€侊紱
- 鑻ュ凡鎸佷箙鍖?PnL series锛屽垯灞曠ず鑷?strategy/portfolio 鐢熸晥浠ユ潵鐨勫巻鍙?PnL锛?
- 閫夊畾鏃堕棿娈靛唴鐩稿叧甯傚満浠锋牸銆佹暟閲忋€丗X銆佽矾绾挎垚鏈€乫low銆乻torage銆丩NG 鍜?warning锛?
- 甯﹀紩鐢ㄧ殑鍊欓€夊競鍦哄喅绛栨敮鎸?commentary銆?

鎶ュ憡蹇呴』鍖呭惈 source references銆乵issing inputs銆亀arnings銆乣research_only` 鍜?
`human_review_required`銆?

## 鏈琛ㄩ泦鎴?

鏈琛?term 鍙€氳繃浠ヤ笅绔偣鏆撮湶杩愯惀涓婁笅鏂囷細

```text
GET /api/glossary/{term}/context
```

绀轰緥锛?

- Easington Entry Point锛氭弿杩般€佸閲忋€侀€夊畾蹇収/鏃堕棿娈电殑瀹归噺浣跨敤鐜囥€佺浉鍏?
  NBP/ICE OCM/ICIS 浠锋牸銆佽矾绾块€夐」鍜屾潵婧愮姸鎬併€?
- ICIS Heren锛氫环鏍艰瘎浼版弿杩般€乴icense warning銆佺浉鍏充环鏍煎拰甯傚満鏉ユ簮涓婁笅鏂囥€?

濡傛灉杩愯鏃?DB 鏁版嵁涓嶅彲鐢紝绔偣蹇呴』杩斿洖甯︽槑纭?warning 鐨?partial context锛屼笉寰?
缂栭€犲鎴锋暟鎹€?

## 褰撳墠绔偣

```text
GET  /api/analysis/ontology
POST /api/analysis/query
POST /api/reports/portfolio
GET  /api/glossary/{term}/context
```

## 浜掕仈缃戣姹?

鍙湁鍦?`invoke_provider=true` 涓斿凡閰嶇疆 DeepSeek credential 鏃舵墠闇€瑕佷簰鑱旂綉銆?
绂荤嚎寮€鍙戝拰娴嬭瘯浣跨敤纭畾鎬х殑 snapshot output锛屼笉寰楄皟鐢ㄤ换浣?LLM provider銆?
