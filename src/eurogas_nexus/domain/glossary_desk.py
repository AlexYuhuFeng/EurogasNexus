# ruff: noqa: E501 - bilingual definition text is kept whole rather than split mid-sentence
"""Desk glossary: the vocabulary a European gas desk uses daily, with units and examples.

Bilingual (English and Simplified Chinese) definitions written for the people who use the
product: what the term means on a trading desk, its unit, how it is calculated where that
matters, a short worked example, and where it appears in the application. Regulation
references name the act or code, not a summary of it.
"""

from __future__ import annotations

from eurogas_nexus.domain.glossary import GlossaryTerm


def _t(
    term_id: str,
    term: str,
    category: str,
    en: str,
    zh: str,
    *,
    aliases: tuple[str, ...] = (),
    related: tuple[str, ...] = (),
    sources: tuple[str, ...] = (),
    unit: str = "",
    formula: str = "",
    example_en: str = "",
    example_zh: str = "",
    where: tuple[str, ...] = (),
) -> GlossaryTerm:
    return GlossaryTerm(
        term_id=term_id,
        term=term,
        category=category,
        definition_en=en,
        definition_zh_cn=zh,
        aliases=list(aliases),
        related_terms=list(related),
        source_refs=list(sources),
        unit=unit,
        formula=formula,
        example_en=example_en,
        example_zh_cn=example_zh,
        where_in_app=list(where),
    )


