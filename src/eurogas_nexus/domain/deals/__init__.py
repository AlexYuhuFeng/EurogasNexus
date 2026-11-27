"""Deal capture from exchange exports: the canonical deal record and its replaceable formats.

The desk's exchange exports (EEX, ICE, a broker's sheet) are read by a *format*: a TOML file
that maps the export's columns and values to one canonical deal record
(:class:`~eurogas_nexus.domain.deals.record.CanonicalDeal`), with a small optional adapter
hook for what a mapping cannot say. A new or corrected layout is an edit of that file, not a
redesign. The ETRM entry sheet is produced from the same records by a layout file
(``etrm_entry_sheet.toml``). Nothing here places, sends or pre-fills an order, nominates,
settles or books (AGENTS.md rule 8): a captured deal is a record of a trade the exchange or a
broker already confirmed, and the ETRM stays the official record.

交易捕获：交易所导出文件经可替换的格式文件映射为统一交易记录；不下单、不提名、不结算。
"""
