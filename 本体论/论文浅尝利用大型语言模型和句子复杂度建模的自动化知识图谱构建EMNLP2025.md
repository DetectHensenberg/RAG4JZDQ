![cover_image](https://mmbiz.qpic.cn/mmbiz_jpg/E9ZRhhMLLIdcKMagFERcqY0MULx3NGFEK12dpdl2PmcpOVicTgQ18zIoS9xicczXxEYeAhcXXejUyyOu4GSbXOBDiaESIaP2rIx0QVg95heyP8/0?wx_fmt=jpeg)

#  论文浅尝 | 利用大型语言模型和句子复杂度建模的自动化知识图谱构建（EMNLP2025）

原创  张士杰  张士杰  [ 开放知识图谱 ](javascript:void\(0\);)

_2026年03月02日 19:40_ __ _ _ _ _ _ 浙江  _

![](https://mmbiz.qpic.cn/sz_mmbiz_png/E9ZRhhMLLIdicM3HwTrxH9GklDJmU0Jx4ng2Tc4cXpVhdoQzLd3pZo20kBCn1mdxHEzMR1ZZyte7sxpTCsvpUEHUtQWciaduvNfZHWOIVB024/640?wx_fmt=png&from=appmsg)

> 笔记整理：  张士杰，天津大学硕士，研究方向为知识图谱
>
> 论文链接：  https://doi.org/10.18653/v1/2025.emnlp-main.783
>
> 发表会议：  EMNLP 2025

** 1\. 动机  **

** 当前从海量非结构化文本中自动构建高质量知识图谱（  KG  ）依然是一个长期且尚未完全解决的难题  ，  现有的  KG
构建流程并未真正实现自动化，不仅需要大量人工设计提示词，还依赖人工清洗噪声文本，整个流程分散、难以形成统一的端到端框架。同时，非结构化文本，尤其是科研领域如生物医学文献，其句子往往极长、结构复杂，包含多从句、多谓语以及频繁出现的指代现象，使得大语言模型（
LLM  ）在解析时容易出现理解偏差，导致三元组抽取不完整或出现错误关系。此外，许多现有研究忽视了  “  句子复杂度  ”
对模型抽取能力的关键影响，而句子结构类型（如简单句、复合句、复杂句或并列复合句）在很大程度上决定了  LLM
的推理与关系识别难度。与此同时，科研文本中普遍存在的共指指代现象，例如  “  它  ”  、  “  这种机制  ”  、  “  该药物  ”
等常常指向前文实体，如果不进行准确的共指消解，模型会在实体识别与关系抽取阶段发生偏差，从而显著降低构建  KG
的整体质量。因此，论文提出针对这些挑战构建真正的端到端、自动化的知识图谱构建框架。我们认为，建模并将这些复杂句子类型转换为更简单的形式，能够使  LLM
更有效地进行解释，特别是对于结构化信息提取。  **

** ** 2\. 贡献  ** **

本文的主要贡献有：

(1)  引入了  CoDe-KG  统一自动化知识图谱构建框架，用于关系抽取（  RE  ）和知识图谱构建，该框架借鉴了语言学理论和语义分析。

(2)  提出了  Hybrid CoT + FICL  的混合提示策略，将链式思维  (  CoT  )  与小样例提示  (FICL)
结合，在句子简化任务中实现了  很高  的准确率。

(3)  创新性地提出了  “  句子复杂度语义建模  ”
方法，将学术文本的句子划分为简单句、复合句、并列句、并列复合句以及不完整句，并依据不同句法结构自动匹配最优的提示模式与模型组合。

** 3\. 方法  **

在本研究中，我们提出了一种自动化的知识图谱创建流程  CoDe-KG  ，用于从摘要中创建知识图谱。如图  1
所示，我们的方法包括四个关键阶段：执行共指消解、句子分类、句子转换和关系抽取（  RE  ）。

![](https://mmbiz.qpic.cn/mmbiz_png/E9ZRhhMLLIfhxtUibACbspU6JtufRGiciaMicSJoH2TXU53IQzBYcbod1zO9ap6YLC0qMwHlJL6ibibJ5IOwAibDOyVxrrf70Ewdp5uRMeqDRRE7js/640?wx_fmt=png&from=appmsg)

图  1  总体框架图

(1)  执行共指消解：  通过专家标注与多组提示词  —
模型组合的系统比较，筛选出最优配置，用于处理医学文献中大量存在的指代现象，以避免实体错配、三元组缺失以及错误关系的级联传播。

(2)  句子分类：系统对每个句子进行句子复杂度分类，将其划分为五类句法类型，并为后续选择最合适的简化策略提供依据。

(3)  句子转换：对于复合句、并列句及并列复合句，系统会根据句法类型自动匹配最优的  Prompt–Model  组合实现句子简化

关系抽取（  RE  ）  ：  系统对所有原始简单句以及简化后的句子执行关系抽取，生成三元组，并在  REBEL  、  WebNLG  、  Wiki-
NRE  与  CaRB  等基准上进行验证，最终累计构建出超过  150,000  条结构化三元组，用于生成高质量的知识图谱。

** 4\. 实验  **

实验  1  ：共指消解结果

我们在我们的基准上评估了几个大型语言模型。  大多数模型的结果都很差。表  1  列出了执行共指消解的模型的  F1  得分，并以  ChatGPT
o4-mini-high  和  ChatGPT-4.5  的响应作为基线进行基准测试。  ChatGPT o4- mini-high  总体表现最佳，使用
FICL  提示时的  F1  约为  63%  。我们用粗体标出了最佳开源模型，它与此任务的闭源模型相当。

表  1  ：各模型  F  1  分数比较
![](https://mmbiz.qpic.cn/mmbiz_png/E9ZRhhMLLIeLOjC0y01YH7MUVRBKJlYpAsVf3xW8n3oQgLHkIyib3WIXmySQ92mfMSHnljkkaRO4MJj3sljdIj1xBfAR9RvFuqRCneye1iaq8/640?wx_fmt=png&from=appmsg)

实验  2  ：句法句子分类

我们在训练集上微调了六个基于  Transformer  的模型和两个较小的  LLM  ，并在测试集上评估了它们  ，  表  2
报告了每个模型的测试准确率和宏平均  F1  ，  我们使用  GPT-4o  模型评估了整个测试集。

表  2  ：句子类型分类结果（训练集：  2,00  句；测试集：  5,269  句）
![](https://mmbiz.qpic.cn/mmbiz_png/E9ZRhhMLLIdQuZ0hyciaZedGcyzCeSwyicYoq8k5icF6icnNeBbXYK32icm8mf8gMZ80S5JMrlGib41IoBfrH8PHLh5LA0nwAYzg5oUojIRJ2alibM/640?wx_fmt=png&from=appmsg)

实验  3  ：评估提示策略和语义转换

我们从复杂句、并列句和并列复杂句类别中分别随机抽取  300  个句子，并将它们翻译成简单句。这些  300  个的样本量在其各自的总体中实现了  95%
的置信度，误差范围分别为  ±5.62%  、  ±5.57%  和  ±5.26%  。我们测试了表现最佳的模型，并评估了它们在不同提示策略上的性能。

表  3  ：模型在复合句到简单句转换上的性能
![](https://mmbiz.qpic.cn/mmbiz_png/E9ZRhhMLLIfib06BLTjBSEogsQ0450yiaDqLicU7YznIVUZfktUW37edglEick2UOYL0n5195ec22Crswt4LC7w2LSDdRvgnErNu3PoyjLTkcos/640?wx_fmt=png&from=appmsg)

表  4  ：模型在将复杂句转换为简单句时的性能

![](https://mmbiz.qpic.cn/sz_mmbiz_png/E9ZRhhMLLIdiaxVfoeIU6AHmaib7j3hrgmPBNtFl44h602KgF5lrD81CQaTdUz5xlcXgZU15SGEE0NnGQAXOUqKIMV1VtpHXlgsl3nic0oUZIo/640?wx_fmt=png&from=appmsg)

表  5  ：模型在复合  \-  复杂句到简单句转换上的性能

![](https://mmbiz.qpic.cn/sz_mmbiz_png/E9ZRhhMLLIdxEDVGZsS05ibKdpXRG5raQe5b9lFia0iczXJQ2vIamiadkPwQ9iaVb3MhoMLAMqFs4nRJLa8afczTRWiaEicj31HFNk1sDDF5bImgRU/640?wx_fmt=png&from=appmsg)

由于简单句的总数超过  177,000  ，我们使用了精心设计的  COT + FICL  提示，因为数据显示它表现最佳。注释者  AB  和  CD
研究了从每个被测试模型生成的  100  个句子，并达成一致意见，即  Mixtral-8x7B-Instruct-v0.1
模型表现良好，在解简单句中的关系方面准确率达到  99%  ，其中还包括捕捉文本中的多种关系。

** 5\. 总结  **

论文的研究结果表明，将句子复杂度建模与大语言模型结合，可以显著增强知识图谱构建中的三元组抽取能力，尤其在结构复杂的学术与生物医学文本中，结构化输入能有效提升模型的理解与推理表现。通过
CoDe-KG
框架，作者实现了一个真正意义上的端到端自动化知识图谱构建流程，涵盖共指消解、句子结构分类、句子简化、三元组抽取与图谱构建等关键步骤，并已完整开源供研究与应用使用。研究同时验证了
Hybrid CoT + FICL  是句子简化任务的最优提示策略，可获得  很高的
的精确匹配率。此外，作者也指出未来的改进方向，包括进一步提高共指消解能力、探索弱监督条件下的模型微调策略，以及提升框架在更多领域中的迁移适配性，以推动自动化知识图谱构建的广泛应用。

  

* * *

  

** OpenKG  **  

  

OpenKG（中文开放知识图谱）旨在推动以中文为核心的知识图谱数据的开放、互联及众包，并促进知识图谱算法、工具及平台的开源开放。

![](https://mmbiz.qpic.cn/mmbiz_png/GNpj5fw72EqrajdIDAiaB5IqLYjAV22DXCC8e2lfacd5t5rF2aDmyEN9iaaMicTdGfGWOhHmp1xDw7bxO6ibcdLvew/640?wx_fmt=png)

点击  ** 阅读原文  ** ，进入 OpenKG 网站。  

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

![作者头像](http://mmbiz.qpic.cn/mmbiz_png/GNpj5fw72Er9C33gNMN8EJB0lXvDj3yrQJqR1O53zfha0WrxFAUVONCqoWk7qFG4n2eM3qzkyaUWcsLEKkSiaHQ/0?wx_fmt=png)

微信扫一扫可打开此内容，  
使用完整服务

：  ，  ，  ，  ，  ，  ，  ，  ，  ，  ，  ，  ，  。  视频  小程序  赞  ，轻点两下取消赞  在看  ，轻点两下取消在看
分享  留言  收藏  听过

