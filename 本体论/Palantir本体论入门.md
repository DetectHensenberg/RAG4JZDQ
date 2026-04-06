![cover_image](https://mmbiz.qpic.cn/sz_mmbiz_jpg/4yrjkun1LmsEXLFdbWn2DMAJibIaYpHyRiaYhRiajVib2tZGIJBy706k0ImScAUskgTGw6DrAJSbaYcg9AZj9doIEaYI1iaMG8cAOlxMOmt6vxhQ/0?wx_fmt=jpeg)

#  Palantir 本体论入门

原创  晓晓  晓晓  [ 数据驱动智能 ](javascript:void\(0\);)

_2026年03月13日 09:55_ __ _ _ _ _ _ 北京  _

![](https://mmbiz.qpic.cn/sz_mmbiz_png/4yrjkun1Lmve1IzuCwuKqpUfAH2hD8GLzShvPvricD4uT9FmEiaNBbbGd7WgqcyN16xRyibVHfZfHo1Meib4FVCkMJjaX67K8uicf3fibLncV6jPI/640?from=appmsg)
让我用通俗易懂的方式解释一下本体论在人工智能和机器学习领域的重要性。本文并非人工智能生成，因此您将会轻松愉快地阅读和理解。  本体论的“意义”是什么？
理解某件事的“为什么？”比理解“怎么做？”更重要，因为“为什么？”有助于建立坚实的基础，从而构建出色的商业解决方案。  让我们来看一下下图——
UI层（数据生成层）
——数据在此层生成，并遵循特定的业务原则，运用业务领域知识进行生成。所有业务知识都编码于此层，并在UI界面中呈现。如果您对UI层中的业务代码非常熟悉，那么您就掌握了业务及其原则的全部内容。
OLTP 层  ——当数据进入 OLTP
层时，我们只能获取数据本身，而无法获取业务逻辑，因为业务逻辑仍然保留在用户界面中。这是存储在表中的数据/行的固有特性。数据展示的是“发生了什么？”或“历史记录”，而不是“如何发生”或“未来（业务模型）”。例如，理赔表中的数据显示了
3 行理赔记录，分别对应 3
个不同的状态，但它不会显示理赔状态从“已提交”变为“已审核”再变为“已支付”。或者，数据也不会显示只有在“已审核”步骤完成后才能进入“已支付”状态。希望您能理解我的意思。
![](https://mmbiz.qpic.cn/sz_mmbiz_png/4yrjkun1LmsU68S48I38TWPHkqe2KhqQUnSEPGReBU51uOibb0LicH0LReLicBheJT39kYBZoffgSnKyr4BoAw4sLt9FBcibCuLBVlq70w9xNoE/640?from=appmsg)
OLAP 层  ——一旦在 OLAP 层获得数据，你又会对数据进行大量处理，进行聚合，然后将其呈现以进行报告和分析，聚合等进一步降低了业务部分。
BI/仪表盘层
——这一层决定了我们在上图中看到的整个数据流。首先，我们获取报表和仪表盘的需求，然后从左侧开始获取能够满足这些需求的数据。在这个过程中，我们并不在意数据中是否包含业务信息，因为我们依赖于最终使用BI/仪表盘的人员。因此，如果您缺乏业务知识，您将很难理解这些仪表盘和报表。  
同时，如果我们希望人工智能（AI）能够使用这些数据，那么AI在生成有用的结果时将面临严重问题，它可能会开始产生错误的信息，或者给出完全错误或与预期结果相去甚远的结论。
现在你应该能理解这里的问题所在了：我们有数据，但只有数据，没有生成这些数据的业务流程的详细信息。业界想用人工智能和人工智能代理来取代右侧的业务用户，但如果我们不利用业务知识来丰富数据，这样做行不通，或者说无法取得最佳效果。
那么本体论究竟是什么？  本体 = 数据 + 业务知识 + 业务约束 + 业务流程  从下面的更新图片中可以看到，一旦添加了本体，您仍然可以继续支持传统的
BI/分析仪表板，但现在由于数据有了本体，AI/ML 也可以发挥作用，极大地支持业务活动。  现在，就业务流程、数据生成规则、业务流程和业务约束而言，UI
和 OLAP 都处于同一水平。  现在，数据不仅显示“发生了什么？”（最终事件），还显示“它是如何发生的？”（业务流程）和“为什么会发生？”（商业模式）。
![](https://mmbiz.qpic.cn/mmbiz_png/4yrjkun1LmtibEBFJ1KzicPgVaNguJWjVpK9BJ5F0sia3u3IibRWqlJsg7W2HcOgttKg2KRQJYt7uLGruqdcqusB7TpIpNGLVHXFzicNuz242F24/640?from=appmsg)
本体示例（简单业务）  让我们从上一节讨论过的非常简单的例子开始。（一个典型的索赔表会有很多行和列，但为了便于理解，我们这里只用了一个小表格。）
![](https://mmbiz.qpic.cn/mmbiz_png/4yrjkun1LmsdVaWJCVfrXXxbupIctx2XNeWuslbBFgp8ickvGzEXohelialDf4gt8QkqnvbHmyhLFA4M3n9vAjAPZIDia2xUIHwToWiadfB2icyk/640?from=appmsg)
如果您使用StatusDate，则可以在此表中找到事件顺序，因此在这个典型的示例中，业务事件顺序是存在的，但被隐藏了（我们还将看到数据中没有业务详细信息的示例）。
关于这种隐藏的知识，仍然存在很多问题。  1\.  如果您位于某一行或您的逻辑正在处理某一行，它将无法了解此索赔业务流程中的其余行/步骤。  2\.
如果索赔仅处于“已提交”或“已接收”状态，则数据中没有任何业务信息可以说明该索赔的下一步步骤是什么。  3\.
它也没有表明“待处理”是一种可选状态，索赔也可以从审核进入裁决阶段。  4\.  索赔的最终状态是什么？
因此，知识是存在的，但它隐藏得非常隐蔽，难以获取，甚至根本无法获取，也就无法用于人工智能/机器学习。但如果仪表盘是由业
务用户使用的，那么业务用户就拥有足够的知识和经验来理解仪表盘中显示的数据和状态。  现在让我们来看一个添加了本体论的相同例子。
除了上表所示的数据外，我还提供了以下详细信息，解释索赔的业务审批流程。该本体可以独立于数据存在，使人工智能/机器学习能够查看业务流程并根据该业务流程使用数据。
![](https://mmbiz.qpic.cn/sz_mmbiz_png/4yrjkun1LmvF6vXQbibpdMxicLeIQhkHibylMRmibIPJUtz6UCWibD9JCaZpAxyU2e0qgw77DagAUQhDU0y33icNaQ9Lib7b5eJLJicvORrAvSJ2odM/640?from=appmsg)
您也可以提供如下相同的业务流程。  已提交 → 已收到 → 审核中 → 待处理/已裁决 → 已批准/部分批准 → 已汇款 → 已支付
有人可能会问，如果明天添加了新的状态怎么办？如果您使用图数据库（例如 Neo4j 等），则可以通过单个命令获取所有关系，从而自动处理这种情况。
有一点我不想让您错过，那就是，这些状态不仅是下图所示的数据的一部分，也是上图所示的业务流程的一部分。
![](https://mmbiz.qpic.cn/sz_mmbiz_png/4yrjkun1LmtR5lbe51lOEOzTPykTAJYTzhsYiaqrsSeY3HSDXfiaCMn0BzeMw38xp66XrK6epYMQjjOFYKMRBIbrZlotVZE5AeVTI8TP0jceU/640?from=appmsg)
所以，你实际上是了解了状态之间的相互关系，以及状态与索赔之间的关系。  这只是一个小例子，用来说明缺少本体的数据在人工智能/机器学习用例中的使用有多么困难。
本体示例（复杂业务）  在上面的例子中，我们看到表中存在一个业务详情，但它无法重用或无法获取。有些情况下，业务规则甚至根本不存在于数据中。让我们来看一个例子
![](https://mmbiz.qpic.cn/mmbiz_png/4yrjkun1LmsEr2XJRqHibfSdCjn2cawfRnEKH7Ej7jibVm5ib5oJLoK8Gs3c4djL4w2OrCS4srXPyls5tqF3bDibN2vc79yWRZBUbxHJdV97Kbc/640?from=appmsg)
我们不知道在创建上图所示数据时是否应用了以下规则。  1\.  HMO 需要初级保健提供者（PCP 指标）  2\.  终止合同需提前90天通知  3\.
供应商加入网络所需承担的义务  这样的例子不胜枚举，现在你可以回到第一张图片，它展示了完全相同的情况：UI 拥有所有生成数据的业务规则，但当数据传递给
OLTP 和 OLAP 时，数据本身只显示事实，没有任何业务上下文，这使得它几乎无法用于 AI。
因此，当您不仅需要数据，而且还想了解数据的创建方式、执行的规则以及应用的约束等细节时，您谈论的就是  本体论。  Palantir 中的
Ontology++  （根据 Palantir 的定义，这是运营数字孪生）
到目前为止，我们刚刚了解了本体是什么，以及它对于人工智能应用和常见分析的重要性。Palantir
中的本体应用更进一步，不仅用于人工智能/分析，还用于运营目的。这对于来自其他平台的用户来说非常重要，尤其是那些之前只将数据/图数据库/本体用于报告和分析的用户。
Palantir 在本体论的基础上增加了操作、安全、治理等功能，使其超越了单纯的语义数据模型，并将其称为可操作的数字孪生。
![](https://mmbiz.qpic.cn/mmbiz_png/4yrjkun1LmsDVqNohI38nicHFeDFVR5wXBwvvXXYIt2caWVZwfGIHBic77KxyLr1kCmQpn1lNFVUeYEicVqdkLuDDtYS5F9qbFtfaX3loIhr2o/640?from=appmsg)
其他本体论与Palantir本体论的比较  ：
在报表和分析层，如果我们从用户界面（数据生成的地方）复制/模拟数据和业务流程（本体），我们称之为“数字孪生”。通过数字孪生，您可以查看发生了什么以及事物的现状。但在
Palantir 的案例中，我们不仅这样做，还添加了操作部分，使我们能够采取相应的行动，因此它被称为“操作型数字孪
生”。我将在下一节中用通俗易懂的方式解释操作型数字孪生。  什么是运营数字孪生？
让我们来看下图，它详细解释了“数字孪生”的概念。我以CRM为例，展示了如何通过Palantir平台执行操作。  1\.  数据从 CRM 复制到
Palantir Foundry 作为数据资产（频率根据业务需求而定）。  2\.  Palantir 中构建了本体，其中包含“批准订单”等操作。  3\.
用户点击“批准订单”，同时查看本体屏幕上的所有其他可用信息（您可能还有来自其他平台（如 ERP）的数据，这些信息也有助于做出该决定）。  4\.
数据直接在 CRM 系统中更新（通常不在代工厂数据资产中更新）。
![](https://mmbiz.qpic.cn/mmbiz_png/4yrjkun1Lmvc3ibvqwr4yiabMicb0Gsy3tw0CBK1EoLlES3Lr0kN70NrwaibkJW4QVOwldhSQgZV73lVViayndDQRBkWSHBZMOvsaDPhmu7zc0lI/640?from=appmsg)
小  结
我们已经充分探讨了本体论的概念，首先理解了本体论是什么，然后结合Palantir的背景理解了本体论。我们也了解了“运营型数字孪生”中“运营”部分的整体运作流程。
![](https://mmbiz.qpic.cn/sz_mmbiz_png/QcibqWcEM8EkOPYC3BueiaqIgk2Yef0iaQBzV3pScmHdvQGVrqErofgkIQsGykXYUpaWaRrDic52o36NVS43mnPJ5A/640?wx_fmt=png)  
![](https://mmbiz.qpic.cn/sz_mmbiz_png/QcibqWcEM8EkOPYC3BueiaqIgk2Yef0iaQBykPVuR1y46uuZk6jgmr43flB99o8ehnvhzgoMDrzzTko97ydHmcUFQ/640?wx_fmt=png)  

往期推荐

[ 2026 年智能体人工智能治理框架：风险、监督和标准
](https://mp.weixin.qq.com/s?__biz=MzIwOTIyMDE1NA==&mid=2247504573&idx=1&sn=f09a2b450dce4a0badc12781aedd383b&scene=21#wechat_redirect)

[ MLOps 中的数据质量保证和治理
](https://mp.weixin.qq.com/s?__biz=MzIwOTIyMDE1NA==&mid=2247504568&idx=1&sn=da393ac80160aeddc62715627e74183d&scene=21#wechat_redirect)

[ 在人工智能领域，本体是什么？
](https://mp.weixin.qq.com/s?__biz=MzIwOTIyMDE1NA==&mid=2247504563&idx=1&sn=bdba384ff107ecd22c1ad2cc4b9bf111&scene=21#wechat_redirect)

[ 检索增强生成（RAG）详解：从基本原理出发
](https://mp.weixin.qq.com/s?__biz=MzIwOTIyMDE1NA==&mid=2247504558&idx=1&sn=1ab9fbe313f2124478ee18b46f702ea8&scene=21#wechat_redirect)

[ 一文读懂企业如何更好的开展AI项目建设：来自实战的经验和教训
](https://mp.weixin.qq.com/s?__biz=MzIwOTIyMDE1NA==&mid=2247504553&idx=1&sn=62a9e56dce33d8388ab9cadff97b61dd&scene=21#wechat_redirect)

[ Gemini Enterprise 如何处理敏感数据
](https://mp.weixin.qq.com/s?__biz=MzIwOTIyMDE1NA==&mid=2247504548&idx=1&sn=7b878d78dce66ce4c2e0b211cf38a287&scene=21#wechat_redirect)

[ Malt 公司AI应用和发展的实际案例|在不陷入混乱的情况下实现人工智能广泛应用
](https://mp.weixin.qq.com/s?__biz=MzIwOTIyMDE1NA==&mid=2247504543&idx=1&sn=b1013dcd703c1c348087d32971a50d86&scene=21#wechat_redirect)

[ 全国首部“AI高质量数据集验收”标准，现公开征集起草单位和个人
](https://mp.weixin.qq.com/s?__biz=MzIwOTIyMDE1NA==&mid=2247504533&idx=1&sn=693eb6622481c51e92ad1007093fa237&scene=21#wechat_redirect)

  

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

![作者头像](http://mmbiz.qpic.cn/mmbiz_png/4yrjkun1LmuaM4qZ0QlBLOTflH4HsboicOqsse69g7ODaVnkfYibCwucicJPnZuExhiaMf91vvEjD7nNfjEY4pibkIAIY9UJxIdtH70qhDFibUAVk/0?wx_fmt=png)

微信扫一扫可打开此内容，  
使用完整服务

：  ，  ，  ，  ，  ，  ，  ，  ，  ，  ，  ，  ，  。  视频  小程序  赞  ，轻点两下取消赞  在看  ，轻点两下取消在看
分享  留言  收藏  听过

