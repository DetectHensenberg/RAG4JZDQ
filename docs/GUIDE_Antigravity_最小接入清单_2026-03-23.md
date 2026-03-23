# GUIDE - Antigravity IDE 最小接入清单（2026-03-23）

> 目标：在 Antigravity 中稳定使用本仓库与 ECC 能力，先可用、再增强

---

## 1. 先判断能不能直接用

## 代码层

1. `git clone` 后直接在 Antigravity 打开项目目录即可编辑代码。
2. Python/Node 项目结构不会受影响，和普通 IDE 使用方式一致。

## Agent 能力层

1. 如果 IDE 原生支持 `AGENTS.md` / skills / hooks 约定，则可自动识别。
2. 如果 IDE 不原生支持，也可以通过命令方式“半自动接入”。

---

## 2. 最小可用接入（推荐当天完成）

## Step 1: 环境准备

1. 安装 Git、Node.js 18+、Python 3.11+（或项目要求版本）。
2. 在项目根目录执行依赖安装（按本项目实际脚本）。
3. 确认 IDE 终端可在项目根目录执行命令。

## Step 2: 仓库能力目录确认

本仓库已包含可复用资产，优先使用现成目录：

1. `.agents/skills/`（项目级技能）
2. `AGENTS.md`（行为与协作约束）
3. `docs/`（方案、任务、验收与上下文）

## Step 3: 在 IDE 中建立三个固定入口

1. `Run QA`：执行项目最小回归测试。
2. `Sync Docs`：更新 `docs/context.md` 与相关方案文档。
3. `Release Check`：执行 lint/test/import-smoke。

说明：即便 IDE 不支持原生 skills，这三个入口也能把流程稳定下来。

---

## 3. 第二阶段接入（1-3 天）

## A. 全局层（跨项目）

1. 保留通用能力：`search-first`、`verification-loop`、`security-review`。
2. 这些能力放在用户级配置目录，供所有项目复用。

## B. 项目层（本仓库）

1. 保留项目专用能力：RAG、检索、QA、文档更新。
2. 将自动写入类 hooks 默认关闭，只保留提示类 hooks。

## C. 团队层（多人协作时再开）

1. 统一任务模板（需求/设计/TASK/验收/FINAL）。
2. PR 前固定执行 `Run QA` + `Sync Docs`。

---

## 4. 风险与规避

1. 风险：一次引入过多 skills，IDE 体验变慢。  
   规避：先白名单 5-10 个高频技能。

2. 风险：自动 hooks 改动超出预期。  
   规避：先关闭自动写入，只保留提醒。

3. 风险：不同项目规则冲突。  
   规避：全局放通用规则，项目放特定规则。

---

## 5. 推荐白名单（起步版）

1. `search-first`
2. `verification-loop`
3. `security-review`
4. `python-patterns`
5. `python-testing`
6. `api-design`
7. `backend-patterns`

---

## 6. 自检清单（接入完成判定）

1. IDE 能打开并编辑项目，终端命令正常执行。
2. 能运行最小回归测试并看到结果。
3. 能按约定更新 `docs/context.md`。
4. 新任务可按“方案 -> 实施 -> 验证 -> 文档”闭环推进。

---

## 7. 下一步（可选）

若你确认这套最小接入可行，下一步建议输出两份文件：

1. `SOLUTION_Antigravity_项目级配置草案.md`（本仓库）
2. `SOLUTION_Antigravity_全局能力白名单.md`（跨项目）
