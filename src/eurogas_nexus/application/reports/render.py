"""One self-contained HTML document from a report snapshot, laid out as a printed publication.

The house standard is ``docs/product/REPORT_EDITORIAL_STANDARD.md``. In short:

- **Print first.** A4 pages, 20 mm top and bottom and 18 mm side margins; running header from
  page 2 and a footer on every page (classification, page X of Y, disclaimer reference) as CSS
  paged-media margin boxes; exhibits never split; widows and orphans held. Page one stands
  alone; the body flows straight into the back matter. On screen the same three sheets (front
  page, body, back matter) sit centred on a grey desk like a PDF viewer.
- **Page economy.** A section's text sits beside its first half-width exhibit, further
  exhibits pair up, and only an exhibit (never a whole section) is kept from splitting, so no
  page ends in an empty quarter. A daily prints page one, two to three body pages and at most a
  page of back matter; the data annex is printed by default for weekly and monthly reports
  only (every series is always in the CSV download).
- **One text family plus a tabular sans.** A serif for headline, standfirst and prose (system
  fonts only: Charter, Georgia, Cambria, Noto/DejaVu Serif ...), ragged right with
  hyphenation; a sans with tabular lining figures for tables, figures, labels and furniture.
- **Page one is the report in miniature:** masthead with the brand mark, headline, standfirst,
  three to five key findings (the fact in bold, its comparison in regular weight), the At a
  glance indicator table, and the lead exhibit sized to fill the rest of the page.
- **Exhibits** are numbered (Figure n, Table n), with a declarative title, a subtitle naming
  the measure and unit, the source line and notes; the text refers to each one.
- **No interface in the document:** no buttons, disclosures, banners or cards. Classification
  and "simulated" are typography: a dagger next to each simulated value, the footnote in the
  page footer and a light diagonal mark on every page of a demonstration report.

Nothing is fetched: CSS inline, charts inline SVG, no script (a JSON data block for the
viewer's CSV download is data, not code). The same snapshot renders the same bytes.
"""

from __future__ import annotations

import json
import math
import re
from datetime import date, datetime
from html import escape
from typing import Any

from eurogas_nexus.application.brand import mark_svg
from eurogas_nexus.application.reports.catalogue import GROUPS, TEMPLATE_VERSION
from eurogas_nexus.application.reports.charts import (
    cut_window,
    render_chart,
    sparkline,
)
from eurogas_nexus.application.reports.facts import window_start
from eurogas_nexus.application.reports.lang import T, writing, zh
from eurogas_nexus.application.reports.tokens import FONT, LIGHT

PUBLICATION = "Eurogas Nexus · Gas Markets"
PUBLICATION_ZH = "Eurogas Nexus · 天然气市场"
SERIF = ('Charter, "Bitstream Charter", "Sitka Text", Cambria, Georgia, "Noto Serif", '
         '"DejaVu Serif", "Liberation Serif", "Times New Roman", "Songti SC", "SimSun", serif')
DAGGER = "†"
STATE_WORDS = {"current": "current", "late": "late", "stale": "stale", "never": "no data",
               "manual": "manual"}
STATE_WORDS_ZH = {"current": "最新", "late": "延迟", "stale": "过期", "never": "无数据",
                  "manual": "手动"}


def _state(state: Any) -> str:
    return (STATE_WORDS_ZH if zh() else STATE_WORDS).get(str(state), str(state or ""))
CLASSIFICATION = {"internal": "INTERNAL", "shareable": "FOR DISTRIBUTION"}
CLASSIFICATION_ZH = {"internal": "内部", "shareable": "可对外分发"}
DISCLAIMER = ("Decision support only: not advice to trade, and nothing here describes "
              "execution, nomination or settlement.")
DISCLAIMER_ZH = "仅供决策参考：不构成交易建议，亦不涉及执行、提名或结算。"

#: Attribution lines a public source's terms ask for (docs/legal/DATA_SOURCE_TERMS.md).
ATTRIBUTIONS: dict[str, str] = {
    "ENTSOG": "ENTSOG Transparency Platform, https://transparency.entsog.eu/ (data downloaded "
              "{day}). ENTSOG does not endorse this report.",
    "GIE": "Gas Infrastructure Europe: AGSI+ (storage) and ALSI (LNG) transparency platforms. "
           "GIE is the data source.",
    "REMIT": "REMIT inside information as published by the operators on their platforms "
             "(GIE IIP where collected there: GIE is the data source).",
    "ENTSOE": "ENTSO-E Transparency Platform.",
    "ELEXON": "Contains BMRS data © Elexon Limited copyright and database right.",
    "NATIONAL_GAS": "National Gas Transmission data portal (open data licence).",
    "NATIONAL_GAS_DEMAND": "National Gas Transmission data portal (open data licence).",
    "ECB": "European Central Bank reference rates.",
    "EIA": "U.S. Energy Information Administration.",
}
GLOSSARY = (
    ("DA", "Day-ahead: gas delivered on the next gas day."),
    ("Front month", "The nearest calendar month traded; it rolls at each month end."),
    ("Gas day", "06:00 to 06:00 local time on the continent (05:00 to 05:00 UTC in winter)."),
    ("Gas year", "1 October to 30 September."),
    ("GWh/d", "Gigawatt hours per gas day (energy, gross calorific value)."),
    ("TWh", "Terawatt hours of energy."),
    ("EUR/MWh", "Euro per megawatt hour; continental hub prices."),
    ("GBp/th", "Pence sterling per therm; NBP prices."),
    ("MWh/d", "Megawatt hours per gas day; book positions."),
    ("Points", "Percentage points (storage fill)."),
    ("Supply call", "Norwegian pipeline landings plus LNG send-out plus net storage withdrawal "
                    "into NW Europe."),
    ("Net withdrawal", "Storage withdrawal less injection; negative when storage fills."),
    ("REMIT / UMM", "EU market-integrity rules / urgent market message: published outages."),
    ("AGSI+ / ALSI", "GIE's storage and LNG transparency platforms."),
    ("Implied gas burn", "Gas-fired electricity divided by an assumed plant efficiency."),
)