def desk_glossary_terms() -> list[GlossaryTerm]:
    """Terms beyond the institutional baseline, grouped by what the desk does with them."""

    return [
        # ------------------------------------------------------------------- products
        _t(
            "product-gas-day",
            "Gas day",
            "product",
            "The 24-hour delivery period gas is traded and balanced in: 06:00 to 06:00 local "
            "time in continental Europe (05:00 to 05:00 UTC in winter), 05:00 to 05:00 UK time "
            "in Great Britain.",
            "天然气交易与平衡的 24 小时交付周期：欧洲大陆为当地时间 06:00 至次日 06:00（冬令时 "
            "UTC 05:00 至 05:00），英国为英国时间 05:00 至次日 05:00。",
            related=("Day-ahead", "Within-day", "Gas year"),
            sources=("Regulation (EU) 2017/459 (CAM NC)",),
            where=("Top bar: gas day",),
        ),
        _t(
            "product-gas-year",
            "Gas year",
            "product",
            "1 October to 30 September. Capacity, tariffs and many supply contracts run by gas "
            "year; 'GY 2026/27' starts on 1 October 2026.",
            "每年 10 月 1 日至次年 9 月 30 日。容量、费率及许多供应合同按燃气年计；"
            "“GY 2026/27”自 2026 年 10 月 1 日开始。",
            aliases=("GY",),
            related=("Gas day", "Season"),
            where=("Portfolio → Resources",),
        ),
        _t(
            "product-da",
            "Day-ahead",
            "product",
            "Gas for delivery on the next gas day, the most liquid spot product. Weekend and "
            "holiday gas trades as separate products (Weekend, Saturday, Sunday).",
            "次一燃气日交付的天然气，为流动性最好的现货产品；周末与节假日另有独立产品（周末、"
            "周六、周日）。",
            aliases=("DA",),
            related=("Within-day", "Weekend", "Sell-down"),
            where=("Market → Curves",),
        ),
        _t(
            "product-wd",
            "Within-day",
            "product",
            "Gas for delivery during the current gas day. Used to balance a position as the day "
            "unfolds; thinner and usually wider than day-ahead.",
            "当前燃气日内交付的天然气，用于随当日情况平衡头寸；流动性通常低于日前、买卖价差更大。",
            aliases=("WD", "Rest of day"),
            related=("Day-ahead", "Imbalance", "Sell-down"),
            where=("Market → Curves",),
        ),
        _t(
            "product-bom",
            "Balance of month",
            "product",
            "Delivery on every remaining gas day of the current month, from the next gas day.",
            "自下一燃气日起至本月最后一天的每日交付。",
            aliases=("BOM",),
            related=("Month-ahead",),
            where=("Market → Curves",),
        ),
        _t(
            "product-ma",
            "Month-ahead",
            "product",
            "Delivery on every gas day of the next calendar month at a flat daily rate; the "
            "benchmark contract for most European hubs (front month, M+1).",
            "下一个日历月每个燃气日按固定日量交付；为大多数欧洲枢纽的基准合约（近月，M+1）。",
            aliases=("MA", "M+1", "Front month"),
            related=("Forward curve", "Settlement price"),
            where=("Market → Curves", "Portfolio → Exposure"),
        ),
        _t(
            "product-season",
            "Season",
            "product",
            "Summer runs April to September, Winter October to March. 'Win-26' is October 2026 "
            "to March 2027. The summer-winter spread drives storage economics.",
            "夏季为 4 月至 9 月，冬季为 10 月至次年 3 月。“Win-26”指 2026 年 10 月至 2027 年 "
            "3 月。夏冬价差决定储气经济性。",
            aliases=("Sum", "Win"),
            related=("Storage", "Gas year"),
            where=("Market → Curves",),
        ),
        _t(
            "product-cal",
            "Calendar year",
            "product",
            "Delivery on every gas day of a calendar year (January to December).",
            "一个日历年（1 月至 12 月）每个燃气日的交付。",
            aliases=("Cal",),
            where=("Market → Curves",),
        ),
        _t(
            "product-forward-curve",
            "Forward curve",
            "price",
            "The price for each future delivery month, built from month, quarter, season and "
            "year quotes; longer products are split into months so that their average matches "
            "the quoted price. Positions are marked on it.",
            "未来各交付月份的价格，由月、季、季节与年度报价构建；较长产品按月拆分，使其平均值等于"
            "报价。头寸按此曲线估值。",
            related=("Mark-to-market", "Month-ahead"),
            where=("Portfolio → Exposure",),
        ),
        _t(
            "price-spread-location",
            "Location spread",
            "price",
            "The price difference between two hubs for the same delivery period, e.g. NBP minus "
            "TTF in EUR/MWh after converting pence per therm. It must exceed the cost of moving "
            "gas between them for a physical arbitrage to pay.",
            "同一交付期两个枢纽之间的价差，如 NBP 减 TTF（便士/撒姆换算为欧元/MWh 后）。只有超过"
            "两地之间的输气成本，实物套利才有利可图。",
            related=("Route cost", "Interconnector"),
            where=("Strategy Lab → Spread",),
        ),
        _t(
            "price-time-spread",
            "Time spread",
            "price",
            "The price difference between two delivery periods at one hub, e.g. Winter minus "
            "Summer; the value of storage or of shifting delivery.",
            "同一枢纽两个交付期之间的价差，如冬季减夏季；反映储气或调整交付时间的价值。",
            aliases=("Calendar spread",),
            related=("Season", "Storage"),
        ),
        _t(
            "price-ptherm",
            "Pence per therm",
            "price",
            "The NBP price unit. 1 therm = 0.0293071 MWh, so 100 p/th = 34.12 GBP/MWh.",
            "NBP 的报价单位。1 撒姆 = 0.0293071 MWh，因此 100 便士/撒姆 = 34.12 英镑/MWh。",
            aliases=("p/th",),
            unit="GBp/th",
            formula="GBP/MWh = (p/th ÷ 100) ÷ 0.0293071",
            example_en="85.50 p/th = 29.17 GBP/MWh",
            example_zh="85.50 便士/撒姆 = 29.17 英镑/MWh",
            where=("Market → Curves → converter",),
        ),
        _t(
            "price-mmbtu",
            "MMBtu",
            "price",
            "One million British thermal units, the unit LNG and Henry Hub are priced in. "
            "1 MMBtu = 0.29307107 MWh; 1 USD/MMBtu = 3.412 USD/MWh.",
            "一百万英热单位，LNG 与 Henry Hub 的计价单位。1 MMBtu = 0.29307107 MWh；"
            "1 美元/MMBtu = 3.412 美元/MWh。",
            unit="MMBtu",
            formula="EUR/MWh = USD/MMBtu ÷ 0.29307107 ÷ EURUSD",
            where=("Portfolio → Routes → LNG cargo bid",),
        ),
        # ----------------------------------------------------------------- contracts
        _t(
            "contract-dcq",
            "Daily contract quantity",
            "contract",
            "The quantity a supply contract delivers per gas day at its base rate, in MWh/d.",
            "供应合同在基准费率下每个燃气日交付的数量，单位 MWh/日。",
            aliases=("DCQ",),
            unit="MWh/d",
            related=("ACQ", "Swing", "Nomination"),
            where=("Portfolio → Resources",),
        ),
        _t(
            "contract-acq",
            "Annual contract quantity",
            "contract",
            "The quantity a supply contract delivers over its contract year; the buyer must take "
            "at least the minimum (take-or-pay) and may take up to the maximum.",
            "供应合同在合同年度内的交付量；买方至少须提取最低量（照付不议），最多可提取上限量。",
            aliases=("ACQ",),
            unit="MWh",
            related=("DCQ", "Take-or-pay", "Swing"),
        ),
        _t(
            "contract-swing",
            "Swing",
            "contract",
            "The flexibility to nominate more or less than DCQ each day, e.g. 80 to 110 % of "
            "DCQ. Swing has option value: it lets the buyer take more when prices are high.",
            "每日提名量可高于或低于日合同量的灵活性，如日合同量的 80% 至 110%。摇摆具有期权价值："
            "价格高时可多提。",
            aliases=("Flexibility", "Delivery tolerance"),
            related=("DCQ", "Take-or-pay"),
            where=("Portfolio → Resources → Delivery against nominations",),
        ),
        _t(
            "contract-top",
            "Take-or-pay",
            "contract",
            "The buyer pays for the minimum annual quantity whether or not it takes it, usually "
            "with the right to take the paid gas later (make-up).",
            "无论是否提取，买方都须为年度最低量付款，通常可在以后提取已付款的气量（补提）。",
            aliases=("ToP",),
            related=("ACQ", "Swing"),
        ),
        _t(
            "contract-renomination",
            "Renomination",
            "contract",
            "A change to a nomination during the gas day, within the lead time and limits the "
            "contract or the TSO allows.",
            "在燃气日内、在合同或 TSO 允许的提前期与范围内对提名的修改。",
            related=("Nomination", "Allocation"),
            sources=("Regulation (EU) No 312/2014 (BAL NC)",),
        ),
        _t(
            "contract-allocation",
            "Allocation",
            "contract",
            "The quantity the TSO or upstream system finally attributes to a shipper at a point "
            "for a gas day. Allocated minus nominated is the deviation the desk balances.",
            "TSO 或上游系统最终分配给托运人在某点某燃气日的气量。分配量减提名量即交易台需平衡的偏差。",
            related=("Nomination", "Imbalance"),
            formula="deviation = allocated − nominated",
            where=("Portfolio → Resources → Delivery against nominations",),
        ),
        _t(
            "contract-des-fob",
            "DES / FOB",
            "contract",
            "Delivered ex ship: the seller delivers the LNG at the buyer's terminal and bears "
            "shipping. Free on board: the buyer takes the LNG at the loading port and arranges "
            "shipping. A DES bid already includes the voyage.",
            "目的港船上交货（DES）：卖方在买方接收站交付并承担运输；装运港船上交货（FOB）：买方在"
            "装货港提货并自行安排运输。DES 报价已包含航程成本。",
            aliases=("DES", "FOB"),
            related=("Netback", "Regas slot"),
            where=("Portfolio → Routes → LNG cargo bid",),
        ),
        # ---------------------------------------------------------------- balancing
        _t(
            "balancing-zone",
            "Balancing zone",
            "balancing",
            "The entry-exit system a shipper must keep in balance each gas day; it has one "
            "virtual trading point, e.g. THE for Germany, TTF for the Netherlands.",
            "托运人每个燃气日须保持平衡的入口-出口系统，对应一个虚拟交易点，如德国 THE、荷兰 TTF。",
            related=("Virtual trading point", "Imbalance"),
            sources=("Regulation (EU) No 312/2014 (BAL NC)",),
        ),
        _t(
            "balancing-imbalance",
            "Imbalance",
            "balancing",
            "A shipper's inputs minus offtakes in a balancing zone at the end of the gas day. "
            "The TSO cashes it out at a penalty price: buying a shortfall above the market, "
            "taking a surplus below it.",
            "托运人在平衡区燃气日结束时的注入量减提取量。TSO 以惩罚性价格结算：短缺按高于市场的价格"
            "买入，盈余按低于市场的价格收取。",
            related=("Cash-out price", "Within-day", "Sell-down"),
            sources=("Regulation (EU) No 312/2014 (BAL NC)",),
        ),
        _t(
            "balancing-cashout",
            "Cash-out price",
            "balancing",
            "The price at which the TSO settles a daily imbalance: the marginal buy price for a "
            "short shipper, the marginal sell price for a long one (in GB, SMP buy and sell; "
            "SAP is the average).",
            "TSO 结算每日不平衡的价格：短缺托运人按边际买入价，盈余托运人按边际卖出价（英国为 SMP "
            "买/卖价，SAP 为均价）。",
            aliases=("SMP", "SAP", "Marginal price"),
            related=("Imbalance",),
            where=("Portfolio → Resources → Tomorrow's sell-down",),
        ),
        _t(
            "balancing-vtp",
            "Virtual trading point",
            "balancing",
            "The notional point in a balancing zone where title to gas changes hands without "
            "regard to physical location; hubs such as TTF, THE and PEG are VTPs.",
            "平衡区内与物理位置无关、完成天然气所有权转移的虚拟点；TTF、THE、PEG 等枢纽即为虚拟交易点。",
            aliases=("VTP",),
            related=("Balancing zone",),
        ),
        _t(
            "concept-sell-down",
            "Sell-down",
            "balancing",
            "Selling a long physical position in the market, typically mostly day-ahead with a "
            "buffer kept for within-day, sized by how uncertain tomorrow's delivery is and what "
            "a shortfall or surplus would cost.",
            "在市场上出售多头实物头寸，通常主要在日前出售，并按明日交付的不确定性及短缺/盈余成本"
            "保留部分到日内。",
            related=("Day-ahead", "Within-day", "Imbalance"),
            formula="sell Q* = μ + σ·Φ⁻¹(c_under / (c_under + c_over))",
            where=("Portfolio → Resources → Tomorrow's sell-down",),
        ),
        # ---------------------------------------------------------------- capacity
        _t(
            "capacity-entry-exit",
            "Entry-exit system",
            "capacity",
            "Capacity is booked separately to enter and to exit a balancing zone; inside it gas "
            "moves freely. A route across borders needs exit from one zone and entry into the "
            "next, usually as a bundled product at an interconnection point.",
            "入口与出口容量分别预订，平衡区内天然气自由流动。跨境线路需要在互联点预订前一区的出口与"
            "后一区的入口，通常为捆绑产品。",
            related=("Interconnection point", "Bundled capacity", "Tariff"),
            sources=("Regulation (EU) 2024/1789",),
        ),
        _t(
            "capacity-bundled",
            "Bundled capacity",
            "capacity",
            "Exit and entry capacity at an interconnection point sold as one product, as the "
            "capacity allocation code requires where both sides have capacity.",
            "互联点的出口与入口容量作为一个产品出售，在两侧均有容量时为容量分配规范所要求。",
            related=("PRISMA", "Entry-exit system"),
            sources=("Regulation (EU) 2017/459 (CAM NC)",),
        ),
        _t(
            "capacity-prisma",
            "PRISMA",
            "capacity",
            "The booking platform on which most European TSOs auction capacity (yearly, "
            "quarterly, monthly, day-ahead and within-day).",
            "大多数欧洲 TSO 拍卖容量（年度、季度、月度、日前与日内）的预订平台。",
            related=("Annual yearly auction", "Bundled capacity"),
        ),
        _t(
            "capacity-aya",
            "Annual yearly auction",
            "capacity",
            "The auction of yearly capacity products for the coming gas years, held on the first "
            "Monday of July. Final tariffs must be published at least 30 days before it.",
            "对未来燃气年年度容量产品的拍卖，于每年 7 月第一个星期一举行。最终费率须至少提前 30 天公布。",
            related=("NC TAR", "Tariff publication"),
            sources=("Regulation (EU) 2017/459 (CAM NC)",),
            where=("Portfolio → Routes → Tariff publications",),
        ),
        _t(
            "regulation-nc-tar",
            "NC TAR",
            "regulation",
            "The EU network code on harmonised transmission tariff structures. TSOs publish "
            "reserve prices for the coming gas year at least 30 days before the annual yearly "
            "auction; many publish indicative prices first.",
            "欧盟输气费率结构协调网络规范。TSO 须在年度拍卖前至少 30 天公布下一燃气年的底价；"
            "许多 TSO 先公布指示性价格。",
            aliases=("Tariff network code",),
            related=("Annual yearly auction", "Tariff"),
            sources=("Regulation (EU) 2017/460",),
            where=("Portfolio → Routes → Tariff publications",),
        ),
        # ---------------------------------------------------------------------- LNG
        _t(
            "lng-regas-slot",
            "Regas slot",
            "lng",
            "The right to berth one LNG cargo at a terminal, store it and send it out over a set "
            "number of days. Bought as long-term capacity or as a spot slot; prices follow the "
            "terminal's regime (regulated tariff, auction or negotiated).",
            "在接收站停靠一艘 LNG 船、储存并在规定天数内外输的权利。可作为长期容量或现货舱位购买；"
            "价格取决于接收站的定价方式（受监管费率、拍卖或协商）。",
            aliases=("Slot", "Unloading slot"),
            related=("Send-out", "SMART SPOT", "Boil-off"),
            where=("Portfolio → Routes → LNG cargo bid",),
        ),
        _t(
            "lng-smart-spot",
            "SMART SPOT",
            "lng",
            "Elengy's last-minute capacity at the French regulated terminals: booked after the "
            "20th of the month before unloading, at a lower price than standard capacity.",
            "Elengy 法国受监管接收站的临时容量：在卸货前一月 20 日之后预订，价格低于标准容量。",
            related=("Regas slot",),
            sources=("Elengy ATTM7 tariff (CRE deliberation 2025-41)",),
            where=("Portfolio → Routes → LNG cargo bid",),
        ),
        _t(
            "lng-boil-off",
            "Boil-off",
            "lng",
            "LNG that evaporates during the voyage, about 0.08 to 0.15 % of the cargo a day on "
            "modern ships; used as fuel or reliquefied. A longer voyage lands less gas.",
            "航行中蒸发的 LNG，现代船舶每天约为货量的 0.08% 至 0.15%，用作燃料或再液化。航程越长，"
            "到岸气量越少。",
            aliases=("BOG", "Boil-off rate"),
            unit="%/day",
            related=("Heel", "Netback"),
        ),
        _t(
            "lng-heel",
            "Heel",
            "lng",
            "LNG kept in the tanks after discharge to keep them cold for the return voyage.",
            "卸货后保留在船舱中、用于返程保持舱体低温的 LNG。",
            related=("Boil-off",),
        ),
        _t(
            "lng-gas-in-kind",
            "Gas in kind",
            "lng",
            "Gas the terminal keeps from each cargo to run the terminal (fuel and losses), as a "
            "percentage of the quantity unloaded, e.g. 1.30 % at Zeebrugge.",
            "接收站从每船货物中保留用于运营（燃料与损耗）的气量，按卸货量百分比计，如泽布吕赫为 1.30%。",
            aliases=("Fuel retention", "Gas taken off"),
            unit="%",
            where=("Portfolio → Routes → LNG cargo bid",),
        ),
        _t(
            "lng-max-bid",
            "Maximum DES bid",
            "lng",
            "The most the firm can pay for a delivered cargo at a terminal: the hub price for the "
            "arrival month on the gas sent out, less regas, entry, fuel, port, boil-off and "
            "charter, less the target margin, per MWh of cargo bought.",
            "公司在某接收站可为到岸货物支付的最高价格：到港月枢纽价格乘以外输气量，减去再气化、入网、"
            "燃料、港口、蒸发与租船成本及目标利润，按每 MWh 采购量计。",
            related=("Netback", "DES / FOB", "Regas slot"),
            formula="bid = (sent-out × hub − costs) ÷ cargo − margin",
            where=("Portfolio → Routes → LNG cargo bid",),
        ),
        # --------------------------------------------------------------------- risk
        _t(
            "risk-hedge-ratio",
            "Hedge ratio",
            "risk",
            "Financial cover as a share of a physical position for the same hub and month: a "
            "long of 100 GWh sold forward by 80 GWh is 80 % hedged. Mandates may cap it (a hedge "
            "above the physical position is speculation) or set a floor.",
            "同一枢纽同一月份的金融对冲量占实物头寸的比例：100 GWh 多头远期卖出 80 GWh 即 80% 套保。"
            "授权可设上限（超过实物头寸即为投机）或下限。",
            formula="hedge ratio = −financial ÷ physical",
            related=("Mandate", "Mark-to-market"),
            where=("Portfolio → Exposure",),
        ),
        _t(
            "risk-var",
            "Value at risk",
            "risk",
            "The loss on today's open position that observed daily price moves exceed only on a "
            "given share of days (95 % VaR: one day in twenty). Here historical simulation over "
            "the hubs' own price history.",
            "当前未平仓头寸在给定置信度下的损失（95% VaR：二十天中只有一天超过）。此处采用各枢纽自身"
            "价格历史的历史模拟法。",
            aliases=("VaR",),
            unit="currency",
            related=("Mark-to-market",),
            where=("Portfolio → Exposure",),
        ),
        _t(
            "risk-credit-exposure",
            "Credit exposure",
            "risk",
            "What the firm would lose if a counterparty defaulted today: the cost of replacing "
            "the undelivered deals at today's prices (netted under a master agreement) plus gas "
            "delivered but not yet paid for, less collateral held.",
            "交易对手今天违约时公司的损失：按当前价格替换未交付交易的成本（主协议下净额结算），加上已"
            "交付未付款的气款，减去持有的抵押品。",
            related=("Credit line", "Collateral", "EFET"),
            formula="net = max(0, replacement) + receivables − collateral",
            where=("Portfolio → Exposure → Credit and mandates",),
        ),
        _t(
            "risk-mandate",
            "Trader mandate",
            "risk",
            "What a trader is authorised to hold: books, hubs, net size per hub-month, tenor, "
            "products and instruments, and the hedge band. Set by risk, never by the trader.",
            "交易员获授权持有的范围：账簿、枢纽、每枢纽-月净头寸、期限、产品与工具及套保区间。由风控"
            "设定，交易员本人不能设定。",
            aliases=("Trading limit", "Authority"),
            related=("Hedge ratio", "Credit exposure"),
            where=("Portfolio → Exposure → Credit and mandates",),
        ),
        # --------------------------------------------------------------- regulation
        _t(
            "regulation-remit",
            "REMIT",
            "regulation",
            "The EU regulation on wholesale energy market integrity and transparency: it forbids "
            "insider trading and market manipulation, requires inside information (such as an "
            "outage) to be published promptly, and trades and orders to be reported to ACER.",
            "欧盟批发能源市场诚信与透明度法规：禁止内幕交易与市场操纵，要求及时公布内幕信息（如设施停运），"
            "并向 ACER 报告交易与订单。",
            related=("UMM", "ACER"),
            sources=("Regulation (EU) No 1227/2011, amended by (EU) 2024/1106",),
            where=("Market → Capacity & Events → Outages",),
        ),
        _t(
            "regulation-umm",
            "Urgent market message",
            "regulation",
            "A publication of inside information under REMIT, typically an unplanned or planned "
            "outage of a field, pipeline, storage or terminal, with the capacity affected.",
            "依 REMIT 发布的内幕信息，通常为气田、管道、储气库或接收站的计划或非计划停运及受影响容量。",
            aliases=("UMM",),
            related=("REMIT",),
            where=("Market → Capacity & Events → Outages",),
        ),
        _t(
            "regulation-acer",
            "ACER",
            "regulation",
            "The EU Agency for the Cooperation of Energy Regulators; receives REMIT reporting and "
            "monitors wholesale markets.",
            "欧盟能源监管机构合作署；接收 REMIT 报告并监测批发市场。",
            related=("REMIT",),
        ),
    ]
