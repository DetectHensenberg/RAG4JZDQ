![cover_image](https://mmbiz.qpic.cn/sz_mmbiz_jpg/0nIB33cfDvZL4lOyicXcv9cZEsicvESvWrYVvWrZCfqfZZBSaVcU791HkZRQpaPpTXEExYVxO0v4zKTg74WkjFSKV5VRXXWWJWhIyfFldJDbQ/0?wx_fmt=jpeg)

#  Palantir 本体论建模平台深度解析

原创  何明璐  何明璐  [ 人月聊IT ](javascript:void\(0\);)

_2026年03月19日 08:51_ __ _ _ _ _ _ 广东  _

** 大家好，我是人月聊IT。  **

本文档整理自我和Claude大模型关于Palantir本体建模的一次完整的技术对话，涵盖 Palantir Foundry / AIP
平台的本体论建模机制、供应链场景应用、与数据中台的集成方案，以及大模型决策回写的实现路径。

* * *

##  目录

  1. Palantir 本体论建模平台概览 
  2. 供应链场景：数据在可视化图谱上的流动 
  3. 大模型决策如何回写业务系统 
  4. 与已有数据中台的集成方案 
  5. 库存周转率告警驱动决策的完整解决方案 

* * *

##  1\. Palantir 本体论建模平台概览

** 问：你是否对 Palantir
的基于本体论建模的平台熟悉？在该平台上有一个运营平台，可以对本体论模型进行动态模拟或推演。在这个可视化图谱上，我看到有数据采集源系统、数据采集 ETL
集成流，也有对象模型（包括对象间关系）。帮我看下这个建模可视化页面还有哪些关键组件或元素，以及这些元素间是如何协同起来的？  **

* * *

###  平台整体架构

Palantir Foundry / AIP 平台由五个层次构成，自上而下协同运转：

![](https://mmbiz.qpic.cn/sz_mmbiz_png/0nIB33cfDvYQwdiaicZ6Aib6BpVSiaXDm8xib36LVToCKNLZyGetmmnHBoZVibgQQsdGcluCh9qE59HhaAobicniaTQ0FDdyujIEicXN8icCxicC2aj1q8/640?wx_fmt=png&from=appmsg)

    
    
    【架构图占位】  
    Palantir 本体论平台五层架构图  
    （数据采集层 → 集成与转换层 → 本体论建模层 → 应用与运营层 → 权限与治理层）  
    

* * *

###  一、数据采集层（Source Systems）

这是整个平台的最左端/最上端入口。可以接入的典型来源包括：

  * ** 数据库  ** ：Oracle、SQL Server 
  * ** ERP  ** ：SAP 
  * ** 实时流  ** ：Kafka、IoT 传感器 
  * ** 外部 REST API  **
  * ** 数据仓库  ** ：Snowflake、Redshift 

* * *

###  二、ETL / 集成层（Pipeline & Transform）

包含四个关键子组件：

** Connector（连接器）  ** ：Palantir 使用 Magritte 框架实现与外部系统的对接，支持推拉两种模式，也支持自定义连接器开发。

** Transform（转换）  ** ：数据在 Code Repository 中通过 Python、Spark 或 SQL
脚本进行清洗和转化，转化逻辑本身是可版本化的代码资产。

** Dataset（数据集）  ** ：Foundry 的数据存储单元，支持分支（Branch）、版本（Version）管理，类似 Git
对代码的管理方式。多个 Dataset 可以串联成 DAG 流水线。

** 调度机制  ** ：支持增量更新、全量刷新、事件触发三种调度模式，并有完整的数据血缘（Lineage）追踪。

* * *

###  三、本体论建模层（Ontology）—— 核心

这是平台最具特色的部分，包含四类核心元素：

** Object Type（对象类型）  **
：等同于业务实体的"类定义"，比如"飞机"、"零件"、"人员"。每个对象类型有属性（Properties）、主键（Primary Key），以及来源
Dataset 的映射关系。

** Link Type（链接类型）  ** ：显式定义对象间关系，支持 1:1、1:N、M:N
三种基数。关系本身可以携带属性（比如"人员——属于——部门"这条链接，可以附带"入职日期"属性）。

** Action Type（行动类型）  **
：定义"可以对对象做什么操作"，例如修改状态、触发工单、更新属性，是把"只读图谱"变成"可操作平台"的关键。

** Function / Interface  ** ：Function 是无副作用的计算逻辑（类似派生属性）；Interface
定义跨对象类型的通用契约，让多个不同类型的对象可以共享同一套查询接口。

* * *

###  四、应用与运营层

面向用户的展现端，包含以下组件：

** Workshop / Slate（前端应用）  ** ：低代码应用构建器，业务用户可以在这里消费 Ontology，而不需要写代码。

** 图谱可视化  ** ：对象关系图（Object Graph）在这里展现，支持对象图、时序图、地图视图等多种展现形态。可以从任意对象节点出发，沿着
Link Type 扩展图谱。

** 动态推演引擎（AIP Logic / Scenario Modeling）  ** ：在 Ontology
的对象模型上，叠加一套假设性参数（What-if），通过 Function 或 Rules
计算推演结果，而不改动真实数据。典型用途是资源调度优化、供应链断供模拟、战场推演等。

** AIP Agent  ** ：将 LLM 与 Ontology 绑定，用户可以用自然语言操作对象、执行 Action、查询图谱。Agent
的工具集就是 Ontology 暴露的 Actions 和 Functions。

* * *

###  五、各层的协同关系

整体协同逻辑是一个  ** 单向数据流 + 双向操作回写  ** 的架构：

  * ** 数据流向  ** ：Source → ETL → Dataset → Ontology 对象实例（数据流向下游自动同步） 
  * ** 操作回流  ** ：用户通过 Action → 写回 Dataset 或外部系统（操作回流上游） 
  * ** 推演层  ** ：在 Ontology 层上的"沙盒分支"，不影响主链路数据 
  * ** 治理层  ** ：横切所有层，对象级的权限控制可以细化到单个属性 

* * *

##  2\. 供应链场景：数据在可视化图谱上的流动

**
问：给我一个和供应链相关的具体场景来进一步说明下数据在这个可视化图谱上的流动。另外大模型做出决策后，是如何回写为原来的业务系统的，这个实现是在上面架构的哪一层？
**

* * *

** 场景设定  ** ：某汽车 OEM 厂商，供应商 A 的某关键零件（刹车片）库存突然告急，AIP Agent 感知异常并推演出备选方案，最终决策回写进
SAP 生成采购订单。

![](https://mmbiz.qpic.cn/sz_mmbiz_png/0nIB33cfDvau16aRQgt5GvNhf5MPRQic9qibicOfstC35orwtF3lEbsp8e9wicRCf7ZhSMoefMznrpiagibzRMXIWtI03HVXSb65FVJCFJrYnn96k/640?wx_fmt=png&from=appmsg)

    
    
    【架构图占位】  
    供应链场景完整数据流动图  
    （源系统 → ETL → Ontology 对象图谱 → AIP Agent 推演层 → Action 执行 → 回写至业务系统）  
    

* * *

###  数据流动详解

####  第一步：源系统数据采集

SAP ERP、WMS、供应商门户、物流平台通过实时同步 / 增量 ETL 将数据推入 Foundry。

####  第二步：Dataset 层落地

在 Foundry 内形成以下核心数据集：

  * 库存快照 Dataset 
  * 采购订单 Dataset 
  * 运输状态 Dataset 
  * 供应商评级 Dataset 

####  第三步：Ontology 对象实例化

Dataset 数据被映射为以下 Object Type 实例，并通过 Link Type 建立关联：

对象类型  |  关键属性  |  关联关系  
---|---|---  
供应商  |  评级、交货周期、地理位置、风险值  |  供应 → 零件  
零件  |  料号、安全库存、BOM 层级、替代料  |  持有 → 库存记录  
库存记录  |  在手量、在途量、仓库、更新时间  |  —  
采购订单  |  状态、数量、金额、预计到货、紧急标记  |  关联 → 供应商、零件  
运输批次  |  运输方式、当前位置、延误风险、ETA  |  包含 → 采购订单  
生产工单  |  工厂、计划用量、开工日期、优先级  |  消耗 → 库存记录  
  
此外，  ` Function: 断供风险评分  ` 挂在零件对象上，基于库存量、在途量、工单需求实时计算风险得分。

####  第四步：AIP Agent 推演

  * ** 感知  ** ：刹车片 P-4421 库存 = 80 片，安全库存 = 500 片，工单需求 = 600 片/周 
  * ** 推演方案  ** ： 
    * 方案①：紧急补单 
    * 方案②：启用替代料 P-4422 
    * 方案③：降低产线速率 

####  第五步：执行 Action，回写业务系统

选定方案后，调用  ` createEmergencyPurchaseOrder  ` Action，参数回写至 SAP，同时通知相关团队。

* * *

##  3\. 大模型决策如何回写业务系统

###  回写机制的核心：Action Type 是关键枢纽

回写发生在  ** 应用与运营层  ** ，但真正承载回写逻辑的是 Ontology 建模层定义的  ` Action Type  `
。两层协同配合，具体链路如下：

####  第一步：AIP Agent 选择方案

LLM 通过读取 Ontology 对象（库存量、在途量、供应商风险评分等）形成上下文，推演出最优解。  ** LLM 的工具列表就是 Ontology
暴露出来的所有 Action Type  ** ，Agent 不能做超出 Action 定义范围之外的任何写操作，权限边界在建模时就锁死了。

####  第二步：调用 Action Type

` createEmergencyPurchaseOrder  ` 这个 Action Type 在 Ontology 建模层预先定义，包含三件事：

  1. 参数校验（料号、数量、供应商是否合法） 
  2. 在 Ontology 中创建一个新的"采购订单"对象实例 
  3. 触发配置好的回写通道 

####  第三步：回写通道（三种主要机制）

** 机制一：Webhook / HTTP Action  ** Action 执行时直接向外部系统发一个 HTTP POST，SAP 的 BAPI
接口或现代 ERP 的 REST API 收到请求后在业务系统内创建真实采购订单。适合外部系统有稳定 API 的场景。

** 机制二：Action → 写 Dataset → 外部系统轮询  ** Action 先把结果写入 Foundry 的"出站
Dataset"，外部系统的 ETL 连接器定期轮询这个 Dataset 并消费变更。这是松耦合方式，适合老旧 ERP 系统，不需要暴露实时 API。

** 机制三：Streaming / Event Bus 集成  ** Action 把事件写入消息队列（Kafka），外部系统订阅该 topic
并响应。适合对延迟敏感的生产系统。

####  第四步：状态回流形成闭环

SAP 执行完采购订单创建后，订单状态（确认号、实际到货时间等）通过 ETL 连接器同步回 Foundry，更新 Ontology
中对应"采购订单"对象的状态，图谱上的节点颜色和属性随之变化。

* * *

###  关键设计约束

> ** LLM 在这个架构里不能直接操作任何外部系统  ** ，它只能调用预先在 Ontology 中定义并经过权限审核的  ` Action Type
> ` 。

这意味着：谁有权创建紧急采购订单、最大数量上限是多少、哪些供应商可以选、是否需要人工审批——这些业务规则全部在建模阶段就固化在 Action
的定义里，而不是依赖 LLM 的自我判断。

** 大模型做推理，Action 做执行，权限和规则在 Ontology 层管控。  **

* * *

##  4\. 与已有数据中台的集成方案

** 问：客户已经有数据中台，Palantir 是否会存储采集过来的数据？类似详细的供应商数据、零件数据、库存数据？如果原来已经有类似数据中台、BI
等系统进行了数据采集，那么又如何和 Palantir 集成和对接？  **

* * *

###  Palantir 确实存储数据，但有明确的层次

Palantir Foundry 内部有自己的数据存储体系，分三个层次：

** 原始数据层（Raw Dataset）  ** ：从源系统同步过来的数据会完整落地存储在 Foundry 的对象存储中，格式是
Parquet/Delta 列存。供应商主数据、零件 BOM、库存快照都会有一份 Foundry 自己的副本。这不是缓存，是持久化存储，带版本和血缘管理。

** 加工数据层（Transformed Dataset）  ** ：经过 ETL Transform 处理后的清洗数据，也存在 Foundry
里。每一步转化都可追溯。

** Ontology 对象层  ** ：并不单独存储一份完整数据，而是"对象定义 + 指向 Dataset 的映射关系"。查询对象属性时，底层读的还是
Dataset。

> ** 结论  ** ：Palantir 的存储策略是——数据进来就落地，Ontology 是语义层而不是独立存储层。

* * *

###  三种主流集成模式

![](https://mmbiz.qpic.cn/sz_mmbiz_png/0nIB33cfDvb0MsBUyXMtO8ibsvYv9aeGYXTKVs9ia0Y1qvVS6hHibT39x9w8onnaJ7ibEBn1XiaKLWMGicRaF2WUOpC8yWRdkTOicsrRT8Uyqpupes/640?wx_fmt=png&from=appmsg)

###

    
    
    【架构图占位】  
    三种集成模式对比图  
    （模式一：Palantir 作为消费方 / 模式二：并行双轨 / 模式三：Palantir 承担中台职能）  
    

####  模式一：Palantir 作为消费方（推荐）

** 适用场景  ** ：已有成熟数据中台。

** 核心逻辑  ** ：不重复采集源系统，直接对接数据中台已加工好的数据层（比如 ODS 或 DWS 层），Palantir
只拿加工后的宽表，跳过原始数据采集。数据中台继续负责 ETL 和治理，Palantir 负责 Ontology 建模和 AIP 决策。

** 优势  ** ：

  * 避免数据孤岛 
  * 口径一致，数据中台是唯一数据权威 
  * Palantir 专注 Ontology + AIP 价值层 

####  模式二：并行双轨

** 适用场景  ** ：BI 侧重报表、Palantir 侧重运营决策，两者并重。

** 核心逻辑  ** ：数据中台和 Palantir 各自从源系统独立采集，但通过  ** 统一数据资产目录（Data Catalog）  **
保持元数据一致，避免口径打架。两套系统服务不同用途，不强行合并。

** 关键点  ** ：Data Catalog 的口径对齐是集成成败的核心。

####  模式三：Palantir 承担中台职能

** 适用场景  ** ：数据中台尚不成熟。

** 核心逻辑  ** ：直接用 Foundry 承担数据中台职能，原有 BI 工具（Tableau、Power BI）通过 Foundry 的
JDBC/ODBC 接口继续连接，不需要迁移。

* * *

###  各层数据归属对照

![](https://mmbiz.qpic.cn/mmbiz_png/0nIB33cfDvaMuVd5zuIeytRcTibhFdPdnUWBiaQ0XX2jY4LU5jqRM7LhdRDo8nHZIDfvK6f5b5KjsDAZmxS3DbG3botsbYwYFQ58wSAaYLzos/640?wx_fmt=png&from=appmsg)

###

    
    
    【架构图占位】  
    数据存储层次与归属对照表  
    （原始层 / 汇总层 / 语义层 / 决策层 / 治理层）  
    

层次  |  数据中台  |  Palantir Foundry  |  数据归属  
---|---|---|---  
原始层  |  ODS 原始表  |  Raw Dataset（模式一推荐跳过）  |  数据中台拥有，Palantir 不重建  
汇总层  |  DWS 宽表  |  Foundry Dataset（核心入口）  |  Foundry 存储副本，中台是口径权威  
语义层  |  无对应概念  |  Ontology 对象图谱  |  Palantir 独有，核心价值层  
决策层  |  BI 报表/看板  |  AIP Agent  |  Palantir 独有，差异化价值  
治理层  |  数据资产目录  |  Foundry 元数据/血缘  |  双方共建，口径对齐是关键  
  
* * *

###  几个实际项目中的重要细节

** 关于"数据副本"的争议  ** ：从 DWS 宽表同步一份到 Foundry 是几乎不可避免的，因为 AIP Agent
需要本地高频读取，跨系统实时查询延迟太高。存两份是工程现实，关键是要明确中台是口径权威，Foundry 的副本只跟随中台变更，不能反向修改中台数据。

** 口径打架是最大风险  ** ：比如"供应商评级"这个字段，中台的定义可能是过去 12 个月的综合评分，而 Palantir Ontology
里如果用了不同的计算 Function，结果可能不一致，业务侧无法信任任何一方。解决方法是在集成初期就列清单，写进数据资产目录。

** Palantir 真正的差异化不在存储  ** ：如果数据中台已经成熟，Palantir 在存储和 ETL 上几乎没有竞争优势，它的价值完全在
Ontology 语义层和 AIP 决策层。

* * *

##  5\. 库存周转率告警驱动决策的完整解决方案

** 问：数据中台有一个监控指标，比如库存周转率，这个指标来源于底层多个数据对象的管理和整合才计算出来的。那么 Palantir
进行本体对象建模的时候是否会有库存周转率这个对象？还是只有底层的订单、库存、入库单等对象？如果只有底层对象，那么在库存周转率触发告警后，如何驱动
Palantir 的本体模型做出一个决策，类似降低安全库存设置的回写？请基于上面的场景来详细说明整体解决方案。  **

* * *

###  核心答案：库存周转率在 Palantir 里是什么？

** 不会有"库存周转率"这个 Object Type。  ** Palantir 的 Ontology
只对"业务实体"建模，库存周转率是一个派生计算结果，不是独立存在的业务对象。它在 Palantir 里的正确形态是：

  * ** 底层对象  ** ：  ` 库存记录  ` 、  ` 采购订单  ` 、  ` 销售订单  ` 、  ` 入库单  ` 这些是 Object Type 
  * ** 库存周转率  ** = 挂在  ` 零件  ` 或  ` 仓库  ` 对象上的一个  ** Function 属性  ** ，由底层对象数据实时计算得出 
  * ** 告警阈值  ** = 挂在该 Function 上的  ** Subscription / Rule  ** ，当计算值越界时触发后续动作 

* * *

###  完整解决方案

![](https://mmbiz.qpic.cn/mmbiz_png/0nIB33cfDvbw8PNDpdFTCehT1vOySw9OQmb2NaIibhAqLZAf3RaUVC5EzNaqIciar06hPHDhGPicu2tyN94nEXd3d3mqpfAaaAYgrxMBLDXGSg/640?wx_fmt=png&from=appmsg)

###

    
    
    【架构图占位】  
    库存周转率告警驱动决策完整链路图  
    （数据中台指标计算 → Webhook 告警 → Palantir 接收定位对象 → Ontology 图谱推演 → AIP Agent 决策 → Action 回写 SAP → 状态回流闭环）  
    

* * *

####  第一阶段：数据中台侧——指标计算与告警触发

数据中台的 DWS 宽表（销售出库汇总、平均库存汇总）驱动指标计算引擎，按如下公式计算库存周转率：

    
    
    库存周转率 = 出库量 / 平均库存  
    

当 P-4421（刹车片）的库存周转率从正常水位下降至  ** 0.8  ** （阈值为 2.0）时，告警规则触发，通过  ** Webhook  **
将告警信息推送至 Palantir。

> ** 关键设计原则  ** ：库存周转率是中台的指标，不是 Palantir 的对象——中台负责计算，Palantir 负责响应和决策。

* * *

####  第二阶段：Palantir 接收告警，定位对象实例

Palantir 的告警接收端点解析 Webhook 内容：

    
    
    料号 = P-4421  
    周转率 = 0.8  
    仓库 = WH-03  
    

** 对象定位方式  ** （两种）：

  1. 中台 Webhook 直接携带 Palantir 对象主键（需提前在中台维度表维护 Palantir 对象 ID） 
  2. Palantir 接收端用料号做对象查找：  ` Part.filter(partId == "P-4421")  ` （更常见，无需改造中台） 

定位到对象后，AIP Agent 沿 Link Type 向外扩展，把该零件关联的库存记录、入库单、生产工单、供应商全部拉入上下文。

* * *

####  第三阶段：Ontology 对象图谱——底层对象与 Function 属性

Palantir 图谱中涉及的对象及其数据：

对象类型  |  关键数据  
---|---  
零件 P-4421  |  安全库存: 500，Function turnoverRate = 0.8，Rule: 告警阈值 < 2.0  
库存记录  |  在手量: 80 片，仓库: WH-03  
入库单  |  近 30 天入库: 100 片，供应商甲，周期: 14 天  
销售出库单  |  近 30 天出库: 64 片，需求趋势下行，同比: -38%  
生产工单  |  未来 4 周需求: 256 片，优先级: 普通，可延期: 是  
  
** Function 定义  ** （挂在零件对象上，非独立存储）：

    
    
    Function turnoverRate(part: Part): Double {  
      val outbound = part.salesOrders  
                         .filter(date >= today - 30days)  
                         .sumOf(qty)  
      val avgInventory = part.inventoryRecords  
                             .filter(date >= today - 30days)  
                             .average(quantity)  
      return outbound / avgInventory  
    }  
    

在这个 Function 上挂一条  ` Subscription Rule  ` ：当  ` turnoverRate < 2.0  `
时，触发内部事件，激活 AIP Agent 推演流程。这样告警的感知和响应全部在 Palantir 内部形成闭环，不依赖外部调度。

* * *

####  第四阶段：AIP Agent 推演

基于图谱中所有关联对象的完整上下文，AIP Agent 做出以下推演：

** 感知信息汇总  ** ：

  * 零件 P-4421 / 周转率 0.8（阈值 2.0） 
  * 出库同比 -38%（需求下行） 
  * 未来 4 周需求 256 片 
  * 现有安全库存 500 片（明显偏高，导致积压） 

** 推演方案  ** ：

方案  |  内容  |  预期效果  
---|---|---  
方案①  |  安全库存 500 → 200，降低补货触发点  |  预计周转率回升至 1.9，6 周达标  
方案②  |  暂停下一周期采购订单，消化现有库存  |  预计 6 周内周转率达标，但有断供风险  
  
** 决策  ** ：选择方案①（更快见效，不影响生产连续性）→ 执行 Action:  ` updateSafetyStock  `

> ** AIP Agent 的核心优势  ** ：不只是知道"周转率低了"这个结果，而是能立刻给出"为什么周转率低"的多维解释——需求下行 -38%
> 是根因，安全库存设置过高是直接原因，调整安全库存是最小干预方案。

* * *

####  第五阶段：Action Type 执行

调用  ` updateSafetyStock  ` Action Type：

    
    
    参数:  
      partId        = P-4421  
      newSafetyStock = 200  
      reason        = "周转率告警，需求下行 -38%"  
      approver      = 系统自动（或配置为需要人工审批）  
      
    内置逻辑:  
      1. 权限校验（是否有权修改该料号安全库存）  
      2. 更新 Ontology 零件对象（安全库存属性 500 → 200）  
      3. 写入出站 Dataset  
      4. 触发 Webhook 通知 SAP  
      5. 记录审计日志（含推演依据）  
    

* * *

####  第六阶段：回写至业务系统

回写目标  |  实现方式  |  内容  
---|---|---  
SAP MM 模块  |  BAPI / REST API  |  物料主数据安全库存参数更新：500 → 200  
通知渠道  |  Webhook → 邮件 / Teams  |  含推演依据摘要，供业务团队知悉  
数据中台  |  出站 Dataset → ETL 同步  |  中台重算周转率，指标随之更新  
  
* * *

####  第七阶段：状态回流——闭环完成

    
    
    SAP 安全库存更新 (200片)  
      → 采购计划按新参数运行，补货频率降低  
      → 库存水位逐步下降  
      → 出库占比提升  
      → 中台重新计算周转率 > 2.0  
      → 告警规则自动解除  
      → Ontology 对象状态同步更新  
    

整个闭环通常在  ** 4～6 周  ** 内完成，全程可追溯（每一步操作均记录在 Foundry 审计日志中）。

* * *

###  最容易踩的坑：口径一致性问题

中台的"库存周转率"定义和 Palantir Function 里的计算逻辑  ** 必须保持一致  ** 。

项目  |  中台口径  |  Palantir Function 口径  
---|---|---  
计算周期  |  年出库量 / 年末库存  |  近 30 天出库 / 近 30 天平均库存  
数值结果  |  可能差异显著  |  —  
影响  |  业务团队质疑 AIP Agent 推演可信度  |  —  
  
** 解决方法  ** ：在集成文档里明确约定——周转率的权威计算在中台，Palantir Function
里的版本只用于推演时的相对比较，最终结果以中台数据为准回传验证。

* * *

##  总结

维度  |  核心结论  
---|---  
Ontology 建模原则  |  只对业务实体建模，指标是 Function 属性而非独立对象  
告警响应机制  |  中台触发 Webhook → Palantir 定位对象 → Agent 推演 → Action 回写  
回写实现层  |  Action Type（Ontology 建模层定义）+ 应用层执行，两层协同  
数据中台集成  |  推荐模式一（Palantir 消费 DWS 宽表），中台是口径权威  
最大风险  |  口径打架——需在集成初期通过 Data Catalog 对齐指标定义  
核心价值边界  |  数据中台负责存储与指标计算，Palantir 负责 Ontology 语义与 AIP 决策  
  
* * *

_ 文档整理完毕。供大家参考。  _

  

接着我们来对整个库存周转率预警和AIP实时决策后回写的整个过程做一个类似Palantir实现的一个简单模拟。整个模拟我们分为两个步骤。

首先是完成一个传统的由已有数据中台就能够完成的采集多方数据进入ODS库，然后形成上层宽表和指标动态计算的过程，如下：

![](https://mmbiz.qpic.cn/mmbiz_png/0nIB33cfDvbd6nNvTFVflibmiaGyCiasR9Kic1PJdkOcSC3rCic37uNmajND5f8naIicp3b6tKQtz0mLicDL5paRJOo3tBwwxEqmYcvcY84mkQjwe8/640?wx_fmt=png&from=appmsg)

接着我们执行动态模型，触发AIP动态计算形成回写策略回写采购系统。在这里我们模拟了三种决策意见，实际可能是人工感觉决策后再选择一条最优决策回写到源头的业务系统。

![](https://mmbiz.qpic.cn/mmbiz_png/0nIB33cfDvYwyBknISX6sr3Bh26g5WCoMmkpT6mzg64nV0UibJIJW1yz44da29tpJ7T1GxPoicfZ4n1lmmXRJ4icBLmKYN2UUR9US8XMddHNS8/640?wx_fmt=png&from=appmsg)

_  
_

_ 希望今天的分享对你有所启发。  _

_  
_

_  
_

  

预览时标签不可点

微信扫一扫  
关注该公众号



微信扫一扫  
使用小程序

****



****



****



×  分析

__

![作者头像](http://mmbiz.qpic.cn/mmbiz_png/mqhc3Xuogv4J6qTbOhkhePQtveChNISV3RSTzxwaFRPCwsOonHBWDkXZs6p1kWiaRIfpib3B7zRJYz6VghlEc9vg/0?wx_fmt=png)

微信扫一扫可打开此内容，  
使用完整服务

：  ，  ，  ，  ，  ，  ，  ，  ，  ，  ，  ，  ，  。  视频  小程序  赞  ，轻点两下取消赞  在看  ，轻点两下取消在看
分享  留言  收藏  听过