GLOSSARY_ZH = {
    "DA": ("DA", "日前：次一燃气日交付的天然气。"),
    "Front month": ("近月", "最近的可交易日历月；每月月底换月。"),
    "Gas day": ("燃气日", "欧洲大陆当地时间06:00至次日06:00（冬季为 UTC 05:00 至 05:00）。"),
    "Gas year": ("气年", "10月1日至次年9月30日。"),
    "GWh/d": ("GWh/d", "每燃气日吉瓦时（能量，高位热值）。"),
    "TWh": ("TWh", "太瓦时能量。"),
    "EUR/MWh": ("EUR/MWh", "欧元每兆瓦时；欧洲大陆枢纽价格。"),
    "GBp/th": ("GBp/th", "便士每色姆；NBP 价格。"),
    "MWh/d": ("MWh/d", "每燃气日兆瓦时；账簿头寸。"),
    "Points": ("百分点", "百分点（储气率）。"),
    "Supply call": ("供应需求", "进入西北欧的挪威管道到岸量、LNG 外输与储气净提取之和。"),
    "Net withdrawal": ("净提取", "储气提取减注入；注气时为负。"),
    "REMIT / UMM": ("REMIT / UMM", "欧盟市场诚信规则 / 紧急市场消息：已发布的停运。"),
    "AGSI+ / ALSI": ("AGSI+ / ALSI", "GIE 的储气与 LNG 透明度平台。"),
    "Implied gas burn": ("隐含燃气消耗", "燃气发电量除以假定的电厂效率。"),
}
#: Method notes in Chinese, by key (the sections' ``methods``).
METHODS_ZH = {
    "landing_points": ("登陆点与运营方", "每个 ENTSOG 点每个燃气日采用一个运营方：登陆登记表为该点"
                       "指定的运营方；否则沿用前一燃气日为该点选定且当日有报告的运营方；否则取当日有"
                       "报告者中排序最先的运营方。进出两侧均采用该运营方的报告，方向相对于其系统；"
                       "其他运营方的副本不重复计入。"),
    "storage_scope": ("储气范围", "比利时、德国、丹麦、法国、荷兰公布工作容量的设施；某日仅在报告"
                      "国家数与覆盖最好的一天相同时计入。英国不公布工作容量，不计入储气率。"),
    "power_day": ("日期与覆盖", "UTC 日；某区域在某日的时段覆盖至少22.5小时才计入，且某日仅在报告"
                  "区域数与覆盖最好的一天相同时计入。"),
    "remit_daily": ("每日不可用容量", "每条消息的最新版本；在消息单位允许时换算为 GWh/d，否则以"
                    "原单位显示。"),
    "forecast_call": ("需求", "季节常态加近期偏差"),
    "forecast_inventory_draw": ("库存提取", "残差减库存外14天均值"),
    "forecast_lng": ("LNG", "14天均值"),
    "forecast_norway": ("挪威", "7天均值减 REMIT 停运"),
    "forecast_storage": ("储气", "残差"),
    "pipeline_landings_note": ("管道到岸说明", "能量按 ENTSOG 发布值，每个实物登陆点一行。英国终端"
                               "同时接收英国大陆架天然气与挪威天然气。"),
    "storage_inventory_basis": ("库存口径", "公布工作容量的设施；英国库存（National Gas）无工作"
                                "容量，不计入库存与储气率"),
    "outage_adjustment": ("停运调整", "未来不可用容量减最近七次观测的不可用容量"),
    "net_position": ("净头寸", "每燃气日净 MWh：多头为正，合同按日量计，屏幕交易按交付日分摊。"),
    "day_pnl_change": ("当日损益变化", "枢纽未来12个月净未平仓头寸乘以最近两日收盘价之差：头寸阶梯"
                       "的平行移动，并非重估。"),
    "credit_exposure": ("信用敞口", "重置敞口（未交付量按市价减合同价，按交易对手轧差并以零为下限）"
                        "加最近应收天数的销售应收款，减所持抵押；使用率为其占限额之比。"),
    "mandate_usage": ("授权使用", "授权所含账簿及交易员自营账户中最大的枢纽月净头寸相对授权规模"
                      "上限，并核对其枢纽、期限、产品与对冲区间。"),
}
#: Why a section is not included, in Chinese (``sections._empty`` reasons; prefix match).
REASONS_ZH = {
    "No licensed close for": "您的许可下没有该枢纽的收盘价",
    "No REMIT messages are held": "未持有 REMIT 消息",
    "No complete gas day of Norwegian landings is held": "未持有挪威到岸量的完整燃气日",
    "No complete gas day of landings in the period": "期间内没有到岸量的完整燃气日",
    "No complete gas day of LNG send-out in the period": "期间内没有 LNG 外输的完整燃气日",
    "No complete gas day of LNG send-out": "没有 LNG 外输的完整燃气日",
    "No LNG send-out is held for the scope": "该范围内未持有 LNG 外输数据",
    "No complete day of gas-fired generation in the period": "期间内没有燃气发电的完整日",
    "No complete day of gas-fired generation": "没有燃气发电的完整日",
    "No gas-fired generation is held for the scope": "该范围内未持有燃气发电数据",
    "No storage day in the period is still in the season read": "期间内的储气日已不在季节读取范围"
                                                                "内",
    "Storage data not connected": "未接入储气数据",
    "No measured balance day in the period": "期间内没有实测平衡日",
    "The balance needs ENTSOG flows, GIE storage and LNG": "平衡需要 ENTSOG 流量、GIE 储气与 LNG",
    "The landings use data outside your licences": "到岸量使用了您许可范围之外的数据",
    "No position is held in the books you may see": "您可查看的账簿中没有头寸",
    "No P&L figure is held for the books you may see": "您可查看的账簿没有损益数据",
    "No credit line or mandate is held that you may see": "没有您可查看的信用额度或授权",
    "No supply contract is in effect in the books you may see": "您可查看的账簿中没有生效的供应合"
                                                                "同",
    "No critical or watch alert is open": "没有未关闭的严重或观察级预警",
    "The outage is not open or upcoming, or is not visible to you": "该停运未开放或即将开始，或您"
                                                                    "无权查看",
    "The alert does not exist or is not visible to you": "该预警不存在或您无权查看",
    "Only a physical-market alert can open a shareable report": "仅实物市场预警可生成对外分发报告",
    "the generating principal may see no book": "生成者无权查看任何账簿",
    "not available": "暂不可用",
    "Our book is not part of a shareable report": "对外分发报告不含我方账簿",
    "Open alerts": "未关闭预警",
    "Balance not available here": "此处无法读取平衡数据",
    "The balance uses data outside your licences": "平衡使用了您许可范围之外的数据",
    "Balance needs ENTSOG flows, GIE storage and LNG": "平衡需要 ENTSOG 流量、GIE 储气与 LNG",
}

