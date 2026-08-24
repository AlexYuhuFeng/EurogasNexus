# Eurogas Nexus OWL 天然气角色模型

> 机器可读伴生文件：[`eurogas-nexus-grm.ttl`](eurogas-nexus-grm.ttl)
> 英文说明：[OWL_GAS_ROLE_MODEL.md](OWL_GAS_ROLE_MODEL.md)

## 1. 目的与状态

本文说明交付于 `docs/ontology/eurogas-nexus-grm.ttl` 的 OWL/Turtle 本体。
它是对 **EASEE-gas Harmonised Gas Role Model（GRM）业务流程视图** 的语义化、
机器可读表达，并与 **SAREF core Commodity 模式** 对齐。

| 属性 | 值 |
| --- | --- |
| 本体 IRI | `https://eurogas-nexus.eu/ontology/grm` |
| 命名空间前缀 | `https://eurogas-nexus.eu/ontology/grm#` |
| 格式 | OWL 2，Turtle 语法 |
| 版本 | `0.5.0` |
| 参考来源 | `Harmonised_GRM_Document_FINAL_2018-05-30.pdf` |
| SAREF 参考 | `https://saref.etsi.org/core/Commodity` |
| 产品状态 | 仅决策支持模型，不可执行 |

该文件是语义映射的规范性依据。产品内部仍以
`src/eurogas_nexus/domain/ontology/` 中的 typed ontology 为可执行权威；本 OWL
文件使 GRM 与 SAREF 对齐关系具备外部可验证、工具无关的表示。

## 2. 命名空间与导入

```turtle
@prefix :      <https://eurogas-nexus.eu/ontology/grm#> .
@prefix saref: <https://saref.etsi.org/core/> .

<https://eurogas-nexus.eu/ontology/grm> a owl:Ontology ;
    owl:imports <https://saref.etsi.org/core/> .
```

本本体导入 ETSI SAREF core 本体。无法联机获取远程 import 的使用方，应先把
SAREF core 装入同一 RDF 图，再解析本地 Turtle 文件。

## 3. Commodity 对齐

GRM 是角色与流程模型，商品语义通过 SAREF Commodity 模式进入本体：

| 本地类 | SAREF 对齐 | 含义 |
| --- | --- | --- |
| `:GasCommodity` | `saref:EnergyCommodity` 且 `saref:NaturalResourceCommodity` | 在欧洲市场中交易和运输的管道天然气 |
| `:LngCommodity` | `:GasCommodity` 的子类 | 由 LNG 系统运营商处理的液化天然气 |
| `:GasMarketServiceCommodity` | `saref:Commodity` 的子类 | 可交易的储气、容量与平衡服务 |
| `:StorageServiceCommodity` | `:GasMarketServiceCommodity` 的子类 | 储气系统运营商提供的储气服务 |
| `:CapacityCommodity` | `:GasMarketServiceCommodity` 的子类 | 通过容量分配流程提供的 entry/exit 容量 |
| `:BalanceServiceCommodity` | `:GasMarketServiceCommodity` 的子类 | 为系统平衡采购的平衡能量 |

这与 SAREF 官方示例一致：`ex:Gas` 同时被声明为
`saref:EnergyCommodity` 与 `saref:NaturalResourceCommodity`。储气、容量与
平衡能量有意建模在 `saref:Commodity` 之下，而不是 SAREF core 的
`saref:Service` 之下：SAREF core 的 `saref:Service` 表示网络暴露的设备
功能，而不是可交易的能源市场服务。

## 4. GRM 角色模型

本体声明 `:MarketParty`（法人或组织主体）、`:GasMarketRole`（外部业务交互
角色）及连接二者的属性 `:playsRole`。与 GRM 原文一致，一个市场参与方可同时
扮演多个角色。

22 个 GRM 协调角色均已收录，并以 GRM 原文描述作为 `skos:definition`：

`AllocationResponsible`、`AreaCoordinator`、`BalanceResponsibleParty`、
`BalancingEnergyResponsible`、`CapacityPlatformResponsible`、
`CapacityResponsibleParty`、`ClearingResponsible`、
`DistributionSystemOperator`、`EnergyTradingPlatformResponsible`、
`FinalCustomer`、`LngSystemOperator`、`MarketInformationAggregator`、
`MeterOperator`、`MeteredDataResponsible`、`ProductionFacilityOperator`、
`ReconciliationResponsible`、`StorageSystemOperator`、`Supplier`、
`SystemOperator`、`Trader`、`TransmissionSystemOperator`、
`WeatherDataProvider`。

## 5. GRM 业务流程视图

本体声明 `:GasBusinessProcess` 及 9 个 GRM 业务流程：

`CapacityAllocationProcess`、`ExchangeGasTradingProcess`、
`OtcGasTradingProcess`、`NominationMatchingProcess`、`MeteringProcess`、
`AllocationProcess`、`BalancingProcess`、`SettlementProcess`、
`RemitTransparencyProcess`。

角色经 `:participatesIn` 参与流程，流程经 `:concerns` 关联其涉及的商品。

GRM 图中的交互箭头被建模为具名对象属性，例如
`:providesValidatedMeteredData`、`:submitsBidsOrOffers`、
`:nominatesConcludedTrades`、`:purchasesCapacityFrom`、
`:offersAvailableCapacity`、`:commissionsBalancingEnergy`、
`:suppliesGasTo`。

## 6. 产品边界标注

Eurogas Nexus 仅提供决策支持，本本体把该边界显式化：

```turtle
:DecisionSupportOutput a owl:Class ;
    rdfs:subClassOf saref:Commodity .

:hasHumanReviewRequirement a owl:DatatypeProperty ;
    rdfs:domain :DecisionSupportOutput ;
    rdfs:range xsd:boolean .
```

本本体中不存在任何代表下单、交易执行、提名提交或结算指令的类或属性；这些
是市场参与方的外部动作，不是产品能力。

## 7. 验证

无需给项目增加运行时依赖，即可用任意 OWL/Turtle 解析器校验该文件，例如：

```bash
pip install rdflib
python -c "import rdflib; g=rdflib.Graph(); g.parse('docs/ontology/eurogas-nexus-grm.ttl', format='turtle'); print(len(g))"
```

仓库契约测试 `tests/contract/test_grm_owl_ontology.py` 额外强制检查命名空间、
SAREF import、完整角色/流程清单、决策支持边界，以及不存在执行动作术语。
