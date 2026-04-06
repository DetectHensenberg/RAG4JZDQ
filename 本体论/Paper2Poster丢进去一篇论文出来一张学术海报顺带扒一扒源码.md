![cover_image](https://mmbiz.qpic.cn/mmbiz_jpg/4Zfl6dmm5YeHtkK0aBjFDx1p2hPNXZWE2J8ADqWCj4L2e9OrvTuC3L1fa3iaCjlfstuCg7TKO3ssNCSCYqvTVjd9SaTPIiavFWw0pQCakRQzA/0?wx_fmt=jpeg)

#  Paper2Poster：丢进去一篇论文，出来一张学术海报——顺带扒一扒源码

原创  ChallengeHub  ChallengeHub  [ ChallengeHub ](javascript:void\(0\);)

_2026年03月18日 16:17_ __ _ _ _ _ _ 北京  _

#  Paper2Poster：丢进去一篇论文，出来一张学术海报——顺带扒一扒源码

做过学术海报的人都知道这活儿有多折磨。

开会 deadline 前两天，论文刚投出去，导师说"顺便把海报也做一下"。然后就开始对着 PowerPoint
手动调字体、拖图表、对齐文字框……排了两小时，打印出来发现字小得没法看，图又糊了。这种痛苦，科研圈的人应该都不陌生。

最近看到一个开源项目  ** Paper2Poster  ** ，专门来解决这个问题——丢给它一篇论文
PDF，它自动帮你生成一张学术海报，而且输出的是可编辑的 PPTX，不是死图。

项目地址：https://github.com/Paper2Poster/Paper2Poster

![](https://mmbiz.qpic.cn/mmbiz_png/4Zfl6dmm5YdoM3iapPazuRc75qSOiasvdibwf5AyxYgKGxSaIs89HGj4OxuibSM7oINMNicGYCfq9eibLlZE2VSKicF0HJVf1f2KoykO2Jtcj2ibACU/640?wx_fmt=png&from=appmsg)

##  这个事情为啥难做？

先说说为什么"论文转海报"不是随便套个大模型就能搞定的。

** 第一，上下文超长。  **
一篇正经论文动辄十几页，几千甚至上万词。要从里面提炼核心贡献、主要方法、关键结论，同时保持逻辑连贯，本身就是个硬任务，不是简单摘要能解决的。

** 第二，输入是多模态的。  ** 论文里有文字、有图表、有公式，每张图都和周围文字存在语义关联。海报要把这些东西整合进去，还得放对位置，不能乱。

** 第三，输出有空间约束。  **
海报不是博客，不是想写多少就写多少。它被限制在一张页面内，文字和图像要共存，还要排版好看，不能溢出，不能失衡，不能逻辑错乱。

这三点加在一起，构成了一个典型的"长上下文 × 多模态理解 × 布局感知生成"的复合任务，之前的工具其实都没有很好地解决。

Paper2Poster 的团队在做这个项目时，先把现有方案都测了一遍，结果挺说明问题的：GPT-4o 直接生成图片放大后文字渲染崩了、生成 HTML
的版本像博客多过像海报、PPTAgent
经常出现内容缺失和面板消失……这几个方案的问题都指向同一个核心：没有真正把"布局"和"内容提取"放在统一框架里解决。

![](https://mmbiz.qpic.cn/sz_mmbiz_png/4Zfl6dmm5YcJXvRIMetyibDLehSTH8rDwbsCUx5mOD2vj3iaHn0vs1fMtbxrvvJ7AmcY29196ZRz2SJOhbAzqthTov6asYfw4WgaliaVTQUJrc/640?wx_fmt=png&from=appmsg)

##  PosterAgent：三个智能体分工干活

Paper2Poster 提出的核心系统叫  ** PosterAgent  ** ，是一个自上而下、多智能体协作的流水线，分三个角色。

![PosterAgent
架构图](https://mmbiz.qpic.cn/sz_mmbiz_png/4Zfl6dmm5YfWMTwR4X1ZejeEfHnIUibjQickwKQ9e2Tbf1JLNJHTJXb1wV6WDiczfIxUDMjy69P9JqmxNr5ibVe3Lr4pYOibYPmE9n2uqQynjLgA/640?wx_fmt=png&from=appmsg)
PosterAgent 架构图

** Parser（解析器）  ** 负责读论文，把整篇 PDF
拆解成结构化的素材库，文字归文字、图表归图表，每个元素都标注好语义角色，把"长文档理解"这个问题单独先解决掉。

** Planner（规划器）  ** 负责排版，把 Parser 提取出来的文字-
图像对，按照"二叉树布局"的方式组织起来。这个结构天然保证了阅读顺序和空间平衡，不会出现某个角落堆满内容、另一个角落空着的情况。

** Painter-Commentor（画图+审阅循环）  ** 负责渲染和修正。Painter 根据布局方案执行渲染代码，Commentor
是一个视觉语言模型，充当"审稿人"角色，检查有没有溢出、有没有对齐问题，然后把反馈喂回给 Painter
继续改。整个过程"视觉在回路中"，不是一次性生成就完事。

评估方面，团队还设计了一套叫  ** PaperQuiz  ** 的方案：用 LLM
根据原论文自动出选择题，让视觉语言模型只看海报来答题，答题得分越高说明海报传达信息的效率越好。比单纯看"好不好看"实用得多。
![](https://mmbiz.qpic.cn/mmbiz_png/4Zfl6dmm5YfPicJ69np1BS0uD0dlLs6gcbMKMpOiaBWhn47Yl7C9lbsNXlclibchVZFzGJ8gZKVIYZ01EvxZeqx3rgZnwBOMKZeWa7ia5gImsbc/640?wx_fmt=png&from=appmsg)

从公布的结果来看，PosterAgent 在几乎所有评估指标上都优于基于 GPT-4o 的方案，**但 token 消耗只有后者的
13%**，效率差距相当大。

![](https://mmbiz.qpic.cn/sz_mmbiz_png/4Zfl6dmm5YeeGoX9Cseq6u9T7l1UwDnhAE6iauGpuXjDqmiah8Fe4BIM0P7lWvb8BoA0FjnMgfgBFfI4uTLaNEQDoSr0EEWyQDshnBn3icWWTA/640?wx_fmt=png&from=appmsg)
![](https://mmbiz.qpic.cn/mmbiz_png/4Zfl6dmm5YeasBVV4aSEA9mDebZaUmPviaDo9CIiaWMUBah62RZLVBaejvtZWc89icBjI7XdH9DxuSMrOsSRSe2ia7trJzbpjDL9eLjzrdEFgAc/640?wx_fmt=png&from=appmsg)

##  扒一扒源码：系统内部到底怎么跑的

功能介绍完了，今天重点看看这套系统内部的实现逻辑。

###  整体流水线：八步走

核心入口在  ` poster_gen_pipeline.py  ` ，整个流程分成八个阶段：

    
    
    parse_raw(args, actor_config)           # 1. 解析论文  
    gen_image_and_table(args)               # 2. 提取图表  
    filter_image_table(args, actor_config)  # 3. 筛选图表  
    gen_outline_layout(args, ...)           # 4. 生成布局大纲  
    gen_poster_content(args, actor_config)  # 5. 生成海报内容  
    fill_poster_content(args, actor_config) # 6. 填充内容  
    stylize_poster(args, actor_config)      # 7. 样式美化  
    deoverflow(args, actor_config, ...)     # 8. 消除溢出  
    

每个阶段的输出都存成中间文件，方便调试，也支持断点续跑。海报生成这种多步骤任务，中途某个环节挂掉可以单独重跑，设计上挺务实的。

###  Parser：两个解析器备选，谁靠谱用谁

Parser 模块把 PDF 论文转成嵌套 JSON，代码里用了两个工具作为备选：

    
    
    # 首选 docling  
    raw_result = doc_converter.convert(raw_source)  
    raw_markdown = raw_result.document.export_to_markdown()  
      
    # 提取内容太短，自动切换到 marker 兜底  
    if len(text_content) < 500:  
        print('\nParsing with docling failed, using marker instead\n')  
        parser_model = create_model_dict(device='cuda', dtype=torch.float16)  
        text_content, rendered = parse_pdf(raw_source, model_lst=parser_model)  
    

先用 docling（IBM 开源的文档解析工具），如果提取内容不足 500 字符，自动切到 marker 兜底。docling
处理复杂排版更稳，marker 对某些特殊格式论文更鲁棒，两个互补。

提取出 Markdown 后，系统调用 LLM 做结构化处理：识别章节结构、每节控制在 500 字左右、去掉页眉页脚和冗余引用，最终输出嵌套
JSON。图表的提取是独立进行的，系统遍历文档里所有图片和表格，存成独立文件，同时记录尺寸、宽高比、标题等元数据，这些信息后续决定图表在海报里的大小和位置。

###  Planner：二叉树递归切割空间

布局规划是整个系统里最核心的部分，分两层：先定整体框架，再细化每个区块内部。

** 图表分配  ** 先解决"哪张图放哪个章节"的问题。  ` poster_planner_new_v2.yaml  `
定义了决策逻辑——分析每个章节的主题描述，与图表标题做语义匹配。"实验结果"章节优先分配结果对比图，而不是随机堆砌，分配方案还会记录每张图被分配到哪个章节以及分配理由。

** 面积预测  ** 是布局的关键前置步骤。系统用一个从真实海报数据里训练出来的线性回归模型，根据章节内容特征预测每个区块应该占多大面积：

    
    
    def infer_panel_attrs(panel_model, tp, gp):  
        # tp = 文本长度占全文的比例  
        # gp = 分配图表面积占总图表面积的比例  
        vec = np.array([tp, gp, 1.0])  
        sp = np.dot(panel_model["w_s"], vec)  # 预测面积比例  
        rp = np.dot(panel_model["w_r"], vec)  # 预测宽高比  
        return sp, rp  
    

模型从大量真实海报数据里学会了"文字多的章节需要更大空间"这样的隐式规则，不是人工硬编码的模板——这一点很关键，后面细说。

有了预期面积，递归分割正式开始：

    
    
    def panel_layout_generation(panels, x, y, w, h):  
        if len(panels) == 1:  
            return loss, arrangement  
          
        for i in range(1, n):  
            subset1, subset2 = panels[:i], panels[i:]  
            ratio = sum(p["sp"] for p in subset1) / total_sp  
              
            # 尝试水平分割  
            h_top = ratio * h  
            l1, a1 = panel_layout_generation(subset1, x, y, w, h_top)  
            l2, a2 = panel_layout_generation(subset2, x, y+h_top, w, h-h_top)  
              
            # 尝试垂直分割  
            w_left = ratio * w  
            l1, a1 = panel_layout_generation(subset1, x, y, w_left, h)  
            l2, a2 = panel_layout_generation(subset2, x+w_left, y, w-w_left, h)  
              
            best_loss = min(horizontal_loss, vertical_loss)  
          
        return best_loss, best_arrangement  
    

算法枚举所有分割方式，选损失最小的。举个具体例子：三个章节，预期面积比例是 0.3、0.4、0.3，算法会尝试先切成 0.3 和 0.7 两部分，再把
0.7 切成 0.4 和 0.3，每一步都同时考虑横切和竖切，最终选整体误差最小的组合。

另一个细节：系统强制给标题区留出海报顶部约 10% 的空间，保证学术海报的基本规范——标题永远在最上面。

###  Painter-Commenter：让 VLM "看"海报做修正

内容填充进去之后，文字可能撑出文本框造成溢出。  ` deoverflow.py  ` 实现了迭代修正机制——系统渲染出某个区块，截图丢给 VLM 判断：

    
    
    critic_msg = BaseMessage.make_user_message(  
        role_name="User",  
        content=critic_prompt,  
        image_list=[neg_example, pos_example, zoomed_img],  # 负例、正例、目标图  
    )  
    # VLM 返回：1=溢出 / 2=空白太多 / 3=刚好  
    response = critic_agent.step(critic_msg)  
    

提示词设计得挺聪明：先给 VLM 看一张溢出的反例和一张正常的正例，让它建立判断标准，再分析目标图片。这种少样本学习的方式比直接描述规则可靠得多。

检测到问题之后，Actor 智能体会生成修正代码来解决。这里有个有意思的设计——整张海报本质上是一段 Python 程序，用  ` python-pptx
` 库来操控 PowerPoint 文件。修正的方式就是修改这段代码（调整字体大小、改文本框位置、删减内容），然后重新执行生成新的
PPT。"代码即内容"，改起来非常灵活。

修正循环会一直跑，直到 VLM 判断"刚好合适"，或者撞到最大迭代次数（默认 5 次）。

###  布局规则是从真实海报里总结来的

这个系统有一个容易被忽视但很关键的设计：布局规则不是人工定义的，而是从真实学术海报数据里学来的。

研究团队收集了大量论文和对应的海报，解析出每个面板的属性——面积比例、宽高比、文字长度比例、图表面积比例，然后用线性回归学这些属性之间的关系：

    
    
    def train_panel_attribute_inference(panel_records):  
        linreg_sp = LinearRegression(fit_intercept=False)  
        linreg_sp.fit(X_array, y_sp)   # 学面积分配  
          
        linreg_rp = LinearRegression(fit_intercept=False)  
        linreg_rp.fit(X_array, y_rp)   # 学宽高比  
          
        return {"w_s": w_sp, "w_r": w_rp, ...}  
    

所以系统里那些"文字多的章节自然更大"、"带图表的章节有特定宽高比"之类的规律，都是从专业设计的海报里学来的，不是拍脑袋写死的。这意味着系统不是在套模板，而是真正"学会"了如何根据内容特点来分配空间。

###  为什么能输出可编辑的 PPTX

很多人问这个，解释起来也很简单：整个流程都是在构建一段 Python 程序，每个阶段往里面添加操作：

    
    
    code = initialize_poster_code(width, height, slide_name, poster_name, utils)  
      
    for p in panel_arrangement_list:  
        code += generate_panel_code(p, ...)  
    for t in text_arrangement_list:  
        code += generate_textbox_code(t, ...)  
    for f in figure_arrangement_list:  
        code += generate_figure_code(f, ...)  
      
    code += save_poster_code(output_file, ...)  
    

最后执行这段代码，输出完整的 PPTX 文件。文件里每个元素——文本框、图片、形状——都是独立的可编辑对象，不是一张死图，生成完还可以继续手动调整。

##  小结

Paper2Poster 这个项目不是那种"大力出奇迹"的方案，而是把问题拆解得比较清楚，然后各个击破。Parser 解决内容提取，Planner
解决布局规划，Painter-Commenter 解决渲染质量，每个环节都有针对性的设计。

几个核心思路值得借鉴：分层流水线让职责清晰，从真实数据里学布局让结果更自然，视觉反馈循环是保证质量的关键，代码即内容让输出天然可编辑，多解析器备选加上中间结果持久化让整体更健壮。

这是 NeurIPS 2025 D&B track 的工作，代码、数据集都已开源，Hugging Face 上也有 Demo 可以直接试。

  * 论文：https://arxiv.org/abs/2505.21497 
  * 代码：https://github.com/Paper2Poster/Paper2Poster 
  * 数据集：https://huggingface.co/datasets/Paper2Poster/Paper2Poster 
  * 在线 Demo：https://huggingface.co/spaces/camel-ai/Paper2Poster 

* * *

都看到这里了，点个在看、关注一下呗，这类工具后面还会持续更新。

  

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

![作者头像](http://mmbiz.qpic.cn/mmbiz_png/1FD1x61uYVf9D3QcAhQDRtcia3Z56uk8JzHrb6lojGEQ4ddbzCa0XyMB2TpjRFI2zABZ3xOg2ITsdpbpum5BVdw/0?wx_fmt=png)

微信扫一扫可打开此内容，  
使用完整服务

：  ，  ，  ，  ，  ，  ，  ，  ，  ，  ，  ，  ，  。  视频  小程序  赞  ，轻点两下取消赞  在看  ，轻点两下取消在看
分享  留言  收藏  听过

