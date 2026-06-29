# ScholarFlow

[English](./README.md) | [简体中文](./README.zh-CN.md)

ScholarFlow 是一个中文优先的 AI 科研任务流程 Agent，面向需要把模糊研究方向转化为可追踪科研资产的学生和研究者。它不是一个简单的论文搜索 demo，而是一个 local-first 的科研工作台，用来沉淀 paper table、Deep Paper Card、gap analysis、novelty check、复现实验计划、实验设计和写作前证据。

ScholarFlow 试图回答的问题是：

> 给定一个关键词或粗略 idea，在 AI 科研中我应该读什么、真正的 gap 是什么、一周内能验证什么、下一步研究方向是否值得做？

## 当前状态

当前仓库处于 Phase 9: Open-Source Release Polish，已经可以作为 v0.1.0 public preview 和简历项目展示。

当前代码库包含：

- React 科研工作台。
- FastAPI + SQLite 本地后端。
- Node CLI，用于初始化本地工作区并启动 Web/API。
- 最小 Agent Loop，包括 Research Plan、Tool Registry、Timeline 和 Artifact 持久化。
- arXiv / OpenAlex 真实文献检索。
- 单篇论文 Deep Paper Card 生成。
- Gap / Novelty / Experiment Plan 研究决策生成。
- GitHub Actions CI、Issue 模板、PR 模板、Security Policy、release notes 和公开安全示例。

当前尚未包含：

- 真实 DeepSeek API 调用。
- PDF 自动下载。
- 批量论文精读。
- 自动训练或 benchmark 执行。
- 自动写完整论文。
- 云服务、付费系统或实验室多人协作。

阶段计划见 [IMPLEMENTATION_PHASES.md](./IMPLEMENTATION_PHASES.md)。

## 快速开始

环境要求：

- Node.js 20+
- npm 10+
- Python 3.11+

安装 JavaScript 依赖：

```bash
npm install
```

安装 Python API 依赖：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r services/api/requirements.txt
```

初始化本地 ScholarFlow 工作区：

```bash
npm --workspace @scholarflow/cli run start -- init
```

同时启动 Web UI 和 API：

```bash
npm --workspace @scholarflow/cli run start -- start
```

查看或停止本地服务：

```bash
npm --workspace @scholarflow/cli run start -- status
npm --workspace @scholarflow/cli run start -- stop
```

默认本地工作区是 `~/.scholarflow`。如果想使用自定义路径：

```bash
SCHOLARFLOW_WORKSPACE=/path/to/workspace npm --workspace @scholarflow/cli run start -- init
```

后端单独开发时，可以直接初始化 SQLite 数据库：

```bash
npm run db:init
```

手动启动前端：

```bash
npm run dev:web
```

手动启动 API：

```bash
npm run dev:api
```

运行本地校验：

```bash
npm run check
npm run build
python3 -m compileall services/api/src/scholarflow_api
```

如果要检查 API health，请先确保 Python 依赖已经安装并激活虚拟环境：

```bash
npm run health:api
```

## 目标用户

ScholarFlow 初期面向：

- AI 方向硕士研究生。
- 正在进入科研训练的高年级本科生。
- 需要结构化完成文献调研、idea 验证和实验计划的研究者。

产品语言以中文为主，必要技术术语保留英文，例如 Agent Loop、Artifact、Timeline、Gap、Claim、Baseline 和 Ablation。

## 核心工作流

```text
关键词 / 模糊 idea
  -> 方向理解
  -> 文献检索与筛选
  -> 结构化 Paper Table
  -> Deep Paper Card
  -> Gap Analysis
  -> Novelty Check
  -> 一周最小复现实验
  -> Experiment Plan
  -> 可复用科研 Artifact
