# ScholarFlow

[English](./README.md) | [简体中文](./README.zh-CN.md)

ScholarFlow 是一个中文优先的 AI 科研任务流程 Agent，面向人工智能方向的学生和研究者。它的目标不是只做论文搜索，而是把关键词、论文主题或粗略 idea 转化为可复用、可追踪的科研资产。

这个项目适合用于：

- 根据 AI 研究关键词查找和整理相关论文。
- 生成结构化 Paper Table 和深度论文阅读笔记。
- 从论文和任务中识别真正的 research gap。
- 规划一周内可以完成的最小复现实验。
- 设计 baseline、dataset、metric、ablation 和成功标准。
- 将科研过程中的关键输出保存成本地 artifact。

## ScholarFlow 的用途

用户给出关键词或模糊方向后，ScholarFlow 关注完整科研流程：

```text
关键词 / 模糊 idea
  -> 理解研究方向
  -> 检索并排序论文
  -> 生成结构化 Paper Table
  -> 生成 Deep Paper Card
  -> 分析 gap 和 novelty risk
  -> 规划最小复现实验
  -> 设计实验计划
  -> 保存可复用科研 artifact
```

产品语言以中文为主，必要技术术语保留英文，例如 VLM、LLM、Agent、Artifact、Gap、Baseline、Metric 和 Ablation。

## 快速上手

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

配置 OpenRouter 作为主要模型 provider：

```bash
export SCHOLARFLOW_MODEL_PROVIDER=openrouter
export OPENROUTER_API_KEY=your_openrouter_api_key
export OPENROUTER_MODEL=minimax/minimax-m2.5
```

可选配置未来检索工作流使用的 embedding 模型：

```bash
export OPENROUTER_RAG_MODEL=qwen/qwen3-embedding-8b
```

初始化本地 ScholarFlow 工作区：

```bash
npm --workspace @scholarflow/cli run start -- init
```

启动 Web UI 和 API：

```bash
npm --workspace @scholarflow/cli run start -- start
```

默认启动地址：

- Web UI: `http://127.0.0.1:5173`
- API: `http://127.0.0.1:8000`
- 本地工作区: `~/.scholarflow`

查看或停止本地服务：

```bash
npm --workspace @scholarflow/cli run start -- status
npm --workspace @scholarflow/cli run start -- stop
```

使用自定义工作区路径：

```bash
SCHOLARFLOW_WORKSPACE=/path/to/workspace npm --workspace @scholarflow/cli run start -- init
SCHOLARFLOW_WORKSPACE=/path/to/workspace npm --workspace @scholarflow/cli run start -- start
```

## 开发命令

只启动前端：

```bash
npm run dev:web
```

只启动 API：

```bash
npm run dev:api
```

初始化开发数据库：

```bash
npm run db:init
```

运行本地检查：

```bash
npm run check
npm run build
python3 -m compileall services/api/src/scholarflow_api
```

安装 Python 依赖后检查 API health：

```bash
npm run health:api
```

## 本地数据

ScholarFlow 是 local-first 项目。CLI 默认将运行数据保存在 `~/.scholarflow`：

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

请不要提交 API key、本地数据库、PDF、日志、用户 artifact、私人笔记或未发表研究材料。
