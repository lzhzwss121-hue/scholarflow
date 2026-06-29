# ScholarFlow 分阶段实现计划

更新时间：2026-06-29

原则：ScholarFlow 按阶段推进。每个阶段只完成本阶段定义的目标，完成后先验收，再进入下一阶段。不要一口气实现完整产品。

## 阶段总览

```text
Phase 0: 开源仓库与工程边界
Phase 1: Monorepo 骨架
Phase 2: Web UI 静态工作台
Phase 3: 后端 API 与数据模型
Phase 4: CLI 启动与本地工作区
Phase 5: Agent Core 最小循环
Phase 6: 文献检索 MVP
Phase 7: Deep Paper Card
Phase 8: Gap / Novelty / Experiment Plan
Phase 9: 开源发布打磨
```

## Phase 0: 开源仓库与工程边界

目标：先把项目作为一个可开源产品立起来。

交付物：

- `README.md`
- `LICENSE`
- `ROADMAP.md`
- `CONTRIBUTING.md`
- `.env.example`
- `.gitignore`
- `docs/architecture.md`
- `docs/deep-paper-card.md`

验收标准：

- README 能在 1 分钟内说明 ScholarFlow 是什么。
- `.gitignore` 明确排除 API key、PDF、数据库、日志、用户数据。
- Roadmap 明确 Phase 0-9。
- 不写业务代码，最多写目录占位文件。

不得提前做：

- 不接模型 API。
- 不做论文检索。
- 不写复杂前端。

## Phase 1: Monorepo 骨架

目标：搭好前后端和共享包目录。

推荐结构：

```text
scholarflow/
├── apps/
│   ├── web/
│   └── cli/
├── services/
│   └── api/
├── packages/
│   └── schemas/
├── docs/
└── examples/
```

交付物：

- React + Vite 空项目。
- FastAPI 空服务。
- Node CLI 空入口。
- 共享 schema 包占位。
- 根目录开发脚本。

验收标准：

- `web` 能启动空页面。
- `api` 有 `/health`。
- `cli` 能输出版本号。
- README 的 Quick Start 和实际命令一致。

不得提前做：

- 不设计复杂 UI。
- 不接数据库。
- 不接 LLM。

## Phase 2: Web UI 静态工作台

目标：先做 Claude Code 式科研工作台外壳。

交付物：

- 三栏布局：
  - Project Navigator
  - Agent Workspace
  - Artifact Preview
- 静态页面：
  - Dashboard
  - New Project
  - Paper Table
  - Paper Reader
  - Gap Board
  - Experiment Planner
- 静态 mock 数据。

验收标准：

- 不依赖后端也能展示完整产品形态。
- 用户能看懂 ScholarFlow 的工作流。
- UI 中能看到 plan checklist、tool timeline、artifact preview 三个核心概念。

不得提前做：

- 不接真实 API。
- 不做登录。
- 不做多人协作。

## Phase 3: 后端 API 与数据模型

目标：建立项目、论文、artifact、session 的基础数据结构。

交付物：

- SQLite 数据库。
- 基础表：
  - `projects`
  - `papers`
  - `artifacts`
  - `paper_cards`
  - `sessions`
  - `tool_events`
- FastAPI CRUD：
  - 创建项目
  - 获取项目
  - 保存 artifact
  - 获取 session timeline

验收标准：

- Web UI 能创建 research project。
- artifact 能保存和读取。
- tool timeline 能从后端读取 mock events。

不得提前做：

- 不做真实论文检索。
- 不做 Agent 自动执行。

## Phase 4: CLI 启动与本地工作区

目标：实现 Ddo 风格的本地启动和工作区管理。

当前状态：complete。

交付物：

- `scholarflow init`
- `scholarflow start`
- `scholarflow stop`
- `scholarflow status`
- 默认工作区：

```text
~/.scholarflow/
├── config.yaml
├── projects/
├── artifacts/
├── logs/
└── cache/
```

验收标准：

- CLI 可以初始化本地目录。
- CLI 可以启动 Web + API。
- API key 只从环境变量或本地配置读取，不进入 Git。

不得提前做：

- 不做复杂 REPL。
- 不实现全部 CLI 命令。

