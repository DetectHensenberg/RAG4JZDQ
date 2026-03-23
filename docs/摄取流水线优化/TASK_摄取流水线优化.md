# TASK: 摄取流水线性能平衡改造

## 任务拆解与依赖图
依赖关系：T1 -> T2

### T1: 增强 `LayoutPdfLoader` 图片提取算法 [原子化]
- **工作节点**: 合并代码算法
- **输入契约**: 现有的 `LayoutPdfLoader` 源码逻辑与 `PdfLoader` 优秀的渲染逻辑。
- **实现约束**: 
  - 移除 `LayoutPdfLoader` 中原生粗糙的基于 `page.get_images()` 的图片切片提取方式。
  - 将 `PdfLoader._extract_and_process_images` 及其相关的 `MIN_IMAGES_FOR_RENDER` (当页面有实质内容时) 及 `RENDER_DPI` (高清缩放控制) 等常量的渲染算法平移引入。
  - 使得版面解析不仅产出优雅的分栏 Markdown，更能在插图所在物理位置无缝挂载拼装好的高清全页大图 `[IMAGE: xxx]`。
- **输出契约**: 更新后的 `src/libs/loader/layout_pdf_loader.py` 文件。
- **验收标准**: 解析速度不受大的影响，但能在遇到图文混排页面时存储有效的大视野全图而非碎片图标。

### T2: 查漏补缺与配置闭环 [原子化]
- **工作节点**: 配置文件巡检
- **输入契约**: 核心配置文件 `config/settings.yaml`
- **实现约束**: 审查并确保项目中 `ingestion.pdf_parser` 设定在极速的 `layout` 上，且富化流水线 `use_llm` 被默认关闭以符合前述 PC 性能极致对齐方案。
- **输出契约**: 确认最终配置生效。
