"""Bilingual gas-market glossary baseline used by API, SDK, and clients."""

# ruff: noqa: E501

from __future__ import annotations

from pydantic import BaseModel, Field


class GlossaryTerm(BaseModel):
    term_id: str
    term: str
    category: str
    definition_en: str
    definition_zh_cn: str
    aliases: list[str] = Field(default_factory=list)
    related_terms: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)

    def localized(self, lang: str) -> dict:
        definition = self.definition_zh_cn if lang in {"zh", "zh-CN"} else self.definition_en
        return {
            "term_id": self.term_id,
            "term": self.term,
            "category": self.category,
            "definition": definition,
            "definition_en": self.definition_en,
            "definition_zh_cn": self.definition_zh_cn,
            "aliases": self.aliases,
            "related_terms": self.related_terms,
            "source_refs": self.source_refs,
        }


def baseline_glossary_terms() -> list[GlossaryTerm]:
    """Return a DB-free baseline glossary for development and tests."""

    terms = [
        GlossaryTerm(
            term_id="institution-entsog",
            term="ENTSOG",
            category="institution",
            definition_en=(
                "European Network of Transmission System Operators for Gas, the EU-level "
                "association and transparency platform for gas transmission system operators."
            ),
            definition_zh_cn="欧洲天然气输送系统运营商网络，负责汇集欧洲天然气输送系统运营商并提供透明度数据平台。",
            aliases=["ENTSOG Transparency Platform"],
            related_terms=["TSO", "Interconnection Point", "Capacity"],
            source_refs=["ENTSOG public transparency platform"],
        ),
        GlossaryTerm(
            term_id="institution-gie",
            term="GIE",
            category="institution",
            definition_en=(
                "Gas Infrastructure Europe, the European association covering gas storage, "
                "LNG terminals, and transmission infrastructure operators."
            ),
            definition_zh_cn="欧洲天然气基础设施协会，覆盖欧洲储气库、LNG 接收站和输气基础设施运营商。",
            aliases=["Gas Infrastructure Europe", "AGSI", "ALSI"],
            related_terms=["Storage", "LNG", "AGSI", "ALSI"],
            source_refs=["GIE transparency platform"],
        ),
        GlossaryTerm(
            term_id="institution-ecb",
            term="ECB",
            category="institution",
            definition_en="European Central Bank, a source for reference FX rates used in EUR conversions.",
            definition_zh_cn="欧洲中央银行，可作为欧元相关汇率参考数据来源。",
            aliases=["European Central Bank"],
            related_terms=["FX", "EURGBP", "EURUSD"],
        ),
        GlossaryTerm(
            term_id="venue-ice-ocm",
            term="ICE OCM",
            category="venue",
            definition_en=(
                "ICE On-the-Day Commodity Market, the UK within-day gas market used for "
                "live NBP balancing and screen liquidity."
            ),
            definition_zh_cn="ICE 当日商品市场，英国 NBP 日内天然气平衡和实时屏幕流动性的主要市场。",
            aliases=["OCM", "On-the-Day Commodity Market"],
            related_terms=["NBP", "Within-day", "Bid", "Ask"],
        ),
        GlossaryTerm(
            term_id="venue-eex",
            term="EEX",
            category="venue",
            definition_en="European Energy Exchange, a venue for listed European gas products and clearing workflows.",
            definition_zh_cn="欧洲能源交易所，提供欧洲天然气挂牌产品和清算相关流程。",
            aliases=["European Energy Exchange"],
            related_terms=["Clearing", "Settlement", "TTF", "NBP"],
        ),
        GlossaryTerm(
            term_id="venue-trayport",
            term="Trayport",
            category="venue",
            definition_en="A trading technology network used by European energy brokers and traders for screen markets.",
            definition_zh_cn="欧洲能源经纪商和交易员常用的屏幕交易技术网络。",
            aliases=[],
            related_terms=["Broker", "Screen", "Bid", "Ask"],
        ),
        GlossaryTerm(
            term_id="hub-ttf",
            term="TTF",
            category="hub",
            definition_en="Title Transfer Facility, the Dutch virtual gas trading hub and main continental European benchmark.",
            definition_zh_cn="荷兰产权转让设施，荷兰虚拟天然气交易枢纽，也是欧洲大陆主要基准价格。",
            aliases=["Title Transfer Facility"],
            related_terms=["Virtual Hub", "EEX", "ICE"],
        ),
        GlossaryTerm(
            term_id="hub-nbp",
            term="NBP",
            category="hub",
            definition_en="National Balancing Point, the UK virtual gas trading hub.",
            definition_zh_cn="国家平衡点，英国虚拟天然气交易枢纽。",
            aliases=["National Balancing Point"],
            related_terms=["ICE OCM", "Easington", "Bacton"],
        ),
        GlossaryTerm(
            term_id="hub-the",
            term="THE",
            category="hub",
            definition_en="Trading Hub Europe, the German market area and virtual gas trading hub.",
            definition_zh_cn="德国 Trading Hub Europe 市场区和虚拟天然气交易枢纽。",
            aliases=["Trading Hub Europe"],
            related_terms=["NCG", "Gaspool"],
        ),
        GlossaryTerm(
            term_id="hub-peg",
            term="PEG",
            category="hub",
            definition_en="Point d'Echange de Gaz, the French virtual gas trading hub.",
            definition_zh_cn="法国天然气交换点，法国虚拟天然气交易枢纽。",
            aliases=["Point d'Echange de Gaz"],
            related_terms=["France", "Virtual Hub"],
        ),
        GlossaryTerm(
            term_id="terminal-easington",
            term="Easington",
            category="terminal",
            definition_en=(
                "UK east-coast beach terminal and National Gas NTS entry point used for "
                "North Sea and upstream beach delivery contracts."
            ),
            definition_zh_cn="英国东海岸海滩终端和 National Gas NTS 入口点，常用于北海及上游海滩交付合同。",
            aliases=["Easington Beach Terminal"],
            related_terms=["NBP", "Entry Capacity", "National Gas NTS"],
        ),
        GlossaryTerm(
            term_id="terminal-bacton",
            term="Bacton",
            category="terminal",
            definition_en="UK gas terminal and NTS exit/entry area connected to interconnectors and domestic network flows.",
            definition_zh_cn="英国天然气终端及 NTS 出入口区域，连接互联管道和国内管网流量。",
            aliases=["Bacton GDN"],
            related_terms=["Exit Capacity", "Interconnector", "NBP"],
        ),
        GlossaryTerm(
            term_id="concept-entry-capacity",
            term="Entry Capacity",
            category="capacity",
            definition_en="Right or tariffed capacity to flow gas into a transmission system at an entry point.",
            definition_zh_cn="在入口点将天然气注入输气系统所需的权利或收费容量。",
            aliases=["NTS Entry Capacity"],
            related_terms=["Exit Capacity", "TSO Tariff", "Firm Capacity"],
        ),
        GlossaryTerm(
            term_id="concept-exit-capacity",
            term="Exit Capacity",
            category="capacity",
            definition_en="Right or tariffed capacity to offtake gas from a transmission system at an exit point.",
            definition_zh_cn="在出口点从输气系统提取天然气所需的权利或收费容量。",
            aliases=["NTS Exit Capacity"],
            related_terms=["Entry Capacity", "TSO Tariff", "Firm Capacity"],
        ),
        GlossaryTerm(
            term_id="concept-firm-capacity",
            term="Firm Capacity",
            category="capacity",
            definition_en="Capacity that is contractually firm unless curtailed under defined network rules.",
            definition_zh_cn="按合同为确定性的容量，除非根据明确的管网规则被削减。",
            aliases=["Firm"],
            related_terms=["Interruptible Capacity", "Capacity Product"],
        ),
        GlossaryTerm(
            term_id="concept-interruptible-capacity",
            term="Interruptible Capacity",
            category="capacity",
            definition_en="Capacity that can be interrupted by the operator under defined conditions and usually prices differently.",
            definition_zh_cn="可在规定条件下被运营商中断的容量，通常采用不同定价。",
            aliases=["Interruptible"],
            related_terms=["Firm Capacity", "Capacity Product"],
        ),
        GlossaryTerm(
            term_id="price-bid",
            term="Bid",
            category="price",
            definition_en="The price at which a market participant is willing to buy; sell decisions mark against executable bids.",
            definition_zh_cn="市场参与者愿意买入的价格；卖出决策应按可成交买价进行盯市。",
            aliases=[],
            related_terms=["Ask", "Mark-to-Market", "ICE OCM"],
        ),
        GlossaryTerm(
            term_id="price-ask",
            term="Ask",
            category="price",
            definition_en="The price at which a market participant is willing to sell.",
            definition_zh_cn="市场参与者愿意卖出的价格。",
            aliases=["Offer"],
            related_terms=["Bid", "Spread"],
        ),
        GlossaryTerm(
            term_id="price-settlement",
            term="Settlement Price",
            category="price",
            definition_en="Official price used by a venue or clearing house for margining, invoicing, or settlement.",
            definition_zh_cn="交易场所或清算机构用于保证金、发票或结算的官方价格。",
            aliases=["Settle"],
            related_terms=["Clearing", "Variation Margin"],
        ),
        GlossaryTerm(
            term_id="price-mark-to-market",
            term="Mark-to-Market",
            category="financial",
            definition_en="Revaluing a position or option using current market marks such as bid, ask, last, or settlement.",
            definition_zh_cn="使用当前买价、卖价、最新价或结算价重新估值头寸或方案。",
            aliases=["MTM"],
            related_terms=["PnL", "Bid", "Settlement Price"],
        ),
        GlossaryTerm(
            term_id="price-icis-heren",
            term="ICIS Heren",
            category="price",
            definition_en=(
                "Licensed energy price-assessment source used by market participants "
                "for products such as NBP day-ahead assessments."
            ),
            definition_zh_cn=(
                "需要授权的能源价格评估来源，市场参与者可用于 NBP 日前等价格评估。"
            ),
            aliases=["ICIS", "Heren", "ICIS Heren Day Ahead"],
            related_terms=["NBP", "Day-ahead", "Price Assessment", "ICE OCM"],
        ),
        GlossaryTerm(
            term_id="terminal-easington-entry-point",
            term="Easington Entry Point",
            category="terminal",
            definition_en=(
                "National Gas NTS entry-point representation for Easington beach "
                "delivery and associated upstream portfolio routes."
            ),
            definition_zh_cn=(
                "Easington 海滩交付和相关上游组合路线在 National Gas NTS 中的入点表示。"
            ),
            aliases=["Easington Beach Entry", "Easington Beach Terminal"],
            related_terms=["Easington", "Entry Capacity", "NBP", "ICE OCM"],
        ),
        GlossaryTerm(
            term_id="financial-pnl",
            term="PnL",
            category="financial",
            definition_en="Profit and loss, calculated from price, volume, route costs, fees, financing, and contract effects.",
            definition_zh_cn="损益，由价格、数量、路线成本、费用、融资和合同影响共同决定。",
            aliases=["Profit and Loss"],
            related_terms=["Mark-to-Market", "Netback", "Cash Value"],
        ),
        GlossaryTerm(
            term_id="financial-cash-value",
            term="Early Recovered Cash Value",
            category="financial",
            definition_en=(
                "Financing benefit from receiving screen-sale cash earlier than upstream "
                "contract settlement or invoice payment."
            ),
            definition_zh_cn="屏幕销售现金早于上游合同结算或发票付款回收时产生的融资收益。",
            aliases=["Cash Acceleration Value"],
            related_terms=["Settlement", "PnL", "Financing Rate"],
        ),
        GlossaryTerm(
            term_id="contract-efet",
            term="EFET",
            category="contract",
            definition_en="European Federation of Energy Traders standard contract framework commonly used in European energy trading.",
            definition_zh_cn="欧洲能源交易商联合会标准合同框架，常用于欧洲能源交易。",
            aliases=["EFET General Agreement"],
            related_terms=["Settlement", "Tolerance", "Contract Quantity"],
        ),
        GlossaryTerm(
            term_id="contract-tolerance",
            term="Tolerance",
            category="contract",
            definition_en="Contractual or operational allowed deviation around nominated or delivered gas quantity.",
            definition_zh_cn="合同或操作层面对提名量或交付量允许的偏差范围。",
            aliases=["Delivery Tolerance", "Nomination Tolerance"],
            related_terms=["Nomination", "Imbalance", "Overrun"],
        ),
        GlossaryTerm(
            term_id="contract-nomination",
            term="Nomination",
            category="contract",
            definition_en="Operational instruction or schedule for gas flow submitted to a system operator under market rules.",
            definition_zh_cn="根据市场规则向系统运营商提交的天然气流量操作指令或计划。",
            aliases=[],
            related_terms=["Tolerance", "Imbalance", "TSO"],
        ),
        GlossaryTerm(
            term_id="concept-hdd",
            term="HDD",
            category="weather",
            definition_en="Heating Degree Days, a weather-derived measure of heating demand.",
            definition_zh_cn="采暖度日数，用于衡量由天气驱动的采暖需求。",
            aliases=["Heating Degree Days"],
            related_terms=["CDD", "Demand Nowcast"],
        ),
        GlossaryTerm(
            term_id="concept-cdd",
            term="CDD",
            category="weather",
            definition_en="Cooling Degree Days, a weather-derived measure of cooling demand.",
            definition_zh_cn="制冷度日数，用于衡量由天气驱动的制冷需求。",
            aliases=["Cooling Degree Days"],
            related_terms=["HDD", "Demand Nowcast"],
        ),
        GlossaryTerm(
            term_id="concept-lng",
            term="LNG",
            category="infrastructure",
            definition_en="Liquefied Natural Gas, natural gas cooled into liquid form for marine transport and regasification.",
            definition_zh_cn="液化天然气，将天然气冷却成液态以便海运并在接收站再气化。",
            aliases=["Liquefied Natural Gas"],
            related_terms=["Regasification", "Send-out", "ALSI"],
        ),
        GlossaryTerm(
            term_id="concept-send-out",
            term="Send-out",
            category="infrastructure",
            definition_en="Gas delivered from an LNG terminal into the gas grid after regasification.",
            definition_zh_cn="LNG 接收站再气化后输送进入天然气管网的气量。",
            aliases=["Sendout"],
            related_terms=["LNG", "Regasification"],
        ),
        GlossaryTerm(
            term_id="concept-storage",
            term="Storage",
            category="infrastructure",
            definition_en="Underground gas storage inventory and injection/withdrawal capability used for flexibility and seasonality.",
            definition_zh_cn="地下储气库存及注采能力，用于灵活性管理和季节性调节。",
            aliases=["UGS"],
            related_terms=["AGSI", "Injection", "Withdrawal"],
        ),
        GlossaryTerm(
            term_id="concept-netback",
            term="Netback",
            category="financial",
            definition_en="Destination market value minus route, tariff, conversion, financing, and handling costs.",
            definition_zh_cn="目标市场价值扣除路线、关税、换算、融资和处理成本后的净回值。",
            aliases=[],
            related_terms=["Route Cost", "PnL", "Spread"],
        ),
        GlossaryTerm(
            term_id="concept-route-cost",
            term="Route Cost",
            category="route",
            definition_en="All costs required to move or monetize gas along a route, including tariffs, capacity, commodity fees, losses, FX, and financing.",
            definition_zh_cn="沿路线输送或变现天然气所需的全部成本，包括关税、容量、商品费、损耗、汇率和融资。",
            aliases=[],
            related_terms=["Entry Capacity", "Exit Capacity", "Netback"],
        ),
    ]
    return sorted(terms, key=lambda item: item.term.lower())