## Phase 5: Agent Core 最小循环

目标：实现 Claude Code 式最小 Agent Loop，但先只支持少量科研工具。

当前状态：complete。

交付物：

- `ModelProvider` 抽象。
- `DeepSeekProvider`。
- `ToolRegistry`。
- 最小工具：
  - `create_plan`
  - `search_mock_papers`
  - `save_artifact`
  - `update_timeline`
- Research Plan Mode 初版。

验收标准：

- 用户输入任务后，Agent 先生成 plan。
- 用户确认后，Agent 按步骤执行 mock tools。
- 每个工具调用都写入 timeline。
- 所有输出保存为 artifact，不只留在聊天框。

不得提前做：

- 不接真实论文 API。
- 不生成 deep paper card。
- 不实现多 Agent。

## Phase 6: 文献检索 MVP

目标：从关键词生成真实论文表格。

当前状态：complete。

交付物：

- arXiv 检索。
- OpenAlex 或 Semantic Scholar 检索。
- 论文元数据标准化。
- Paper Table artifact。
- 筛选字段：
  - title
  - year
  - authors
  - abstract
  - venue/source
  - url
  - relevance reason
  - priority

验收标准：

- 用户输入关键词后，系统能返回结构化论文表。
- 每条论文有相关性理由。
- Paper Table 保存为 artifact，并可在 Web UI 查看。

不得提前做：

- 不做复杂 citation graph。
- 不做自动下载 PDF。

## Phase 7: Deep Paper Card

目标：实现你的 12 步论文分析协议。

当前状态：complete。

交付物：

- `deep-paper-reading` skill。
- `PaperCard` schema。
- Paper Reader 页面。
- 支持输入：
  - abstract
  - arXiv metadata
  - 用户粘贴论文内容
- 输出 12 个固定部分：
  - 研究问题与背景
  - prior work 不足
  - 作者思考路径
  - core intuition
  - 方法 pipeline
  - 数学解释
  - 实验逻辑
  - take-aways
  - 最脆弱假设
  - 一周最小复现实验
  - 反例设计
  - 非增量 follow-up idea

验收标准：

- 输出不是摘要，而是结构化 paper card。
- 作者思考路径不能倒用论文贡献。
- follow-up idea 必须说明为什么不是简单增量。

不得提前做：

- 不做批量 20 篇精读。
- 不做自动论文写作。

## Phase 8: Gap / Novelty / Experiment Plan

目标：把论文卡片转成可执行研究计划。

当前状态：complete。

交付物：

- Gap Board。
- Idea Validation Report。
- Experiment Plan。
- Novelty risk：
  - low
  - medium
  - high
- Feasibility：
  - one-week
  - one-month
  - thesis-scale

验收标准：

- 系统能区分真 gap、工程 gap、伪 gap。
- 系统能指出 idea 与已有工作的差异。
- 实验计划包含 baseline、dataset、metric、ablation、资源估计。

不得提前做：

- 不自动跑训练。
- 不自动生成完整论文。

## Phase 9: 开源发布打磨

目标：把 ScholarFlow 做成可以公开展示的开源项目。

当前状态：complete。

交付物：

- 完整 README。
- 截图或 GIF。
- 示例项目。
- GitHub Issues templates。
- GitHub Actions lint/test。
- `v0.1.0` release notes。

验收标准：

- 新用户能按 README 跑起来。
- 仓库没有 secret、PDF、真实用户数据。
- 项目能作为简历和申请材料引用。

不得提前做：

- 不承诺云服务。
- 不做付费系统。
- 不做实验室多人协作。

完成说明：

- README 已同步 v0.1.0 public preview 状态。
- 示例项目使用公开安全的 synthetic artifacts，不包含真实用户数据。
- GitHub Issue/PR 模板、CI、Security Policy 和 release notes 已补齐。
- 截图资产放在 `docs/assets/scholarflow-dashboard.png`。

## 阶段推进规则

每个阶段完成时必须回答：

1. 本阶段交付物是否完成？
2. 是否有测试或手动验证？
3. 是否有安全或隐私风险？
4. 是否有文档同步？
5. 是否进入下一阶段？

如果任一问题答案不清楚，不进入下一阶段。
