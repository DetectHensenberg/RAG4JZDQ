![cover_image](https://mmbiz.qpic.cn/mmbiz_jpg/LZxzhaXSZF06yiagItUzhDYWzwARl1POaZPtOd1UTcM9V3xZTU4sW89o6zTEzCnWFOeic1VaMlNnZq4STSU7ICJIK4RvqlQfcG00b9TBiaGskk/0?wx_fmt=jpeg)

#  突然猛涨7K+ star！阿里开源的前端增强项目火了！

原创  开源君  开源君  [ 开源先锋 ](javascript:void\(0\);)

_2026年03月14日 19:02_ __ _ _ _ _ _ 江西  _

* 戳上方蓝字“  开源先锋  ”关注我 

  

  

大家好，我是开源君！

以前我们搞 Web 自动化要么需要搭建 Python、无头浏览器等复杂环境，要么依赖截图 OCR 和多模态模型，操作很是麻烦，也很难嵌入现有产品做前端增强。

最近在 Github 上意外发现一款来自阿里的非常有意思的开源项目 -  ` PageAgent  ` ，可以让网页直接拥有一个 AI
Agent，通过自然语言就能控制网页界面完成各种操作。

![](https://mmbiz.qpic.cn/sz_mmbiz_jpg/LZxzhaXSZF1DQMr1hu7C2ThZIicd3DE8waiaUx2Dpxa85bOdfTaJic9lxe914z2uWbicbtYYRWeHhf3o1jFp9iaO5lKbU0ALprrzhxVE4CuKKPWc/640?wx_fmt=other&from=appmsg)

##  项目简介

` PageAgent  ` 是一个纯前端的 JavaScript GUI 智能体框架，它的核心理念是  ** “The GUI Agent Living
in Your Webpage”  ** （住在你网页里的 GUI 智能体）。与传统的“外部控制”方案不同，PageAgent
直接在浏览器页面内运行，通过读取和操作 DOM 结构来理解和控制界面，无需截图、无需 OCR、无需多模态大模型。

![](https://mmbiz.qpic.cn/sz_mmbiz_jpg/LZxzhaXSZF17iaOerNhkic5dw13JQsc0JWn16PVibb5ibrel7DUAsLVsn39efpynF72hMSlacdiahY984QhjIqciaHcPuZmfrCTDic71Qegn38ONVY/640?wx_fmt=other&from=appmsg)

项目在 GitHub 上已经获得了  ** 8k+ star  ** 的高度认可，是当前 Web Agent 领域的热门开源项目。

![](https://mmbiz.qpic.cn/mmbiz_png/LZxzhaXSZF3eBicvJXnFsrpn2pg6s9bicUYMT50IPvjwIL7AY5hN1GQpzV5MKcCZQf0H0OYudRZkzRqibufibxAnialjafrBAiaIUPKDK6bRPgN3U/640?wx_fmt=png&from=appmsg)

##  项目体验展示

为了让大家直观地感受 PageAgent 的功能，开源君通过  ** Page-Agent 官方 CDN 一行脚本的方式  **
，接入了一个极简的演示页面。

页面只保留了登录表单和商品列表两个核心区块，结构清晰，便于 AI 理解。演示了以下两个典型场景：

###  场景1：自动填写表单

在交互面板中输入指令：“在登录表单中填写邮箱 demo@test.com，密码 123456，然后点击登录”。

PageAgent 会立刻解析 DOM 结构，精准定位到邮箱和密码的输入框，填入指定信息，并自动点击“登录”按钮。整个过程流畅自然，无需任何手动操作。

###  场景2：提取并分析商品信息

在交互面板中输入指令：“提取页面所有商品名称和价格，并找出页面中最便宜的商品”。

PageAgent 会自动扫描页面，从商品列表中提取出所有商品的名称和对应的价格信息，并进行计算比对，标记出价格最低的商品。

  

##  功能特性

  * 纯前端实现：无需后端部署，直接在浏览器中运行，支持 CDN 和 NPM 两种引入方式 
  * 无需截图：基于 DOM 结构进行文本操作，速度快、成本低、准确性高 
  * 支持多模型：兼容 OpenAI、Claude、DeepSeek、Qwen、Gemini 等多种主流大模型 
  * 人机协同：提供交互式 UI 面板，支持 Human-in-the-loop，用户可实时查看和确认 AI 操作 
  * 隐私安全：采用 BYOK（Bring Your Own Key）架构，数据只在浏览器和用户配置的 LLM 之间流动 
  * 多页面支持：通过可选的 Chrome 扩展，支持跨标签页的复杂任务执行 

![](https://mmbiz.qpic.cn/mmbiz_jpg/LZxzhaXSZF1yAKiapJbTd42YjGC5iajp7zQRMG79RQvQlQVst4KFu0Nqf2pvSoWkN636tcMjQp2Z4PPez5n1ZXAkfNiaxQnWeWyJC4eIwLT6q4/640?wx_fmt=other&from=appmsg)

##  快速安装与使用

PageAgent 的使用也非常简单，官方提供了多种方式：

###  1.最快体验——Demo LLM

该方式通过官方Demo CDN接入，直接使用免费测试LLM API，零配置即可快速体验，适合技术评估，注意该接口有频率和提示词限制。

####  全球节点

    
    
    <script src="https://cdn.jsdelivr.net/npm/page-agent@1.5.2/dist/iife/page-agent.demo.js" crossorigin="true"></script>  
    

####  国内节点

    
    
    <script src="https://registry.npmmirror.com/page-agent/1.5.2/files/dist/iife/page-agent.demo.js" crossorigin="true"></script>  
    

###  2.NPM安装

推荐实际项目开发使用该方式，可灵活配置自定义LLM服务，步骤如下：

  1. 安装依赖包 

    
    
    npm install page-agent  
    

  2. 引入并初始化配置 

    
    
    import { PageAgent } from 'page-agent'  
    // 初始化配置，推荐使用qwen3.5-plus，也可替换为其他兼容OpenAI接口的模型  
    const agent = new PageAgent({  
      model: 'qwen3.5-plus',  
      baseURL: 'https://dashscope.aliyuncs.com/compatible-mode/v1',  
      apiKey: 'YOUR_API_KEY', // 替换为自己的LLM API密钥  
      language: 'zh-CN' // 配置使用语言  
    })  
    

  3. 启动并使用 

    
    
    // 方式1：程序化执行自然语言指令  
    await agent.execute('点击登录按钮，然后将用户名填写为admin');  
    // 方式2：展示交互面板，让用户手动输入指令  
    agent.panel.show()  
    

###  3.Chrome扩展

Chrome扩展为  ** 可选依赖  ** ，不影响核心单页功能使用，安装后可实现跨Tab、多页面自动化操作，还能实现浏览器级的导航与控制

![](https://mmbiz.qpic.cn/mmbiz_jpg/LZxzhaXSZF24l8gZBqkK6ibf2njM3kR8heMcRgMH5TG7jLZO7wT4eO2vf58uZlg0ibTZOWh6SHu09fHx3Ejxwbekz9nKh2B0GxNt4hX3ib5VKA/640?wx_fmt=other&from=appmsg)

##  小结

` Page-Agent  ` 没有走传统 Web 自动化路线，而是直接把 AI Agent
放进网页本身，这样接入成本极低、运行效率更高、自动化稳定性更好，并且非技术用户也能使用。当然，目前项目仍然比较新，一些复杂页面和多步骤任务还有优化空间。但从趋势来看，开源君觉得，“网页内嵌
Agent”很可能会成为未来 Web 应用的重要方向。

更多细节功能，感兴趣的可以到项目地址查看：

    
    
    https://github.com/alibaba/page-agent  
    

推荐阅读：  

[ 比 wget、curl 快 2 倍的高颜值终端项目!
](https://mp.weixin.qq.com/s?__biz=MzkwNzU4NTMyMA==&mid=2247503720&idx=1&sn=3e0602999bba9d03357f9be34d25aec5&scene=21#wechat_redirect)

[ 仅2MB大小，专为 Mac 准备，双向同步支持！
](https://mp.weixin.qq.com/s?__biz=MzkwNzU4NTMyMA==&mid=2247503733&idx=1&sn=b2141344c74c17e17ebb68c0d1861173&scene=21#wechat_redirect)

[ 10.4K star！一款开源聚合利器！
](https://mp.weixin.qq.com/s?__biz=MzkwNzU4NTMyMA==&mid=2247503769&idx=1&sn=c971ebddb987a371fca040bf08325134&scene=21#wechat_redirect)

[ 一键部署，100+安全工具，一句话就能打靶！
](https://mp.weixin.qq.com/s?__biz=MzkwNzU4NTMyMA==&mid=2247503784&idx=1&sn=5f9b2f94c19973d1627e3b2ed56b66e6&scene=21#wechat_redirect)

[ 这个 AI 股票分析项目，居然快 2w star了
](https://mp.weixin.qq.com/s?__biz=MzkwNzU4NTMyMA==&mid=2247503801&idx=1&sn=4e37030e1a1fcbc9b06d940c0bddbaab&scene=21#wechat_redirect)

  

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

![作者头像](http://mmbiz.qpic.cn/mmbiz_png/wrSY9P4VMJEgE3EgUFqS9llQCBZlOZJO7EzicfSz5bg3WkepLerZ5O6I7icfMVFEdZU9ubyC5klmxw8m9dsg0ibzQ/0?wx_fmt=png)

微信扫一扫可打开此内容，  
使用完整服务

：  ，  ，  ，  ，  ，  ，  ，  ，  ，  ，  ，  ，  。  视频  小程序  赞  ，轻点两下取消赞  在看  ，轻点两下取消在看
分享  留言  收藏  听过

