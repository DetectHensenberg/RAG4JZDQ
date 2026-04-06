![cover_image](https://mmbiz.qpic.cn/mmbiz_jpg/sMcM9PH6JD2spRSIWa4NBLbY6xibrtARpg4R9kx7M6XPWBGriavHXgA3jZibSO9iarDb4WHsnskAD9jZiaiaMHPypxicrdF55ZwgXv26VibYxK25ibnc/0?wx_fmt=jpeg)

#  AI Infra 学习路径（潦潦草草版）

LatteInfra  LatteInfra  [ AiBioMed日记 ](javascript:void\(0\);)

_2026年02月21日 08:30_ __ _ _ _ _ _ 山东  _

我找了几家在招聘的infra岗位的公司，目前可能相关的技术栈整理出来；那么之后的内容可能也是围绕着这套路径进行。

也欢迎大家在评论区或私信补充遗漏的内容。

##  基础能力

  1. 编程和基础框架 

** Python、PyTorch Internal  ** ：Autograd, dispatcher, 张量生命周期，CUDA
stream，编译/执行路径，计算图

** C++/CUDA Kernel  ** ：算子实现、内存访问、并行划分、Kernel lanuch开销

** Tranformer / Attention 算法  ** ：

MHA / GQA / MQA

Softmax 数值稳定性

RoPE/ALiBi/xPos 位置编码和长上下文外推

  2. 算法题 

链表 / 树遍历 / LRU / LFU / 动态管理

并行处理：线程 / 进程/ 锁 / 无锁队列

Beam Search / Top-K Sampling

##  训练方向 Training Infra

** 1\. 分布式训练并行策略  **

  * 数据并行 Data Parallel：DDP、ZeroRedundancyOptimizer（ZeRO） 
  * 参数/状态分片： FSDP、DeepSpeed ZeRO-1/2/3、Offload（CPU/NVMe） 
  * 模型并行Model Parallel：TP、PP、3D Parallelism（DP+TP+PP）、Megatron（Megatron-Core + Megatron-LM） 
  * MoE专项并行：EP、ETP、EDP、MoE路由/负载均衡/All-to-All通信优化 

** 2\. 训练数值和内存优化  **

  * AMP / BF16 
  * Gradient Checkpoint 
  * Offload 
  * FlashAttention 
  * 长序列优化：Ring Attention、Sequence Parallel、LASP 

** 3\. 优化器 Optimizer  **

  * Muon、MuonClip （+ QK-Clip稳定性）：较为前沿 

##  推理方向Inference / Serving

** 1\. 解码和缓存  **

  * KV Cache 
  * PagedAttention 
  * Ring Attention 
  * 连续批处理 Continuous Batching： 
  * Radix Tree / KV Cache管理 
  * Speculative Decoding 投机解码 / 投机采样 

** 2\. 量化和部署优化  **

  * INT8 / FP8 / AWQ / GPTQ 

** 3\. Serving引擎和Runtime  **

  * vLLM & SGLang：LLM serving 引擎（连续批处理、PagedAttention、量化、spec decode） 
  * Triton Inference Server：通用推理服务框架（动态批处理、多模型并发、调度） 
  * TensorRT-LLM：偏 NVIDIA 栈的高性能 LLM 推理优化（KV cache 系统、kernel/graph 优化） 

** 4\. 高性能推理Kernel  **

  * 分块 Tiling 
  * 内外层计算拆分 
  * HBM带宽 vs Tensor Core利用 
  * MFU指标 

主要围绕上述提到的Lighting/Lighting Attention

##  系统底层

** 1\. 高性能网络和通信  **

  * RDMA 
  * InfiniBand 
  * NCCL调优 
  * MoE All-to-All通信优化  ** 2\. GPUi集群调度  **
  * GPU集群调度：调度需要考虑网络拓扑 + NUMA + 存储亲和性 
  * 多用户资源隔离：Docker + K8s 
  * 队列调度 / 抢占 / 优先级 
  * SLA / 高可用 / 故障诊断 

** 3\. 存储和存储点  **

  * Checkpoint存储： 异步、增量 
  * 高性能存储（IO存储瓶颈）：对象存储 / 并行文件系统 
  * 数据Pipeline：恢复策略 

** 4\. 多模态和Agent  ** \- Agent Runtime / 多模态 Infra - Agent 高并发 - 多模态Token处理 -
Agentic优化

##  系统性能分析

** 1\. 工具栈  **

  * Nsight System：系统层面分析，CPU+GPU+线程 +通信+  ** NVTX Nvidia Tools Extension（提供 标记或区间的作用）  **
  * Nsight Compute：更为精细在算子层面，我们可以返回某些感兴趣的算子来进行分析 
  * PyTorch Profiler：Pytorch profiler是一个用于分析训练的一体化工具 

当然具体的分析工具并不单单只有这些，GPU
Profile作为一个更加复杂的工程领域，我们这里只罗列出几个比较常用的工具，当然像是eGPU，CUPTI，Neutrino这些比较前沿的工作都是有更佳完善的分析流程，后面我们可以单独摘出来讲一讲（
~~ 挖坑  ~~ ）。

![](https://mmbiz.qpic.cn/mmbiz_png/sMcM9PH6JD3Rtmo8mfibQicnDJmwBFfoxFicw0kYAR5vuZK9TOucAd4Kic207TPicZo9W1yr3XD7b4Wq7ZXJDh2gb83TYjeqic8PbUcqjZKXsiaibVA/640?wx_fmt=png&from=appmsg)

** 2\. Workflow  **

那么这里提一个比较入门泛泛的分析流程：

系统分析 → Kernel分析 → 框架分析

Nsight System → Nsight Compute → PyTorch Profiler

分析从系统层逐渐深入到算子和框架，那么这些不过多展开在这里（  ~~ 继续挖坑  ~~ ）。

  

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

![作者头像](http://mmbiz.qpic.cn/mmbiz_png/nfiaCRkMicicCgpp0B0KsbpvwS38XicriaKY0dY4ObxV0DN1bWvy5S8Epv7C5oUFDretj9qzpW2adosBicnSI5zgnDYw/0?wx_fmt=png)

微信扫一扫可打开此内容，  
使用完整服务

：  ，  ，  ，  ，  ，  ，  ，  ，  ，  ，  ，  ，  。  视频  小程序  赞  ，轻点两下取消赞  在看  ，轻点两下取消在看
分享  留言  收藏  听过

