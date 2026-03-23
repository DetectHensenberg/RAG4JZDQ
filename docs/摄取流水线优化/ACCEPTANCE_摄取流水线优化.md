# ACCEPTANCE: 摄取流水线优化

## T1: 增强 LayoutPdfLoader 图片提取算法
- [x] 移除原生粗糙的基于 `page.get_images()` 的小图提取方式
- [x] 引进 `get_pixmap` 整页高质量渲染算法
- [x] 确保图片占位符 `[IMAGE: xxx]` 能随页面正确附着
- [x] 运行测试确认无语法报错

## T2: 配置盘点与清理
- [x] 审查 `config/settings.yaml` (已确认默认启用 layout 且关闭 LLM 提纯)
- [x] 验证流水线可以无缝启动