```

## 当前 Web 工作台

Web UI 采用类似 coding agent 的科研工作台结构：

- Project Navigator
- Agent Workspace
- Artifact Preview
- Dashboard
- New Project
- Paper Table
- Paper Reader
- Gap Board
- Experiment Planner
- Plan Checklist
- Tool Timeline

当 API 运行时，Web 会从 SQLite 读取项目、论文、artifact 和 session timeline。API 未运行时，Web 会回退到静态 mock 工作台，便于展示和本地 UI 开发。

## 当前能力

### Research Plan Mode

- 输入科研任务。
- 生成可持久化的 Research Plan artifact。
- 等待用户确认后执行最小工具链。
- 将工具调用写入 timeline。
- 将输出保存为 artifact，而不是只留在聊天框。

### Paper Table

- 从关键词扩展检索 query。
- 从 arXiv 和 OpenAlex 获取候选论文。
- 对论文进行去重和轻量相关性排序。
- 保存 `paper_table.md` artifact。
- 将论文元数据写入 SQLite。

### Deep Paper Card

Paper Reader 支持基于检索论文、abstract 和用户粘贴的论文片段生成 12 部分论文分析：

1. 研究问题与背景。
2. prior work 不足。
3. 重建作者可能的思考路径。
4. core intuition。
5. 方法 pipeline。
6. 数学和理论解释。
7. 实验逻辑。
8. take-aways。
9. 最脆弱假设。
10. 一周最小复现实验。
11. 反例设计。
12. 非增量 follow-up idea。

完整协议见 [docs/deep-paper-card.md](./docs/deep-paper-card.md)。

### Gap / Novelty / Experiment Plan

Gap Board 和 Experiment Planner 可以生成第一版研究决策 bundle：

- 区分 true gap、engineering gap 和 pseudo gap。
- 输出 novelty risk 和 feasibility。
- 生成包含 baseline、dataset、metrics、ablations、资源估计、成功标准和失败标准的实验计划。
- 保存 `gap_board.md`、`idea_validation_report.md` 和 `experiment_plan.md`。

## 截图

![ScholarFlow Dashboard](./docs/assets/scholarflow-dashboard.png)

## 示例项目

公开安全示例位于 [examples/workflows/phase8-vlm-hallucination](./examples/workflows/phase8-vlm-hallucination)，包含：

- Project brief。
- Paper Table。
- Deep Paper Card。
- Gap Board。
- Idea Validation Report。
- Experiment Plan。

这些示例文件是 synthetic artifact，仅用于展示 ScholarFlow 输出结构，不是真实论文推荐，也不应作为真实 citation 使用。

## CLI

当前 CLI 提供：

```text
scholarflow init
scholarflow start
scholarflow status
scholarflow stop
```

CLI 会创建如下本地工作区：

```text
~/.scholarflow/
  config.yaml
  projects/
  artifacts/
  logs/
  cache/
    scholarflow.sqlite3
    services.json
```

`start` 会启动 FastAPI 和 Vite Web，日志写入 `logs/`，服务状态写入 `cache/services.json`。API 数据库路径通过 `SCHOLARFLOW_DB_PATH` 注入，因此本地研究数据默认不会进入 Git。

## API

当前本地 API 包含：

```text
GET  /health
GET  /projects
POST /projects
GET  /projects/{project_id}
GET  /projects/{project_id}/papers
GET  /projects/{project_id}/artifacts
POST /artifacts
GET  /artifacts/{artifact_id}
GET  /projects/{project_id}/sessions
GET  /sessions/{session_id}/timeline
GET  /projects/{project_id}/timeline
POST /agent/plan
POST /agent/runs/{run_id}/execute
POST /projects/{project_id}/literature/search
POST /projects/{project_id}/paper-cards
POST /projects/{project_id}/research-decisions
```

默认开发数据库路径为 `services/api/.data/scholarflow.sqlite3`，该路径已被 Git 忽略。通过 CLI 启动时，数据库路径为 `<workspace>/cache/scholarflow.sqlite3`。

## 模型策略

ScholarFlow 的模型层采用 provider abstraction。目标默认模型为 DeepSeek：

- `deepseek-v4-pro`：用于 planning、论文分析、novelty check 和长推理。
- `deepseek-v4-flash`：用于 query expansion、分类、抽取和轻量摘要。

v0.1.0 只实现了 `DeepSeekProvider` 边界和 deterministic local-first 流程，尚未实际调用 DeepSeek API。后续接入真实模型时，应保持 provider 可替换，不把工作流绑定到单一模型。

## 设计原则

- 科研 workflow 优先，chat 其次。
- 重要输出必须保存为 artifact，而不是只显示在对话里。
- 论文 claim、agent 推断和用户输入要区分清楚。
- 工具调用、检索 query、筛选逻辑和中间产物要可追踪。
- 不编造 citation、dataset、metric、实验结果或数学推导。
- 用户的本地论文、笔记、API key、数据库和实验日志默认是敏感数据。

## 安全与隐私

ScholarFlow 可能处理 API key、本地论文、未发表 idea、实验结果和私人笔记。因此仓库默认不会提交：

- `.env` 和 API key。
- PDF、Word、PPT、Excel、CSV、TSV。
- SQLite 数据库。
- logs。
- vector store。
- 用户 artifact。
- 本地 workspace。

更多说明见 [SECURITY.md](./SECURITY.md)。

## 开源发布

v0.1.0 release polish 包含：

- GitHub Actions CI。
- GitHub Issue templates。
- Pull request template。
- Security Policy。
- Public-safe example workflow。
- [v0.1.0 release notes](./docs/release-notes/v0.1.0.md)。

## 贡献

贡献前请阅读 [CONTRIBUTING.md](./CONTRIBUTING.md)。好的贡献应该改善科研流程本身，例如文献检索、论文精读质量、evidence tracking、novelty check、复现实验计划、本地工作区可靠性或中文优先用户体验。

请不要提交私有论文、未发表研究材料、个人申请材料、API key、本地数据库或日志。

## License

ScholarFlow 使用 MIT License，见 [LICENSE](./LICENSE)。