CSS_TEMPLATE = """
*{box-sizing:border-box}
:root{--ink:#18181b;--ink-2:#52525b;--ink-3:#5f5f68;--rule:#a1a1aa;--hair:#d4d4d8;
--accent:ACCENT;--paper:#fff;--desk:#e4e4e7}
html{background:var(--desk)}
body{margin:0;background:var(--desk);color:var(--ink);font:9.5pt/13.2pt SERIF;
hyphens:auto;-webkit-hyphens:auto;font-kerning:normal;text-rendering:optimizeLegibility}
.r-sheet{width:210mm;min-height:297mm;margin:10mm auto;padding:20mm 18mm 22mm;
background:var(--paper);box-shadow:0 1px 3px rgba(0,0,0,.18)}
.r-body,.r-back-sheet{min-height:0}
.r-sans,.r-masthead,.r-label,figcaption,table,.r-source,.r-glance,.r-side,.r-annex,
.r-back,.r-contents{font-family:SANS;font-variant-numeric:tabular-nums lining-nums}
.r-masthead{display:grid;grid-template-columns:1fr auto;gap:1mm 6mm;
border-top:2.4pt solid var(--ink);border-bottom:0.5pt solid var(--ink);padding:2.5mm 0 2mm;
margin-bottom:5mm;font-size:7.5pt;line-height:10pt;color:var(--ink-2)}
.r-brand{display:flex;align-items:center;gap:8px;margin:0}
.r-brand svg{flex:none}
.r-pub{font-size:10pt;letter-spacing:.08em;white-space:nowrap;text-transform:uppercase;
color:var(--ink);font-weight:600}
.r-mast-right{text-align:right}
.r-class{letter-spacing:.12em;font-weight:600;color:var(--ink)}
.r-label{font-size:7pt;line-height:10pt;letter-spacing:.14em;text-transform:uppercase;
color:var(--ink-2);font-weight:600;margin:0 0 1.5mm}
h1{font:600 19pt/23pt SERIF;margin:0 0 2.5mm;max-width:150mm;letter-spacing:-.005em}
.r-standfirst{font-size:11pt;line-height:14.5pt;margin:0 0 4mm;max-width:128mm;color:var(--ink)}
.r-question{font:600 17pt/21pt SERIF}
.r-answer{border-left:2pt solid var(--accent);padding:0.5mm 0 0.5mm 4mm;margin:0 0 4mm;
max-width:150mm}
.r-answer p{font-size:10.5pt;line-height:14pt;margin:0}
.r-findings{border-top:0.5pt solid var(--ink);padding-top:2mm;margin-bottom:4mm}
.r-findings ol{margin:0;padding:0;list-style:none;counter-reset:f;max-width:150mm}
.r-findings li{counter-increment:f;position:relative;padding-left:7mm;margin:0 0 1.4mm;
font-size:9pt;line-height:12.4pt}
.r-findings li::before{content:counter(f);position:absolute;left:0;top:0;font:600 9pt/12.4pt SANS;
color:var(--accent)}
.r-findings strong{font-weight:600}
h2{font:600 12pt/15pt SERIF;margin:0 0 1.5mm;break-after:avoid}
.r-group{border-top:0.5pt solid var(--ink);padding-top:1.5mm;margin:5mm 0 1mm;break-after:avoid}
.r-section{margin:0 0 3mm}
.r-section>h2+*{break-before:avoid}
.r-cols{display:grid;grid-template-columns:118mm 1fr;gap:0 8mm;margin:0 0 2mm}
.r-row{display:grid;grid-template-columns:1fr 1fr;gap:0 6mm;margin:0 0 2mm}
.r-row>*{min-width:0}
/* Print layout (the in-app Print, app/model/reportPrintLayout.ts): a row whose figure would
   cross a page keeps its text on the page; the figure follows the page break. */
.r-row-split{display:block}.r-row-split>.r-text{max-width:118mm}
.r-row-moved>figure{grid-column:1}
.r-text p{margin:0 0 2mm;widows:2;orphans:2}
.r-cols .r-text p{max-width:118mm}
.r-lead{font-weight:600}
.r-side{font-size:7.5pt;line-height:10.5pt;color:var(--ink-2);border-left:0.5pt solid var(--hair);
padding-left:3mm}
.r-side dt{color:var(--ink);font-weight:600}.r-side dd{margin:0 0 1.5mm}
figure{margin:0 0 3mm;break-inside:avoid;page-break-inside:avoid}
figcaption{font-size:8pt;line-height:10.5pt;margin-bottom:1mm;break-after:avoid}
.r-exno{font-size:6.8pt;letter-spacing:.12em;text-transform:uppercase;color:var(--accent);
font-weight:600;margin-right:1.5mm}
.r-extitle{font-weight:600;color:var(--ink);font-size:8.4pt;line-height:10.5pt}
.r-exsub{display:block;color:var(--ink-2)}
.r-chart{display:block;width:100%;height:auto}
.r-source{font-size:6.6pt;line-height:8.6pt;color:var(--ink-3);margin:0.8mm 0 0}
table{border-collapse:collapse;width:100%;font-size:7.8pt;line-height:10.2pt}
thead th{border-top:0.8pt solid var(--ink);border-bottom:0.5pt solid var(--ink);font-weight:600;
text-align:left;padding:0.8mm 1.5mm;vertical-align:bottom;color:var(--ink)}
tbody td,tbody th{padding:0.55mm 1.5mm;border-bottom:0.25pt solid var(--hair);vertical-align:top;
text-align:left;font-weight:400}
tbody tr:last-child td,tbody tr:last-child th{border-bottom:0.8pt solid var(--ink)}
tr.r-total td{border-top:0.5pt solid var(--ink);font-weight:600}
td.n,th.n{text-align:right;white-space:nowrap}td.t{white-space:nowrap}
td.r-unit,th.r-unit{width:15mm;color:var(--ink-2);white-space:nowrap}
.r-dag{font-size:70%;vertical-align:super;line-height:0;color:var(--ink-2)}
.st-late{color:#854d0e}.st-stale{color:#b91c1c}
.r-glance td,.r-glance th{padding-top:.3mm;padding-bottom:.3mm}.r-glance td.r-sp{width:18mm}
.r-glance .r-blank{color:var(--ink-3)}
.r-spark{display:block}
.r-lead-ex{margin:0}
.r-contents{font-size:8pt;margin:0 0 4mm}.r-contents ol{margin:0;padding-left:5mm;columns:2}
.r-watch{border-top:0.5pt solid var(--ink);padding-top:2mm;margin-top:3mm;break-inside:avoid}
.r-watch ul{margin:0;padding-left:4mm}
.r-back{font-size:6.7pt;line-height:8.6pt;color:var(--ink);border-top:1.2pt solid var(--ink);
margin-top:5mm;padding-top:1.5mm}
.r-back h2{font:600 9pt/12pt SANS;margin:0 0 1.5mm}
.r-back h3{font:600 7pt/9pt SANS;margin:1.6mm 0 .4mm;letter-spacing:.06em;text-transform:uppercase;
color:var(--ink-2)}
.r-back p{margin:0 0 1mm}
.r-back b{font-weight:600}
.r-back table{font-size:6.6pt;line-height:8.4pt}
.r-three{columns:3;column-gap:6mm}
.r-three h3{break-after:avoid}
.r-annex{margin-top:4mm}
.r-annex table{font-size:6.4pt;line-height:8.2pt}
.r-annex figure{break-inside:avoid;margin:0 0 2.5mm}
.r-annex .r-flow{columns:3;column-gap:5mm}.r-annex .r-flow-2{columns:2}
.r-mark{display:none}
.r-demo .r-mark{display:block;position:fixed;top:45%;left:0;right:0;text-align:center;
transform:rotate(-30deg);font:600 30pt/1 SANS;letter-spacing:.2em;color:rgba(109,40,217,.055);
pointer-events:none;z-index:0;text-transform:uppercase}
.r-ink-1{fill:var(--ink)}.r-ink-2{fill:var(--ink-2)}.r-ink-3{fill:var(--ink-3)}
@media screen and (max-width:820px){
.r-sheet{width:auto;min-height:0;margin:0;padding:6mm 4mm;box-shadow:none}
.r-cols,.r-row{grid-template-columns:1fr}
.r-three,.r-annex .r-flow{columns:1}.r-side{border-left:0;padding-left:0}
table{display:block;overflow-x:auto}
.r-masthead{grid-template-columns:1fr}.r-mast-right{text-align:left}}
@page{size:A4;margin:20mm 18mm 20mm 18mm;
@top-left{content:"HEADER_LEFT";font:7pt SANS;color:#52525b;vertical-align:bottom;
padding-bottom:3mm}
@top-right{content:"CLASS";font:600 7pt SANS;letter-spacing:.1em;color:#18181b;
vertical-align:bottom;padding-bottom:3mm}
@bottom-left{content:"CLASS · FOOT_LEFT";font:6.8pt SANS;color:#52525b;
vertical-align:top;padding-top:3mm}
@bottom-center{content:"FOOT_CENTER";font:6.8pt SANS;color:#52525b;vertical-align:top;
padding-top:3mm}
@bottom-right{content:PAGE_OF;font:6.8pt SANS;color:#52525b;
vertical-align:top;padding-top:3mm}}
@page:first{@top-left{content:none}@top-right{content:none}}
@media print{
html,body{background:#fff}
.r-sheet{width:auto;min-height:0;margin:0;padding:0;box-shadow:none}
.r-front{break-after:page}
h1,h2,h3,figcaption,.r-label,.r-group{break-after:avoid}
p{widows:2;orphans:2}
tr{break-inside:avoid}
thead{display:table-header-group}
a{color:inherit;text-decoration:none}}
"""


#: Furniture words in the report's language. Rule-written prose and the methodology are
#: English; an edition in Chinese carries the editor's Chinese text and these labels.
WORDS: dict[str, dict[str, str]] = {
    "en": {
        "key_findings": "Key findings", "at_a_glance": "At a glance",
        "glance_sub": "Latest value and change; points for storage fill; blank where no "
                      "comparison is held",
        "indicator": "Indicator", "unit": "Unit", "latest": "Latest", "day": "Day",
        "week": "Week", "year": "Year", "norm": "vs norm", "as_of": "As of",
        "days30": "30 days", "figure": "Figure", "table": "Table", "source": "Source:",
        "note": "Note:", "data_as_of": "Data as of", "issue": "Issue", "period": "Period",
        "to": "to", "demo": "DEMONSTRATION DATA: SIMULATED", "question": "Question:",
        "contents": "Contents", "watch": "What to watch",
        "method": "Methodology and sources", "annex": "Data annex",
        "foot_left": "Not advice to trade: see Methodology", "page": "Page", "of": "of",
        "simulated_foot": "† Simulated demonstration data, not market prices",
        "glance_source": "Eurogas Nexus calculations from the sources listed in Methodology.",
        "rows_newest": "rows, newest first",
        "answer": "Answer", "evidence": "Evidence",
        "cannot_tell": "What the data cannot tell",
    },
    "zh-CN": {
        "key_findings": "要点", "at_a_glance": "一览",
        "glance_sub": "最新值与变化；储气率以百分点计；无可比数据处留空",
        "indicator": "指标", "unit": "单位", "latest": "最新", "day": "日变化",
        "week": "周变化", "year": "同比", "norm": "较常态", "as_of": "日期",
        "days30": "近30天", "figure": "图", "table": "表", "source": "来源：",
        "note": "注：", "data_as_of": "数据截至", "issue": "第", "period": "期间",
        "to": "至", "demo": "演示数据：模拟", "question": "问题：",
        "contents": "目录", "watch": "关注事项",
        "method": "方法与来源", "annex": "数据附录",
        "foot_left": "非交易建议：见方法说明", "page": "第", "of": "页，共",
        "simulated_foot": "† 模拟演示数据，非市场价格",
        "glance_source": "Eurogas Nexus 根据方法说明所列来源计算。",
        "rows_newest": "行，最新在前",
        "answer": "回答", "evidence": "依据",
        "cannot_tell": "数据无法说明的内容",
    },
}
#: Section and group titles of the Chinese edition (keys as in the catalogue).
TITLES_ZH = {
    "prices": "枢纽价格", "alerts": "预警", "pipeline_supply": "挪威管道到岸量",
    "lng": "LNG 气化外输", "storage": "西北欧储气", "power_burn": "燃气发电",
    "outages": "停运", "balance": "西北欧平衡与展望", "situation_event": "事件",
    "book_position": "我方头寸", "book_pnl": "损益", "book_limits": "限额",
    "book_contracts": "合同",
    "pf_supply": "供应组合", "pf_trades": "交易与销售", "pf_pnl": "已实现与未实现",
    "pf_outlook": "远期展望", "pf_lng": "LNG 船货与气化", "pf_strategies": "账簿运作方式",
    "Prices": "价格", "Supply": "供应", "Storage": "储气", "Demand": "需求",
    "Infrastructure and outages": "基础设施与停运", "Balance": "平衡",
    "Balance and outlook": "平衡与展望", "What happened": "要闻", "Our book": "我方账簿",
    "Alerts": "预警", "Event": "事件",
}
KIND_ZH = {"daily": "日报", "weekly": "周报", "monthly": "月报", "situation": "事件报告",
           "ask": "专题报告"}


