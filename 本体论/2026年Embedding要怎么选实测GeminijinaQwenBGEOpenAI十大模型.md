![cover_image](https://mmbiz.qpic.cn/mmbiz_jpg/BDbj75fnJWddndM0VYyY8GtSERib1IzwOwr01cPpR352ZuI4dF38ZoZh2wodY0XY9hQ2MS1AVD5qH9TFFNxmuIAnGOkbZ9D9Q8M8eZxEn9jo/0?wx_fmt=jpeg)

#  2026 年，Embedding要怎么选？（实测Gemini 、jina、Qwen、BGE、OpenAI十大模型）

原创  张晨  张晨  [ Zilliz ](javascript:void\(0\);)

_2026年03月23日 18:38_ __ _ _ _ _ _ 上海  _

![图片](https://mmbiz.qpic.cn/mmbiz_jpg/MqgA8Ylgeh7JrHg5C05DE5OutodWics1QLcLRJdNhvLITaticbSpvIzCBLa6QSQgkXnjR6ozgWibomGQ8Q67gPdvw/640?wx_fmt=webp&from=appmsg&wxfrom=5&wx_lazy=1&tp=webp#imgIndex=0)

最近和开发者交流，发现一个很有意思的现象，很多初学者做RAG，一上手就直奔OpenAI的text-
embedding-3-small。的确，这是个无功无过的模型。

但在这之后，进阶版的embedding模型选型，就不知道从何下手了。

一方面，一个生产级的RAG，通常会涉及图片、文字、PDF等等多种文件形态，以及合同、sop、通知等不同内容类型，
不同类型的数据处理，需要不同的embedding模型。

另一方面，在技术上，
embedding模型也在同步发展两个截然不同的方向。一个是往深了做，深耕单模态优化，针对法律、代码这类特定领域打磨性能，做到极致；另一个是往广了做，发力多模态融合，力求用一个模型搞定文本、图像等多种数据形态
。不久前，Google 发布的集  齐  ** 五种模态  ** （文本、图像、视频、音频、PDF 文档），100+ 语言，原生
MRL（维度可按需裁剪），3072 维输出的  ** Gemini Embedding 2 Preview，就是其中一大代表。  **

![](https://mmbiz.qpic.cn/sz_mmbiz_png/BDbj75fnJWeEGa8nu8EgEibxwiaW1Y2ibWAURb6LZruIWicCtvYCicl5XJV7UzCU7apfG1Lrvs3EqeKjhiauTVBtZJR9rCia49lnZcNsMOFzATlGHE/640?wx_fmt=png&from=appmsg)

embedding模型数量越来越多，场景要求也越来越细分，这就导致，选型的难度，也越来越大了。

那么，embedding模型到底怎么选，我们选取了2025到2026年推出的热门embedding模型，专门围绕公开Benchmark未覆盖的生产场景，设计了一套专项测试。

##  01

##  参赛模型

我们一共选了  ** 10 个模型  ** ，覆盖 API 服务和开源本地部署两种形态，也加上了 OpenAI text-
embedding-3-large、CLIP ViT-L-14 这些经典模型作为对照。先看看都有谁：

![](https://mmbiz.qpic.cn/sz_mmbiz_png/BDbj75fnJWfAL1ibu34M924sQDm2FSOslFyOvF72fvGIaczQm4sPDdjpQD7UaPtvDKCAcuGf6X3c0LhPT7icIx0O4SIyBM36LQBzByQ3wUImQ/640?wx_fmt=png&from=appmsg)

简单介绍一下各家：

** Gemini Embedding 2  ** 是 Google 2026 年 3 月发布的首个全模态 embedding 模型，五种模态都支持。

![](https://mmbiz.qpic.cn/mmbiz_png/BDbj75fnJWfOkhO9aFMl20VAXpwF7d4Pkhtbeoxw3L2jAkl2uwDK0EWdnW6STjIiavAs541Ozzu5dQSgUtvzEsZfGuD8XZicZW88SuYqLiaZdM/640?wx_fmt=png&from=appmsg)

** Jina Embeddings v4  ** 基于 Qwen2.5-VL-3B 构建，3.8B 参数。通过三个 LoRA
适配器（retrieval.query / retrieval.passage / text-matching）切换不同检索场景。支持文本、图像和 PDF。

![](https://mmbiz.qpic.cn/sz_mmbiz_png/BDbj75fnJWcicONv3Vf3cwyLCYYbqn1akxdJy0mVO7q7WxRIF4fX4SV9jz9030VhsXcSxhJ5Le3LOoFiadTt4BicHp9icURx0Kg1n4c6jgjbXRc/640?wx_fmt=png&from=appmsg)

** Jina CLIP v2  ** 是 Jina AI 基于 CLIP 架构的现代版本，专注文本-图像跨模态对齐，支持多语言。

** Voyage Multimodal 3.5  ** 来自 Voyage AI 团队，2025 年 2 月被 MongoDB 以 2.2
亿美元收购。文本、图像、视频都支持。

![](https://mmbiz.qpic.cn/sz_mmbiz_png/BDbj75fnJWdMLDajaibMhcYwtLdoCMgVfYFaXfm2xIAfsVj6JLWkMq0STP4sglUqicJXW9ItqXIxyhv4ibINUnHyeVLQU125FKMS4TiauG29qtA/640?wx_fmt=png&from=appmsg)

** Qwen3-VL-Embedding  ** 是阿里 Qwen 团队的开源多模态 embedding 系列，有 2B 和 8B 两个版本。我们选了
2B 版本测试，因为它刚好能跑在一张 11GB 的消费级 GPU 上，更能体现轻量部署的可行性。

![](https://mmbiz.qpic.cn/mmbiz_png/BDbj75fnJWdnIWC6SRpqGxKRIicBRCLypibSianfDfhWCCwn96nd2miaoKrCXwCSw8icvMR8W7X9cFgVvf0DYvEPqPWFjichMX9AZU70uvHUCa08I/640?wx_fmt=png&from=appmsg)

** Cohere Embed v4  ** 和  ** OpenAI  ** ** 3-large  ** 都是纯文本模型，MTEB
细分榜单上的常客，RAG 场景用得最多。

![](https://mmbiz.qpic.cn/mmbiz_png/BDbj75fnJWfPa28RGITSkYbSaH62VEGAtU9cCyVP81SN41vTg8iaVeUwveSRoLibPiaMJ5NHrUmqT0ll40nM18SyLHKc63qOcS1OP2QZ1zcAAU/640?wx_fmt=png&from=appmsg)

** BGE-M3  ** 是智源研究院（BAAI）的开源多语言 embedding 模型，568M 参数，支持 100+ 语言，中文开源
embedding 领域的标杆。

![](https://mmbiz.qpic.cn/sz_mmbiz_png/BDbj75fnJWfML2J2jN668jXmZgd9sibMC80n80xkAK2gQkb99ylMcg3QNoJYITAib5aHnenjI2p0KsdGickpBKWYcEnxKfPsabm9BzXv69Ucgk/640?wx_fmt=png&from=appmsg)

** mxbai-embed-large  ** 和  ** nomic-embed-text  ** 分别来自德国 Mixedbread AI 和美国
Nomic AI，都是轻量级开源模型。mxbai 335M 参数，英文 MRL 表现突出。nomic 只有 137M 参数，是这次测试中最小的模型。

![](https://mmbiz.qpic.cn/mmbiz_png/BDbj75fnJWc7EE1kxzUianPeDLwLobqdiaO3nv2nMksgRZeYBQmEZpj52omtqHUa2Zy7FicjRJ9OEMKrKe6ibeAbk8IPZ9X0dhWXUTLkrTgqL9c/640?wx_fmt=png&from=appmsg)
![](https://mmbiz.qpic.cn/mmbiz_png/BDbj75fnJWcFs6uwD9Jptj08qTrvuJpR24xpSTzd9rcicYgpycX2k3AoSxwpEB9U5XpKnxRM1XJwanGCCqOicc1ibzNAUBoMXWJ6pyNbQvtM2g/640?wx_fmt=png&from=appmsg)

* * *

##  02

##  现有 Benchmark 的局限性与我们的思路

模型选好了，接下来要定测试项目。我们先看了一下现有的 benchmark，发现不太够用。

** MTEB  ** （Massive Text Embedding Benchmark）是目前最权威的 embedding
评测体系，但有几个维度没有覆盖：

  * ** 纯文本  ** ：不涉及图片、视频等多模态输入 

  * ** 同语言检索  ** ：虽然有多语言子集（如 MIRACL），但测的是同语言内检索，没有「中文 query 检索英文文档」这种跨语言项目 

  * ** 不测维度压缩  ** ：不评估 MRL 裁剪后的质量衰减 

  * ** 长文档覆盖有限  ** ：虽然有 LongEmbed 子集，但主流评测仍以千 token 级别的短文本为主，缺少万字级文档的系统测试 

** MMEB  ** （Massive Multimodal Embedding Benchmark）补上了多模态，但也有不足：

  * ** 不含 hard negative  ** ：干扰项和正确答案差异太大，容易拿高分但区分不出模型之间的细微差别 

  * ** 不测跨语言、不测 MRL、不测长文档  **

这些缺项恰好对应当下开发者在建 RAG / Agent / 向量检索系统时最常遇到的实际问题。所以我们设计了四个评测任务：  **
跨模态检索、跨语言检索、大海捞针、MRL 维度压缩  ** 。

因此，针对以上四个问题，我们设计了四个测评维度：

###  维度一：跨模态检索（文本 ↔ 图像）

** 场景  ** ：电商以图搜图、图文混合知识库检索、多媒体内容理解。

** 任务设计  ** ：从 COCO val2017 中取 200 对图文。文本是 GPT-4o-mini 生成的详细描述，每张图还配了  ** 3 条
hard negative  ** ——和正确描述只差一两个细节的干扰项。模型需要在 200 张图 + 600 条干扰描述的混合池中完成图文双向检索。

下面是数据集中的一个实际样例：

![](https://mmbiz.qpic.cn/sz_mmbiz_jpg/BDbj75fnJWdC9LhAqeoo66XsPbIkicNIQ7FiaHWibC75sV9gdUqPZVcOyEibLhu5cwKBxH69hXibJ9PWF0IYLfrIZ9g3lfrHbY7oiby6HZoPPiapm8/640?wx_fmt=jpeg&from=appmsg)

> ** 正确描述  ** ：  _ "The image features vintage brown leather suitcases with
> various travel stickers including 'California', 'Cuba', and 'New York',
> placed on a metal luggage rack against a clear blue sky."  _
> （图中是复古的棕色皮革旅行箱，上面贴着「California」、「Cuba」、「New York」等旅行贴纸，放在金属行李架上，背景是晴朗的蓝天。）
> ** 干扰项（仅改动关键词）  ** ：模型必须真正「理解」图片中的细节，才能区分这些 hard negative。

** 计分方式  ** ：

  1. 所有图片和文本（200 正确 + 600 干扰）生成 embedding 

  2. ** 文本找图 (t2i)  ** ：每条描述在 200 张图中找最像的，第一名对了就得分 

  3. ** 图找文本 (i2t)  ** ：每张图在 800 条文本中找最像的，第一名是正确描述（不是干扰项）才得分 

  4. 最终分  ` hard_avg_R@1  ` = (t2i 得分率 + i2t 得分率) / 2 

####  结果

这个结果我们自己也没想到。

![](https://mmbiz.qpic.cn/sz_mmbiz_png/BDbj75fnJWfS3PV5AzEOxCBbwrV3chFCJmNQTqebSMmZibvl8yNjbzB4negTicSMoBhIGiaYfOicF94ppJN8MYrsOWicFPCc5LyNPem94iaiaoHQYA/640?wx_fmt=png&from=appmsg)

Qwen3-VL-2B 以 hard_avg_R@1 = 0.945 位居第一，超过了 Gemini（0.928）和 Voyage（0.900）。一个 2B
参数的开源模型跑赢了闭源 API。

为什么？看一个指标就明白了：  ** 模态间隙（Modality Gap）  ** 。

> ** 什么是模态间隙？  ** Embedding
> 模型会把文本和图片都映射到同一个向量空间。但实际中，文本向量和图片向量往往「聚居」在不同区域。模态间隙衡量的就是这两个聚居区之间的距离（文本向量均值和图片向量均值的
> L2 距离）。间隙越小，跨模态检索越容易做准。

![](https://mmbiz.qpic.cn/mmbiz_png/BDbj75fnJWcvz2Vacu2iaTV9oWd5MeFFMkThWxyX8ug0EgmHQU3hG5lQxaGYAnsZgDajRNZb28XY58JM1U7fbzA9V35d0qoy5zhrLJj9z8Bo/640?wx_fmt=png&from=appmsg)
![](https://mmbiz.qpic.cn/mmbiz_png/BDbj75fnJWcGtiaT6vqOOZojKl9hL1lYb2UjLiapwonibXUmOICeqffj8bGqhZo4xl5XjMafibcxs8DNC208a1WUqMdsxSPpia6tm7920E9BOvZk/640?wx_fmt=png&from=appmsg)

Qwen3-VL-2B 的模态间隙只有 0.25，远低于 Gemini 的 0.73。在 Milvus 中建图文混合 collection
的话，模态间隙小意味着文本和图片向量可以直接混在同一个索引里，不用额外处理。

跨模态测试的结论比较清楚：  ** 多模态能力上，开源小模型已经能和闭源 API 掰手腕了。  **

###  维度二：跨语言检索（中文 ↔ 英文）

** 场景  ** ：中英文混合知识库，用户中文提问但答案在英文文档里，或反过来。

** 任务设计  ** ：166 对手工构建的中英平行句子，分三个难度级别。每个语言另加 152 条 hard negative 干扰。

![](https://mmbiz.qpic.cn/mmbiz_png/BDbj75fnJWfGAr4SFGciavrQn0ZRElyic5Xr5M8la7fuMaIbyB8IguLeXp5MicrHojn2xicyeA0WRgc2jp03BPm7geX9Mc0aaicvaHpllHvdFEBY/640?wx_fmt=png&from=appmsg)

** 计分方式  ** ：

  1. 所有中文（166 + 152 干扰）和英文（166 + 152 干扰）文本生成 embedding 

  2. ** 中→英  ** ：每条中文在 318 条英文中找到正确翻译 

  3. ** 英→中  ** ：反过来 

  4. ` hard_avg_R@1  ` = (中→英得分率 + 英→中得分率) / 2 

####  结果

![](https://mmbiz.qpic.cn/sz_mmbiz_png/BDbj75fnJWevrwgEia5PnsLxgvp5xyc4TzlYqwKz0UnGyRNcTEjBpYCuAPLibGwC78k5ao63Y2v4UiatKwIVkCdq8g1b1L8Q1DpH7cjMhcCdDI/640?wx_fmt=png&from=appmsg)

这一回合 Gemini 表现最好，0.997 接近满分，包括「画蛇添足」这种成语难度也答对了。在 Hard 分组中，Gemini 是唯一保持 R@1 =
1.000 的模型。

![](https://mmbiz.qpic.cn/mmbiz_png/BDbj75fnJWdgS4uKfOzSPjQ55aFas9XL2EnAnicZ3mOiaaLddVSBqOlrxmQLnjwyrBMfRAkhMqm1uxbQBZzSfHyFchhvIefqO1U3EVtEUqOPw/640?wx_fmt=png&from=appmsg)

这个任务把模型分成了泾渭分明的两拨：前 8 个（hard_avg_R@1 > 0.93）有多语言能力，nomic 和 mxbai（R@1 <
0.16）基本只认英文。中间没有过渡地带。

###  维度三：关键信息检索

** 场景  ** ：RAG 系统处理长篇法律合同、研究论文。Embedding 模型在几万字的文本中还能抓到关键信息吗？

** 任务设计  ** ：Wikipedia 文章作为「大海」（4K-32K 字符），在不同位置（开头 / 25% / 50% / 75% /
结尾）插入一条虚构的事实信息作为大海里的那个「针」。看模型能否通过 query 的 embedding 在含针文档和不含针文档之间做出正确判断。

> ** 样例  ** _ 针  _ ：  _ "The Meridian Corporation reported quarterly revenue
> of $847.3 million in Q3 2025."  _ （Meridian 公司 2025 年第三季度营收 8.473 亿美元。）  _
> 查询  _ ：  _ "What was Meridian Corporation's quarterly revenue?"  _ （Meridian
> 公司的季度营收是多少？）  _ 大海  _ ：一篇 32000 字符的 Wikipedia 文章（比如关于光合作用的），中间某个位置藏着那条营收信息。

** 计分方式  ** ：

  1. 生成 query、含针文档、不含针文档的 embedding 

  2. 如果 query 和含针文档的相似度更高，判定为「找到了」 

  3. 在所有长度和位置上取平均准确率 

** 最终指标  ** ：  ` overall_accuracy  ` ，  ` degradation_rate  `
（从最短到最长文档的准确率衰减）。

####  结果

这个任务的区分度比预期大不少。直接看热力图，绿色满分，黄色开始退化，红色严重退化，灰色是超出模型能力没跑的：

![](https://mmbiz.qpic.cn/mmbiz_png/BDbj75fnJWeHou5ic8nUXfhRIibN8C8UYic5kA93x8ciaUf5tV1ic2E3OusZfqt8vWwwRgJ7iaRtQ0BKm7icmAoOAWRzUQ5vj6wLhW4hMMRxUX9mxQ/640?wx_fmt=png&from=appmsg)

完整成绩：

![](https://mmbiz.qpic.cn/sz_mmbiz_png/BDbj75fnJWcXMM1VedPKCtkpUSpBic441DCIypNvAUiaVRj0XHsiclKTXHprVrbHwrnpibwQuibicqLDfRspPzAsNP85XziaU1VyWL8eAVxzgl92ibk/640?wx_fmt=png&from=appmsg)

> 「—」表示该长度超出模型上下文窗口限制或未测试。

大致分三档。Gemini、OpenAI、Jina v4、Cohere 在各自上下文范围内几乎满分。BGE-M3（568M）到 8K
开始轻微退化（0.92）。335M 以下的 mxbai、nomic 则在  ** 4K 就开始明显下降  ** ，8K 准确率只有 0.40-0.44。

Gemini 是唯一跑完 4K-32K 全程且满分的。另一边，335M 以下的模型在 4K 字符（大概 1000 tokens）就掉到了
0.46-0.60——如果你的 RAG 系统文档平均超过 2000 字，用这些模型需要留意。

###  维度四：MRL 维度压缩

> ** 什么是 MRL？  ** MRL（Matryoshka Representation Learning，俄罗斯套娃表示学习）是一种训练技巧，让
> embedding 向量的前 N 维本身就构成一个有意义的低维表示。举个例子，一个 3072 维的向量，你只取前 256
> 维，仍然能保持不错的语义质量。维度减半，存储成本也减半。

![](https://mmbiz.qpic.cn/sz_mmbiz_png/BDbj75fnJWf8GbGdoZ2ax612kqFnd8Tv3icQObX8ZBQDKafheicGiaD4qSZicxpUZ90H3qxFN9WFSJxOtSCXDdNmuJA6icCicpORjic8yf1WHpYv3w/640?wx_fmt=png&from=appmsg)

** 任务设计  ** ：使用 STS-B（Semantic Textual Similarity Benchmark）的 150
对句子，每对都有人工标注的语义相似度评分（0-5 分）。模型对这些句子生成 embedding，先用全维度，再截断到 256 / 512 / 1024
维，看在每个维度下与人工评分的排序一致性。

![](https://mmbiz.qpic.cn/mmbiz_png/BDbj75fnJWdSKibc1yBtk2VBw64VK4Ciav2E4QiaRQLRlj5nGcBYtR9IwuUvUrILGggMdrD856UNeCsHY9uKn3aibLicvqya954WKj401qiaT52sY/640?wx_fmt=png&from=appmsg)

** 计分方式  ** ：

  1. 每个维度下，计算每对句子 embedding 的余弦相似度 

  2. 将模型给出的相似度排序与人工评分排序做  ** Spearman 秩相关  ** ，得到 ρ 值 

> ** 什么是 Spearman ρ？  ** Spearman 秩相关系数衡量两个排序的一致性。人工觉得 A 对最相似、B 对次之、C 对最不像，模型的
> embedding 相似度排序也是 A > B > C，那 ρ 就接近 1.0。ρ = 1.0 是完全一致，ρ = 0 是毫无关联。

** 关键指标  ** ：Spearman ρ（越高越好），  ` min_viable_dim  ` （质量衰减不超过 5% 的最小维度）。

####  结果

如果你打算在向量数据库中通过截断维度来降低存储成本，这个结果很关键。

![](https://mmbiz.qpic.cn/sz_mmbiz_png/BDbj75fnJWe2JuialQ5k3ATrUuAibvMc1ZzIiazR33LzWicwnqYTIcqKibCggiaGvzuJV3wPTEQNpPw7XK6icGiaGMicXLO1Cpd7ia4OxqT5c4HXrnVDA/640?wx_fmt=png&from=appmsg)
![](https://mmbiz.qpic.cn/mmbiz_png/BDbj75fnJWflM8fic030m3OhChATFPp6gxLMy9P15Z6B3icvrxedF9B4sz3n1pUYtx2oErF8icvfUDh5Gqn96dh6omUEficnvVLduI8y2icibyH0g/640?wx_fmt=png&from=appmsg)

这一回合 Gemini 排在最后。mxbai-embed-large 只有 335M 参数，MRL 排第三，超过了 OpenAI 3-large。Jina
v4 和 Voyage 之所以在 MRL 上突出，也是因为训练时专门优化过 MRL
目标函数。维度压缩能力跟模型大小关系不大，训练的时候有没有专门练过才是决定因素。

> ** 注意  ** ：MRL 排名反映的是维度压缩后的语义保持能力，跟全维度下的语义理解质量是两回事。Gemini
> 全维度下的检索能力很强（跨语言和跨模态已经证明了），但在这个瘦身测试中成绩偏低。如果不需要维度压缩，这个项目的参考价值有限。

四个维度测完下来，每个模型的长处和短板都比较清楚了。把所有成绩放到一张表里看看全貌：

###  总成绩一览

![](https://mmbiz.qpic.cn/mmbiz_png/BDbj75fnJWeHPYajQqgxiaczE0icjkIk3ictAxlicPgib1taUU5mP9TicRr1A3iasUicXbKp1PxlOhm2aic0R67dDEbRCDxONAfOZicz2aJjwic7H13vlI/640?wx_fmt=png&from=appmsg)

> 「—」表示模型不支持该能力或未测试。CLIP 作为 2021 年的基线对照。

可以发现：  ** 没有一个模型能在所有任务上同时拿第一  ** 。Gemini 跨语言和长文档最强但 MRL 垫底，Qwen3-VL-2B 跨模态第一但
MRL 中游，Voyage 各项都不错但没有一项第一。每个模型的成绩单形状都不一样。

##  03

##  总结与选型建议

** 跨模态  ** ：  Qwen3-VL-2B（0.945）拿了第一，Gemini（0.928）第二，Voyage（0.900）第三。开源 2B
模型胜过闭源 API，模态间隙是关键差异。

** 跨语言  ** ：  Gemini（0.997）遥遥领先，成语级别的中英对齐也能满分。前 8 个模型都在 0.93
以上，英文专精的轻量模型则直接归零。

** 大海捞针  ** ：API 和大型开源模型在 8K 以内基本满分，335M 以下模型 4K 就开始退化。Gemini 是唯一跑完 32K 全程满分的。

** MRL 维度压缩  ** ：Voyage（0.880）和 Jina v4（0.833）领先，裁到 256 维衰减不到
1%。Gemini（0.668）垫底。

而在综合维度上，  Gemini Embedding 2 的确可以算得上是最新的embedding模型之王  。

** 强项  ** ：  跨语言第一（0.997），大海捞针第一（1.000），跨模态第二（0.928），模态覆盖最广（五种模态，其他模型最多三种）。

** 弱项  ** ：  MRL 维度压缩排名靠后（ρ=0.668），跨模态被开源的 Qwen3-VL-2B 超越。

如果不需要维度压缩，Gemini 在跨语言 + 长文档的组合场景上目前没有对手。但跨模态精度和维度压缩上，专精型模型做得更好。

基于以上测试结果，决策流程供参考如下：

![](https://mmbiz.qpic.cn/mmbiz_jpg/BDbj75fnJWdoOicoKfRLmxo6Go1SrjyJ4W6rdMmzPFjS1opFkXS45axGSzjP7Yt2meQNfibfSVibtTpPXMciay274gAaY4GQ1iben67Fy5slDoCI/640?wx_fmt=jpeg&from=appmsg)

##  写在最后

四个回合跑下来，感触还挺多的。

几年前跨语言语义对齐还是论文里的研究方向，现在调个 API 就能用。  五年前图文检索得专门训 CLIP，现在一个通用模型能同时处理文本、图片、视频、音频和
PDF。这个领域的变化速度，比大多数人感知到的要快。

另一个让我印象深刻的是开源的追赶速度。  Qwen3-VL-2B 只有 2B 参数，跨模态精度却超过了所有闭源 API。BGE-M3
跨语言能力也不输多数商业服务。在 embedding 这条赛道上，数据质量和训练策略越来越重要，模型规模和算力投入的权重在下降。不用担心被绑死在哪家 API
上，开源这边总能找到替代方案。

最后说回选型这件事。  今天这篇文章的结论，放到一年后大概率得改。与其花时间纠结到底选哪个模型，不如把评测流程搭好
——清楚自己的业务场景和数据长什么样，用自己的数据搭一套能快速验证新模型的测试流程，新东西出来的时候跑一轮就知道行不行。公开的 benchmark
也值得参考，比如 MTEB、MMTEB、MMEB，但最终还是要回到自己的场景里验证。本文的评测代码也开源在
GitHub，有需要可以参考。（链接都在下方参考资料里）长远来看，建立这样的评估能力比选对某一个模型更有价值。

最后说一下这次测试的不足  。有一些模型没来得及测，比如 NVIDIA 的 NV-Embed-v2、Jina
v5-text。另外，视频、音频、PDF/表格这些模态虽然部分模型声称支持，但我们这次没有覆盖，代码检索之类的垂直领域也没涉及。样本量级别较小，个别模型之间的排名差异可能在统计误差范围内。更多的测试有待后续跟进。

参考资料：

MTEB: https://huggingface.co/spaces/mteb/leaderboard

MMTEB: https://huggingface.co/papers/2502.13595

MMEB: https://huggingface.co/spaces/TIGER-Lab/MMEB-Leaderboard

测试代码: https://github.com/zc277584121/mm-embedding-bench

** 作者介绍  **

![图片](https://mmbiz.qpic.cn/mmbiz_jpg/MqgA8Ylgeh5BIxeeON0DX7SClmD3uYNmiaRyeew8sDAyIX935dIqrUdvu7Lw7nFWBMam9TT5kSKIoibvybaBLjOg/640?wx_fmt=jpeg&wxfrom=5&wx_lazy=1&tp=webp#imgIndex=14)

张晨

Zilliz Algorithm Engineer

    
    
    阅读推荐[黄仁勋GTC演讲上，Milvus为什么能站稳非结构化数据处理C位](https://mp.weixin.qq.com/s?__biz=MzUzMDI5OTA5NQ==&mid=2247512061&idx=1&sn=5dccc84dc607489dabef2fe442f5d1bc&scene=21#wechat_redirect)[80%的 Multi-Agent都是伪需求！如何判断是否需要Multi-Agent，以及如何搭？](https://mp.weixin.qq.com/s?__biz=MzUzMDI5OTA5NQ==&mid=2247511975&idx=1&sn=94e937efe7c95765c1cc8f90c8528dad&scene=21#wechat_redirect)[教程：OpenClaw + Milvus + LLM，如何避免GEO批量生文变AI投毒 | 一线实战](https://mp.weixin.qq.com/s?__biz=MzUzMDI5OTA5NQ==&mid=2247512096&idx=1&sn=8c054c62ea441e66b96b8ab7ba7c4dc8&scene=21#wechat_redirect)[养虾实战教程：我用OpenClaw做了个能盯盘，也能深度复盘的投资agent](https://mp.weixin.qq.com/s?__biz=MzUzMDI5OTA5NQ==&mid=2247512017&idx=1&sn=44ce7beb0e034c75432801e006df8219&scene=21#wechat_redirect)

`

`

![图片](https://mmbiz.qpic.cn/mmbiz_jpg/MqgA8Ylgeh7v2tynJ1lNx27GcRicEo9y8l7SEhLGmWX5cT8UibFDvEvNsOEhMQHTJfPqtkGL7xS6rJKRI3p52vxg/640?wx_fmt=jpeg&from=appmsg&wxfrom=5&wx_lazy=1&tp=webp#imgIndex=6)
![图片](https://mmbiz.qpic.cn/mmbiz_jpg/MqgA8Ylgeh7bEHESUCMeG3ic8utWdusblCUuN8JPhCkCqsoYkz1cQ3BAbZezaHNtWhKlRUjaX25Jd5lbjkSUKOQ/640?wx_fmt=webp&from=appmsg&wxfrom=5&wx_lazy=1&tp=webp#imgIndex=2)  

预览时标签不可点

[ 阅读原文 ](javascript:;)

微信扫一扫  
关注该公众号



微信扫一扫  
使用小程序

****



****



****



×  分析

__

![作者头像](http://mmbiz.qpic.cn/mmbiz_png/MqgA8Ylgeh6icloMEicsabgianxn9qXIbntoEsbyrOlUB3AgRJmcia09Qn5GicdC0oQKmyUHialiccFZxH9pib1V78QRbg/0?wx_fmt=png)

微信扫一扫可打开此内容，  
使用完整服务

：  ，  ，  ，  ，  ，  ，  ，  ，  ，  ，  ，  ，  。  视频  小程序  赞  ，轻点两下取消赞  在看  ，轻点两下取消在看
分享  留言  收藏  听过