def _lang(snapshot: dict) -> str:
    return "zh-CN" if str(snapshot.get("language") or "en").startswith("zh") else "en"


def _w(lang: str, key: str) -> str:
    return WORDS[lang][key]


def _e(text: Any) -> str:
    return escape("" if text is None else str(text), quote=True)


def _css_string(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _publication() -> str:
    """The publication line in the report's language (a Chinese report reads Chinese throughout)."""
    return PUBLICATION_ZH if zh() else PUBLICATION


def _css(snapshot: dict) -> str:
    lang = _lang(snapshot)
    classification = (CLASSIFICATION_ZH if zh() else CLASSIFICATION).get(
        snapshot["audience"], T("INTERNAL", "内部"))
    header = f"{_publication()} · {snapshot['title']}"
    foot = _w(lang, "simulated_foot") if snapshot.get("simulated") else ""
    if lang == "en":
        page_of = '"Page " counter(page) " of " counter(pages)'
    else:
        page_of = '"第 " counter(page) " 页，共 " counter(pages) " 页"'
    css = (CSS_TEMPLATE.replace("SERIF", SERIF).replace("SANS", FONT)
           .replace("ACCENT", LIGHT["accent"])
           .replace("HEADER_LEFT", _css_string(header))
           .replace("CLASS", _css_string(classification))
           .replace("FOOT_LEFT", _css_string(_w(lang, "foot_left")))
           .replace("FOOT_CENTER", _css_string(foot))
           .replace("PAGE_OF", page_of))
    return "".join(line.strip() for line in css.splitlines())


def mark_simulated(text: str) -> str:
    """Escape ``text`` and print each "(simulated)" as a dagger after the value."""

    return _e(text).replace(" (simulated)", f'<span class="r-dag" title="simulated">{DAGGER}'
                                            "</span>").replace("（模拟）", (
                                                f'<span class="r-dag" title="simulated">{DAGGER}'
                                                "</span>"))


def fmt_number(value: Any, kind: str = "num") -> str:
    if value is None or value == "":
        return ""
    if not isinstance(value, int | float):
        return str(value)
    magnitude = abs(value)
    digits = 0 if magnitude >= 1000 else 1 if magnitude >= 100 else 2
    text = f"{abs(value):,.{digits}f}"
    if value < 0:
        return "−" + text
    if kind == "signed" and value > 0:
        return "+" + text
    return text


def fmt_date(value: Any) -> str:
    if not value:
        return ""
    try:
        moment = date.fromisoformat(str(value)[:10])
    except ValueError:
        return str(value)
    if zh():
        return f"{moment.year}年{moment.month}月{moment.day}日"
    return f"{moment.day} {moment:%b %Y}"


def fmt_short(value: Any) -> str:
    try:
        moment = date.fromisoformat(str(value)[:10])
    except ValueError:
        return str(value or "")
    return f"{moment.month}月{moment.day}日" if zh() else f"{moment.day} {moment:%b}"


def fmt_datetime(value: Any) -> str:
    if not value:
        return ""
    if value == "open":
        return T("open", "未定")
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return str(value)
    if zh():
        return f"{moment.year % 100}年{moment.month}月{moment.day}日 {moment:%H:%M}"
    return f"{moment.day} {moment:%b %y %H:%M}"


class Numbering:
    """Figure and table numbers in print order."""

    def __init__(self) -> None:
        self.figures = 0
        self.tables = 0

    def figure(self) -> int:
        self.figures += 1
        return self.figures

    def table(self) -> int:
        self.tables += 1
        return self.tables


NUM = ' class="n"'
TOTAL = ' class="r-total"'


def _cell(row: dict, column: dict, first_number: str | None) -> str:
    key, kind = column["key"], column["kind"]
    value = row.get(key)
    if kind in {"num", "signed"}:
        text = _e(fmt_number(value, kind))
        if key == first_number and row.get("simulated") and value is not None:
            text += f'<span class="r-dag">{DAGGER}</span>'
        return f'<td class="n">{text}</td>'
    if kind == "date":
        return f"<td>{_e(fmt_short(value))}</td>"
    if kind == "datetime":
        return f'<td class="t">{_e(fmt_datetime(value or "open"))}</td>'
    if kind == "state":
        return f'<td class="st-{_e(value)}">{_e(_state(value))}</td>'
    if isinstance(value, str) and _ISO_MOMENT.match(value):
        return f'<td class="t">{_e(fmt_datetime(value))} UTC</td>'
    text = _tw(value)
    short = isinstance(text, str) and len(text) <= 4  # a status word never breaks mid-word
    return ('<td class="t">' if short else "<td>") + f"{_e(text)}</td>"


_ISO_MOMENT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")


#: Table words the builders write in English, as the Chinese edition prints them.
TABLE_ZH = {
    "Open alerts, critical first": "未关闭预警（严重在前）", "Severity": "严重程度",
    "Category": "类别", "Alert": "预警", "Updated": "更新时间",
    "Day P&L change on the open position": "未平仓头寸日损益变化", "Hub": "枢纽",
    "Day change": "日变化", "Currency": "货币", "Not valued because": "未估值原因",
    "Imported indicative P&L valuations": "导入的指示性损益估值", "Portfolio": "组合",
    "Indicative P&L (GBP)": "指示性损益（GBP）", "Since previous (GBP)": "较上次（GBP）",
    "Valued": "估值时间", "Contracts in effect today": "今日生效合同", "Contract": "合同",
    "Delivery point": "交付点", "Gas year": "气年", "Price": "价格", "Price unit": "价格单位",
    "Book": "账簿", "Unit": "单位", "The message": "消息内容", "Facility": "设施",
    "Zone": "区域", "Type": "类型", "Unavailable": "不可用", "Technical capacity": "技术容量",
    "Start (UTC)": "开始（UTC）", "End (UTC)": "结束（UTC）", "Published": "发布时间",
    "Version": "版本", "Reason": "原因", "Hubs it touches first": "首先影响的枢纽",
    "What to check": "需核对事项", "The alert": "预警内容", "Detected": "检测时间",
    "open": "未定", "not stated": "未说明", "n/a": "无",
    "critical": "严重", "watch": "观察", "info": "信息", "physical": "实物",
    "Norwegian landings around the outage": "停运前后的挪威到岸量", "Landed": "到岸量",
    "active": "活跃", "scheduled": "计划", "ended": "已结束",
    "unplanned": "非计划", "planned": "计划", "credit line": "信用额度", "mandate": "授权",
}


def _tw(text: Any) -> Any:
    return TABLE_ZH.get(text, text) if zh() and isinstance(text, str) else text


def table_html(spec: dict) -> str:
    """A table: text columns left-aligned, numbers right-aligned, units in the heads."""

    columns = spec["columns"]
    first_number = next((c["key"] for c in columns if c["kind"] in {"num", "signed"}), None)
    head = "".join(
        f'<th scope="col"{NUM if c["kind"] in {"num", "signed"} else ""}>{_e(_tw(c["label"]))}</th>'
        for c in columns)
    body = "".join(
        f'<tr{TOTAL if row.get("total") else ""}>'
        + "".join(_cell(row, c, first_number) for c in columns) + "</tr>"
        for row in spec["rows"])
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _furniture(label: str, title: str, subtitle: str) -> str:
    """Number and declarative title on one line, the measure and unit beneath."""

    return (f'<figcaption><span class="r-exno">{_e(label)}</span>'
            f'<span class="r-extitle">{mark_simulated(title)}</span>'
            + (f'<span class="r-exsub">{_e(subtitle)}</span>' if subtitle else "")
            + "</figcaption>")


def _source_line(source: str, as_of: str, notes: str = "", lang: str = "en") -> str:
    """Source, data time and any note in one small paragraph under the exhibit."""

    note = f" {_w(lang, 'note')} {_e(notes)}" if notes else ""
    return (f'<p class="r-source">{_w(lang, "source")} {_e(source)} {_w(lang, "data_as_of")} '
            f"{_e(fmt_datetime(as_of))} UTC.{note}</p>")


def table_exhibit(spec: dict, number: int, as_of: str, lang: str = "en") -> str:
    if not spec.get("rows"):
        return ""
    return (f'<figure class="r-exhibit r-table" id="t{number}">'
            + _furniture(f"{_w(lang, 'table')} {number}", _tw(spec.get("caption", "")),
                         spec.get("subtitle", ""))
            + table_html(spec)
            + _source_line(spec.get("source") or "Eurogas Nexus.", as_of, spec.get("notes", ""),
                           lang)
            + "</figure>")


def chart_exhibit(spec: dict, number: int, as_of: str, end: date, lang: str = "en") -> str:
    window = spec.get("window")
    shown = cut_window(spec, window_start(window, end), end) if window else spec
    svg = render_chart(shown, f"f{number}")
    if not svg:
        return ""
    extra = " r-lead-ex" if spec.get("lead") else " r-half-ex" if spec.get("half") else ""
    return (f'<figure class="r-exhibit{extra}" id="f{number}">'
            + _furniture(f"{_w(lang, 'figure')} {number}", spec.get("title", ""),
                         spec.get("subtitle", ""))
            + svg + _source_line(spec.get("source", ""), as_of, spec.get("notes", ""), lang)
            + "</figure>")


# ------------------------------------------------------------------------- front page


def _masthead(snapshot: dict) -> str:
    lang = _lang(snapshot)
    classification = (CLASSIFICATION_ZH if zh() else CLASSIFICATION).get(
        snapshot["audience"], T("INTERNAL", "内部"))
    period = snapshot.get("period") or {}
    issue = snapshot.get("issue") or 1
    demo = (f' · <span class="r-class">{_w(lang, "demo")}</span>'
            if snapshot.get("simulated") else "")
    licensed = (snapshot.get("licensed") or {}).get("sources")
    if licensed:
        classification += f" · Licensed data from {', '.join(licensed)}: internal use"
    span = ""
    if period.get("start") and period.get("end") and period["start"] != period["end"]:
        span = (f" · {_w(lang, 'period')} {fmt_short(period['start'])} {_w(lang, 'to')} "
                f"{fmt_date(period['end'])}")
    kind = (KIND_ZH.get(snapshot["kind"], snapshot["kind_label"]) if lang != "en"
            else snapshot["kind_label"])
    line = (_e(snapshot["title"]) if snapshot["title"].startswith(kind)
            else f"{_e(kind)} · {_e(snapshot['title'])}")
    issue_text = f"第 {issue} 期" if lang != "en" else f"Issue {issue}"
    # The paper is white in every medium, so the mark is drawn in its colour tone.
    brand = mark_svg("colour", size=20, title=None)
    return (
        '<header class="r-masthead"><div><p class="r-brand">'
        f'{brand}<span class="r-pub">{_e(_publication())}</span></p><div>{line}</div></div>'
        f'<div class="r-mast-right"><div class="r-class">{_e(classification)}</div>'
        f"<div>{_e(issue_text)} · {_e(fmt_date(snapshot['as_of']))}{_e(span)}</div>"
        f"<div>{_w(lang, 'data_as_of')} {_e(fmt_datetime(snapshot['as_of']))} UTC{demo}</div>"
        "</div></header>"
    )


def _glance(snapshot: dict, number: int) -> str:
    lang = _lang(snapshot)
    rows = snapshot.get("glance") or []
    if not rows:
        return ""
    has_year = any(r["year"] is not None for r in rows)
    has_norm = any(r.get("norm") is not None for r in rows)
    head = [f'<th scope="col">{_w(lang, "indicator")}</th>',
            f'<th scope="col" class="r-unit">{_w(lang, "unit")}</th>',
            f'<th scope="col"{NUM}>{_w(lang, "latest")}</th>',
            f'<th scope="col"{NUM}>{_w(lang, "day")}</th>',
            f'<th scope="col"{NUM}>{_w(lang, "week")}</th>']
    if has_year:
        head.append(f'<th scope="col"{NUM}>{_w(lang, "year")}</th>')
    if has_norm:
        head.append(f'<th scope="col"{NUM}>{_w(lang, "norm")}</th>')
    head += [f'<th scope="col">{_w(lang, "as_of")}</th>',
             f'<th scope="col">{_w(lang, "days30")}</th>']
    body = []
    for r in rows:
        dag = f'<span class="r-dag">{DAGGER}</span>' if r["simulated"] else ""
        cells = [f'<th scope="row">{_e(r["label"])}</th>',
                 f'<td class="r-unit">{_e(r["unit"])}</td>',
                 f'<td class="n">{_e(fmt_number(r["latest"]))}{dag}</td>']
        for key in ["day", "week"] + (["year"] if has_year else []) + (["norm"] if has_norm
                                                                        else []):
            value = r.get(key)
            cells.append(f'<td class="n">{_e(fmt_number(value, "signed"))}</td>'
                         if value is not None else '<td class="n r-blank"></td>')
        state = "" if r["state"] == "current" else T(f" ({_state(r['state'])})",
                                                         f"（{_state(r['state'])}）")
        cells.append(f'<td class="st-{_e(r["state"])}">{_e(fmt_short(r["as_of"]))}{_e(state)}</td>')
        cells.append(f'<td class="r-sp">{sparkline(r.get("spark") or [], label=r["label"])}</td>')
        body.append("<tr>" + "".join(cells) + "</tr>")
    return (f'<figure class="r-exhibit r-glance" id="t{number}">'
            + _furniture(f"{_w(lang, 'table')} {number}", _w(lang, "at_a_glance"),
                         _w(lang, "glance_sub"))
            + f'<table><thead><tr>{"".join(head)}</tr></thead><tbody>{"".join(body)}</tbody>'
            "</table>" + _source_line(_w(lang, "glance_source"), snapshot["as_of"], lang=lang)
            + "</figure>")


#: Where a finding's lead clause (the fact) ends and its comparison begins.
_CLAUSE = re.compile(r",\s|，|；|; ")


def split_lead_clause(text: str) -> tuple[str, str]:
    """(fact, rest): the text up to the first clause break, then the remainder."""

    match = _CLAUSE.search(text)
    if not match or match.start() < 12:
        return text, ""
    return text[: match.start()], text[match.start():]


def _answer(snapshot: dict) -> str:
    """The direct answer: two to four sentences, every figure from a cited fact."""

    lang = _lang(snapshot)
    answer = snapshot.get("answer") or {}
    if not answer.get("text"):
        return ""
    edited = ' data-edited="model"' if answer.get("basis") == "model" else ""
    return (f'<section class="r-answer" aria-labelledby="ah1"{edited}><h2 class="r-label" '
            f'id="ah1">{_w(lang, "answer")}</h2><p>{mark_simulated(answer["text"])}</p>'
            "</section>")


def _findings(snapshot: dict) -> str:
    lang = _lang(snapshot)
    items = []
    for f in snapshot.get("findings") or []:
        lead, rest = split_lead_clause(f["text"])
        text = f"<strong>{mark_simulated(lead)}</strong>{mark_simulated(rest)}"
        if f.get("implication"):
            text += " " + mark_simulated(f["implication"])
        items.append(f"<li>{text}</li>")
    if not items:
        return ""
    return ('<section class="r-findings" aria-labelledby="kf"><h2 class="r-label" id="kf">'
            f"{_w(lang, 'key_findings')}</h2><ol>{''.join(items)}</ol></section>")


#: Page one, in millimetres (A4 less the 20 mm margins): what the lead exhibit may fill.
PAGE_HEIGHT_MM = 257.0
CONTENT_WIDTH_MM = 174.0


def _lines(text: str, chars_per_line: float) -> int:
    wide = sum(1 for ch in text if ord(ch) > 0x2E80)  # a CJK character is about two wide
    return max(1, math.ceil((len(text) + wide) / chars_per_line))


def front_room_mm(snapshot: dict) -> float:
    """Height left on page one for the lead chart's plot, estimated from the text above it
    (deterministic: the same snapshot gives the same size)."""

    used = 26.0  # masthead and its margin
    if snapshot.get("kind") == "ask" and snapshot.get("question"):
        used += 5.0 + _lines(snapshot["question"], 50) * 7.4 + 2.5
        answer = (snapshot.get("answer") or {}).get("text") or ""
        if answer:
            used += 5.0 + _lines(answer, 84) * 4.94 + 5.0
    else:
        used += _lines(snapshot.get("headline") or "", 44) * 8.1 + 2.5
        if snapshot.get("question"):
            used += 5.0
        if snapshot.get("standfirst"):
            used += _lines(snapshot["standfirst"], 70) * 5.1 + 4.0
    findings = snapshot.get("findings") or []
    if findings:
        used += 10.5
        for f in findings:
            text = f["text"] + " " + (f.get("implication") or "")
            used += _lines(text, 92) * 4.37 + 1.4
    rows = len(snapshot.get("glance") or [])
    if rows:
        used += 9.0 + 4.6 + rows * 4.3 + 4.5 + 3.0
    used += 9.0 + 5.0  # the lead exhibit's caption and source line
    return PAGE_HEIGHT_MM - used - 6.0  # and a margin for the estimate


def _lead_chart(snapshot: dict, shown: list[dict]) -> dict | None:
    """The lead exhibit: the first chart of the first finding that has one (its own exhibit,
    else its section's first chart), else the body's first chart."""

    charts = {c.get("id"): c for s in shown for c in s.get("charts") or []
              if c.get("type") != "sankey"}
    by_section = {s["key"]: [c for c in s.get("charts") or [] if c.get("type") != "sankey"]
                  for s in shown}
    facts = {f.get("id"): f for f in snapshot.get("fact_sheet") or []}
    for finding in snapshot.get("findings") or []:
        for fact_id in finding.get("fact_ids") or []:
            fact = facts.get(fact_id) or {}
            for exhibit in fact.get("exhibits") or []:
                if exhibit in charts:
                    return charts[exhibit]
            if by_section.get(fact.get("section")):
                return by_section[fact["section"]][0]
    return next(iter(charts.values()), None)


# ------------------------------------------------------------------------- body


def _rows(cells: list[str]) -> list[str]:
    return [f'<div class="r-row">{"".join(cells[i:i + 2])}</div>'
            for i in range(0, len(cells), 2)]


def _section(section: dict, numbers: Numbering, refs: dict, snapshot: dict, end: date) -> str:
    """Heading, then the text beside the first half-width exhibit (or full width with its key
    figures when the exhibits pair up), the remaining exhibits in pairs, wide ones and tables
    last: text flows next to its exhibit instead of above an empty quarter page."""

    lang = _lang(snapshot)
    commentary = section["commentary"]
    as_of = snapshot["as_of"]
    cited: list[str] = []
    halves: list[str] = []
    wide: list[str] = []
    for chart in [c for c in section.get("charts") or [] if c.get("type") != "sankey"]:
        number = numbers.figure()
        html = chart_exhibit(chart, number, as_of, end, lang)
        if not html:
            numbers.figures -= 1
            continue
        refs[chart.get("id", f"f{number}")] = f"Figure {number}"
        cited.append(f"{_w(lang, 'figure')} {number}")
        (halves if chart.get("half") else wide).append(html)
    tables = []
    for spec in section.get("tables") or []:
        if not spec.get("rows"):
            continue
        number = numbers.table()
        refs[spec.get("id", f"t{number}")] = f"Table {number}"
        cited.append(f"{_w(lang, 'table')} {number}")
        tables.append(table_exhibit(spec, number, as_of, lang))
    paragraph = " ".join(commentary.get("bullets") or [])
    if cited:
        paragraph += T((" " if paragraph else "") + f"({'; '.join(cited)}.)",
                       f"（{'；'.join(cited)}）")
    text = (f'<div class="r-text"><p><span class="r-lead">{mark_simulated(commentary["headline"])}'
            f"</span> {mark_simulated(paragraph)}</p></div>")
    parts: list[str] = []
    if len(halves) % 2 == 1:
        parts += _rows([text] + halves)
    else:
        parts.append(f'<div class="r-cols">{text}{_side(section)}</div>')
        parts += _rows(halves)
    parts += wide + tables
    edited = ' data-edited="model"' if commentary.get("basis", "rule") == "model" else ""
    title = TITLES_ZH.get(section["key"], section["title"]) if lang != "en" else section["title"]
    return (f'<section class="r-section" id="s-{section["key"]}"{edited} '
            f'aria-labelledby="h-{section["key"]}">'
            f'<h2 id="h-{section["key"]}">{_e(title)}</h2>' + "".join(parts) + "</section>")


def _side(section: dict) -> str:
    rows = []
    for fact in (section.get("facts") or [])[:3]:
        if fact.get("value") is None or not fact.get("indicator", True):
            continue
        c = fact["comparisons"]
        unit = fact["unit"]
        parts = [f"{fmt_number(fact['value'])}{unit}" if unit == "%" else
                 f"{fmt_number(fact['value'])} {unit}"]
        change_unit = T("pts", "个百分点") if c.get("unit") == "points" else c.get("unit") or unit
        if c.get("day") is not None:
            parts.append(f"{T('day', '日')} {fmt_number(c['day'], 'signed')} {change_unit}")
        if c.get("year") is not None:
            parts.append(f"{T('year', '同比')} {fmt_number(c['year'], 'signed')} {change_unit}")
        dag = f'<span class="r-dag">{DAGGER}</span>' if fact["simulated"] else ""
        rows.append(f"<dt>{_e(fact['label'])}</dt><dd>{_e(' · '.join(parts))}{dag}</dd>")
    return f'<aside class="r-side"><dl>{"".join(rows)}</dl></aside>' if rows else "<div></div>"


# ------------------------------------------------------------------------- back matter


def _attributions(snapshot: dict) -> list[str]:
    families: set[str] = set()
    for section in snapshot["sections"]:
        for item in section["evidence"].get("sources") or []:
            if item.get("family") and not item.get("simulated"):
                families.add(item["family"])
    day = fmt_date(snapshot.get("as_of"))
    return [ATTRIBUTIONS[f].format(day=day) for f in sorted(families) if f in ATTRIBUTIONS]


def print_annex(snapshot: dict) -> bool:
    """A printed data annex: on request, and by default for weekly and monthly reports only
    (every series is in the CSV download whatever is printed)."""

    asked = (snapshot.get("plan") or {}).get("annex")
    return bool(asked) if asked is not None else snapshot.get("kind") in {"weekly", "monthly"}


def _sources(snapshot: dict, shown: list[dict]) -> str:
    """One run-in line per source: the sections it feeds, its newest data and state."""

    grouped: dict[tuple, list[str]] = {}
    for section in shown:
        for item in section["evidence"].get("sources") or []:
            flags = ", ".join(k for k in ("simulated", "licensed") if item.get(k))
            key = (item.get("source_system") or "", fmt_short(item.get("as_of")),
                   _state(item.get("state")), flags)
            titles = grouped.setdefault(key, [])
            title = section_title(section["key"], section["title"])
            if title not in titles:
                titles.append(title)
    lines = []
    for (system, newest, state, flags), titles in grouped.items():
        flags = T(flags, flags.replace("simulated", "模拟").replace("licensed", "授权")) \
            if flags else ""
        lines.append(T(f"<p><b>{_e(system)}</b> ({_e(', '.join(titles))}): newest {_e(newest)}, "
                       f'<span class="st-{_e(state)}">{_e(state)}</span>'
                       + (f"; {_e(flags)}" if flags else "") + ".</p>",
                       f"<p><b>{_e(system)}</b>（{_e('、'.join(titles))}）：最新 {_e(newest)}，"
                       f'<span class="st-{_e(state)}">{_e(state)}</span>'
                       + (f"；{_e(flags)}" if flags else "") + "。</p>"))
    return "".join(lines)


def _glossary_terms(entry: str) -> list[str]:
    """The spellings of a glossary entry to look for in the report ("REMIT / UMM" -> both)."""

    return [part.strip() for part in entry.split("/") if part.strip()] if " / " in entry \
        else [entry]


def _back(snapshot: dict, numbers: Numbering, body: str = "") -> str:
    """Methods, sources, editing, classification and disclaimer: run-in paragraphs in three
    columns, one page at most, in the report's language. The glossary lists only the terms the
    report uses."""

    lang = _lang(snapshot)
    shown = [s for s in snapshot["sections"] if s["status"] == "ok"]
    audience = T("internal", "内部") if snapshot["audience"] == "internal" else \
        T("distribution", "对外分发")
    out = ['<section class="r-back" aria-labelledby="mh">',
           f'<h2 id="mh">{_w(lang, "method")}</h2><div class="r-three">']
    out.append(T(
        "<p>Every figure is read from the platform's own stores through the same entitled reads "
        f"as its pages, as of {_e(fmt_datetime(snapshot['as_of']))} UTC, for the "
        f"{audience} audience. Gas days run 06:00 to 06:00 continental time. "
        "Day compares with the previous gas day, week with seven days earlier, year with the "
        "same day a year earlier; a range or norm is shown only where held, with the number of "
        "years. No change is given across a front-month roll.</p>",
        f"<p>所有数字均通过与平台页面相同的授权读取取自平台自有存储，数据截至"
        f"{_e(fmt_datetime(snapshot['as_of']))} UTC，读者范围为{audience}。燃气日为欧洲大陆时间"
        "06:00至次日06:00。日变化对比前一燃气日，周变化对比七天前，同比对比一年前同日；仅在持有"
        "数据时给出区间或常态，并注明年数。近月合约换月时不计算跨合约变化。</p>"))
    methods: dict[str, dict] = {}
    for section in shown:
        for method in section["evidence"].get("methods") or []:
            methods.setdefault(method["key"], method)
    if methods:
        plain = [m for m in methods.values() if not m["key"].startswith("forecast_")]
        forecast = [m for m in methods.values() if m["key"].startswith("forecast_")]
        out.append(f"<h3>{T('How each indicator is computed', '各指标的计算方法')}</h3>" + "".join(
            f"<p><b>{_e(_method(m)[0])}{T('.', '。')}</b> {_e(_method(m)[1])}</p>" for m in plain)
            + (f"<p><b>{T('Forecast methods.', '预测方法。')}</b> " + T("; ", "；").join(
                f"{_e(_method(m)[0])}{T(': ', '：')}{_e(_method(m)[1])}" for m in forecast)
               + T(".", "。") + "</p>" if forecast else ""))
    if any(f.get("forecast") for f in snapshot.get("fact_sheet") or []):
        out.append(T("<p><b>Forecasts.</b> Every forecast is labelled as one where it is stated, "
                     "with its method above and its limitation beside it; no range is "
                     "produced.</p>",
                     "<p><b>预测。</b>每项预测在出现处均标明为预测，方法见上，局限性随附其旁；"
                     "不给出区间。</p>"))
    revisions = [(section_title(s["key"], s["title"]),
                  (s["evidence"].get("revisions") or {}).get("count"))
                 for s in shown if s["evidence"].get("revisions")]
    counted = [(t, c) for t, c in revisions if c is not None]
    out.append(f"<h3>{T('Revisions', '修订')}</h3><p>"
               + T("Providers revise published flows, storage and LNG; each replaced value is "
                   "kept. ", "数据提供方会修订已发布的流量、储气与 LNG 数据；被替换的值均予保留。")
               + (T("Revisions received since the previous issue: ", "自上一期以来收到的修订：")
                  + T("; ", "；").join(f"{_e(t)} {c}" for t, c in counted) + T(".", "。")
                  if counted else T("First issue of this kind: no earlier issue to compare with.",
                                    "此类报告的首期：无可比较的上一期。") if revisions else "")
               + "</p>")
    sources = _sources(snapshot, shown)
    if sources:
        out.append(f"<h3>{T('Sources and freshness', '来源与时效')}</h3>" + sources)
    attributions = _attributions(snapshot)
    if attributions:
        out.append(f"<h3>{T('Attribution', '署名')}</h3>"
                   + "".join(f"<p>{_e(a)}</p>" for a in attributions))
    omitted = snapshot.get("omitted") or []
    if omitted:
        out.append(f"<h3>{T('Not included', '未包含的内容')}</h3>" + "".join(
            f"<p><b>{_e(section_title(item.get('key') or '', item['title']))}{T(':', '：')}</b> "
            f"{_e(omitted_reason(item['reason']).rstrip('.。'))}{T('.', '。')}</p>"
            for item in omitted))
    used = [(a, b) for a, b in GLOSSARY
            if any(re.search(rf"(?<![\w-]){re.escape(term)}(?![\w-])", body)
                   for term in _glossary_terms(a))]
    if used:
        out.append(f"<h3>{T('Abbreviations and units', '缩写与单位')}</h3><p>" + " ".join(
            f"<b>{_e(GLOSSARY_ZH.get(a, (a, b))[0] if lang != 'en' else a)}</b> "
            f"{_e(GLOSSARY_ZH.get(a, (a, b))[1] if lang != 'en' else b)}" for a, b in used)
            + "</p>")
    record = snapshot.get("editorial") or {}
    heading = f"<h3>{T('Editing, data and use', '编辑、数据与用途')}</h3>"
    if record.get("basis") == "model":
        kept = sum(1 for v in (record.get("elements") or {}).values() if v.get("ok"))
        total = len(record.get("elements") or {})
        temperature = record.get("temperature")
        out.append(heading + T(
            f"<p><b>Editing.</b> Edited by the AI model {_e(record.get('model'))} under "
            f"directive {_e(record.get('directive'))}"
            + (f" at temperature {_e(temperature)}" if temperature is not None else "")
            + f": {kept} of {total} elements passed the checks and are the model's wording; the "
            "others are rule-written. No figure was written by the model.</p>",
            f"<p><b>编辑。</b>由 AI 模型 {_e(record.get('model'))} 依据编辑指引 v"
            f"{_e(record.get('directive'))}"
            + (f"（温度 {_e(temperature)}）" if temperature is not None else "")
            + f"编辑：{total}个元素中{kept}个通过核对，采用模型措辞；其余为规则撰写。所有数字均非"
            "模型所写。</p>"))
    else:
        out.append(heading + T(
            "<p><b>Editing.</b> Rule-edited: the findings, their order and every sentence were "
            "selected and written by fixed rules from the figures.</p>",
            "<p><b>编辑。</b>规则编辑：要点、其顺序及每个句子均由固定规则依据数字选择和撰写。</p>"))
    out.append(T("<p><b>Data.</b> ", "<p><b>数据。</b>")
               + (T("The data annex follows: each series for the report's own window. ",
                    "随后为数据附录：各序列覆盖本期时段。")
                  if print_annex(snapshot) else
                  T("Every series behind the exhibits is in the CSV download (Download data in "
                    "the viewer); a printed data annex is available on request. ",
                    "图表背后的全部序列均可通过 CSV 下载获取（查看器中的“下载数据”）；"
                    "如需可打印数据附录。"))
               + "</p>")
    licensed = (snapshot.get("licensed") or {}).get("sources")
    classification = (CLASSIFICATION_ZH if zh() else CLASSIFICATION).get(
        snapshot["audience"], T("INTERNAL", "内部"))
    out.append(f"<p><b>{T('Classification.', '密级。')}</b> {_e(classification)}{T('. ', '。')}"
               + (T("For the desk and risk; not for distribution outside the firm. ",
                    "供交易台与风控使用；不得在公司外分发。")
                  if snapshot["audience"] == "internal" else
                  T("May be distributed outside the firm; it holds no position, P&L, limit, "
                    "counterparty or contract term. ",
                    "可在公司外分发；不含头寸、损益、限额、交易对手或合同条款。"))
               + (T(f"Contains licensed data from {_e(', '.join(licensed))}: internal use only. ",
                    f"含有来自{_e('、'.join(licensed))}的授权数据：仅限内部使用。")
                  if licensed else "")
               + (T(f"{DAGGER} marks simulated demonstration values: not market data. ",
                    f"{DAGGER} 表示模拟演示数值，非市场数据。")
                  if snapshot.get("simulated") else "") + "</p>")
    out.append(f"<p><b>{T('Disclaimer.', '免责声明。')}</b> {_e(T(DISCLAIMER, DISCLAIMER_ZH))}"
               "</p>"
               f"<p>{T('Report', '报告')} {_e(snapshot['report_id'])} · {T('template', '模板')} "
               f"{_e(snapshot.get('template_version', TEMPLATE_VERSION))}.</p></div></section>")
    return "".join(out)


def _method(method: dict) -> tuple[str, str]:
    """A method note's title and text in the report's language."""

    title = method["title"]
    if method["key"].startswith("forecast_"):
        title = title.split(":", 1)[-1].strip()
    if not zh():
        return title, method["text"]
    return METHODS_ZH.get(method["key"], (title, method["text"]))


def section_title(key: str, title: str) -> str:
    return TITLES_ZH.get(key, TITLES_ZH.get(title, title)) if zh() else title


def omitted_reason(reason: str) -> str:
    """A reason a section is not included, in the report's language."""

    if not zh():
        return reason
    for en, cn in REASONS_ZH.items():
        if reason.startswith(en):
            return cn
    return reason


def _annex(snapshot: dict, numbers: Numbering) -> str:
    """Narrow series tables flow in three columns, five-column ones in two, wider ones (a
    schedule, LNG by country) run full width."""

    if not print_annex(snapshot):
        return ""
    lang = _lang(snapshot)
    blocks: list[str] = []
    mid: list[str] = []
    wide: list[str] = []
    for section in snapshot["sections"]:
        if section["status"] != "ok":
            continue
        for spec in section.get("annex") or []:
            if not spec.get("rows"):
                continue
            number = numbers.table()
            rows = [r for r in spec["rows"] if not spec.get("print_from")
                    or str(r.get("day", "")) >= spec["print_from"]]
            spec = {**spec, "rows": rows}
            target = wide if len(spec["columns"]) > 5 else mid if len(spec["columns"]) > 4 \
                else blocks
            target.append(f'<figure id="t{number}">'
                          + _furniture(f"{_w(lang, 'table')} {number}",
                                       _tw(spec.get("caption", "")),
                                       f"{section_title(section['key'], section['title'])}"
                                       f"{T(': ', '：')}{len(rows)} "
                                       f"{_w(lang, 'rows_newest')}")
                          + table_html(spec) + "</figure>")
    if not blocks and not mid and not wide:
        return ""
    return ('<section class="r-annex" aria-labelledby="ah"><h2 id="ah" class="r-label">'
            f'{_w(lang, "annex")}</h2><div class="r-flow">{"".join(blocks)}</div>'
            f'<div class="r-flow r-flow-2">{"".join(mid)}</div>{"".join(wide)}</section>')


def _data_block(snapshot: dict) -> str:
    """The annex series as JSON for the viewer's CSV download (data, never executed)."""

    tables = [{"section": s["key"], "caption": spec.get("caption"),
               "columns": [c["key"] for c in spec["columns"]], "rows": spec["rows"]}
              for s in snapshot["sections"] if s["status"] == "ok"
              for spec in s.get("annex") or []]
    text = json.dumps({"report_id": snapshot["report_id"], "tables": tables},
                      ensure_ascii=False, default=str, separators=(",", ":"))
    return ('<script type="application/json" id="report-data">'
            + text.replace("</", "<\\/") + "</script>")


#: Lead plot height in viewBox units: at least a 30 mm plot, at most 80 mm.
LEAD_MIN, LEAD_MAX = 110, 295


def render_report(snapshot: dict) -> str:
    """The report's HTML, in the snapshot's language. Deterministic in ``snapshot``."""

    with writing(snapshot.get("language")):
        return _render_report(snapshot)


def _render_report(snapshot: dict) -> str:
    lang = _lang(snapshot)
    numbers = Numbering()
    refs: dict[str, str] = {}
    end = date.fromisoformat((snapshot.get("period") or {}).get("end") or snapshot["as_of"][:10])
    shown = [s for s in snapshot["sections"] if s["status"] == "ok"]
    order = snapshot.get("section_order") or []
    if order:
        rank = {key: i for i, key in enumerate(order)}
        shown = sorted(shown, key=lambda s: rank.get(s["key"], 99))
        shown = [s for s in shown if s["key"] in rank]
    # Page one: masthead, headline, standfirst, findings, At a glance, the lead exhibit sized
    # to fill what is left of the page.
    asked = snapshot.get("kind") == "ask" and bool(snapshot.get("question"))
    if asked:
        # An asked report is titled by its question and answers it first.
        front = [_masthead(snapshot), f'<p class="r-label">{_w(lang, "question")}</p>',
                 f'<h1 class="r-question">{_e(snapshot["question"])}</h1>', _answer(snapshot)]
    else:
        front = [_masthead(snapshot), f"<h1>{mark_simulated(snapshot['headline'])}</h1>"]
        if snapshot.get("question"):
            front.append(f'<p class="r-label">{_w(lang, "question")} '
                         f'{_e(snapshot["question"])}</p>')
        if snapshot.get("standfirst"):
            front.append(f'<p class="r-standfirst">{mark_simulated(snapshot["standfirst"])}</p>')
    front.append(_findings(snapshot))
    front.append(_glance(snapshot, numbers.table()))
    lead_chart = _lead_chart(snapshot, shown)
    if lead_chart:
        room = front_room_mm(snapshot)
        height = max(LEAD_MIN, min(LEAD_MAX, round(room * 640 / CONTENT_WIDTH_MM)))
        number = numbers.figure()
        html = chart_exhibit({**lead_chart, "half": False, "lead": True, "height": height},
                             number, snapshot["as_of"], end, lang)
        if html:
            front.append(html)
            refs[lead_chart["id"]] = f"Figure {number}"
        else:
            numbers.figures -= 1
            lead_chart = None
    # Body: groups in the house order (or the editor's order), each section once.
    body: list[str] = []
    if snapshot.get("kind") == "monthly":
        body.append(f'<nav class="r-contents" aria-label="Contents"><p class="r-label">'
                    f'{_w(lang, "contents")}</p><ol>'
                    + "".join(f"<li>{_e(s['title'])}</li>" for s in shown)
                    + f"<li>{_w(lang, 'method')}</li>"
                    + (f"<li>{_w(lang, 'annex')}</li>" if print_annex(snapshot) else "")
                    + "</ol></nav>")
    groups = GROUPS if not order else tuple(dict.fromkeys(s["group"] for s in shown))
    if asked:
        # The evidence, in order of relevance to the question (no house grouping).
        groups = (None,)
        body.append(f'<p class="r-label r-group">{_w(lang, "evidence")}</p>')
    for group in groups:
        members = [s for s in shown if group is None or s["group"] == group]
        if not members:
            continue
        if group is not None:
            label = TITLES_ZH.get(group, group) if lang != "en" else group
            body.append(f'<p class="r-label r-group">{_e(label)}</p>')
        for section in members:
            if lead_chart is not None:
                section = {**section, "charts": [c for c in section.get("charts") or []
                                                 if c is not lead_chart
                                                 and c.get("id") != lead_chart["id"]]}
            body.append(_section(section, numbers, refs, snapshot, end))
    if asked and snapshot.get("cannot_tell"):
        body.append('<section class="r-watch r-cannot" aria-labelledby="ch"><h2 class="r-label" '
                    f'id="ch">{_w(lang, "cannot_tell")}</h2><ul>' + "".join(
                        f"<li>{mark_simulated(item)}</li>" for item in snapshot["cannot_tell"])
                    + "</ul></section>")
    # What to watch never repeats a sentence the body already prints.
    printed = "".join(body)
    watch = [w for w in snapshot.get("watch") or []
             if mark_simulated(w["text"]).rstrip(".") not in printed]
    if watch:
        body.append('<section class="r-watch" aria-labelledby="wh"><h2 class="r-label" id="wh">'
                    f"{_w(lang, 'watch')}</h2><ul>" + "".join(
                        f"<li>{mark_simulated(w['text'])}</li>" for w in watch) + "</ul></section>")
    back = _back(snapshot, numbers, "".join(front + body)) + _annex(snapshot, numbers)
    title = snapshot["title"]
    demo_class = ' class="r-demo"' if snapshot.get("simulated") else ""
    mark = ('<div class="r-mark" aria-hidden="true">'
            f'{T("Demonstration · simulated data", "演示 · 模拟数据")}</div>'
            if snapshot.get("simulated") else "")
    html_lang = "zh-CN" if lang != "en" else "en"
    return (
        f'<!doctype html><html lang="{html_lang}"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<meta name="generator" content="'
        f'{_e(snapshot.get("template_version", TEMPLATE_VERSION))}">'
        f"<title>{_e(title)}</title><style>{_css(snapshot)}</style></head>"
        f"<body{demo_class}>{mark}<main>"
        f'<article class="r-sheet r-front" aria-label="Summary">{"".join(front)}</article>'
        f'<article class="r-sheet r-body" aria-label="Report">{"".join(body)}</article>'
        f'<article class="r-sheet r-back-sheet" aria-label="Methodology and data">{back}'
        f"</article></main>{_data_block(snapshot)}</body></html>"
    )


__all__ = ["front_room_mm", "print_annex", "render_report", "split_lead_clause", "table_html"]
