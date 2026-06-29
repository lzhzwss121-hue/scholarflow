# ScholarFlow: AI 科研全流程 Agent 项目规划

更新时间：2026-06-29

## 1. 项目定位

ScholarFlow 不是一个单纯的论文搜索工具，而是一个面向人工智能领域硕士研究生的科研工作流 Agent。用户输入研究关键词、模糊想法或任务目标后，系统自动完成方向理解、论文检索、文献脉络分析、研究空白判断、实验方案设计、代码复现辅助、结果分析、论文写作辅助和研究任务管理。

项目可以定位为：

> AI Research Workflow Agent: 面向 AI 科研新手和硕士研究生的本地优先科研工作台，用多 Agent 工作流把“找论文、读论文、定方向、做实验、写论文”串成可追踪、可复用、可验证的完整流程。

核心价值不是“帮用户找到更多论文”，而是“帮用户知道下一步该做什么，并把每一步沉淀成研究资产”。

当前产品决策：

- 项目名：`ScholarFlow`。
- 目标形态：先做完整产品骨架，不以单一 demo 为中心。
- 输出语言：中文为主，必要术语保留英文。
- 前端技术：React + Vite。
- MVP 闭环：`关键词输入 -> 文献检索 -> 论文表格 -> deep paper card -> gap analysis -> idea validation -> experiment plan`。

## 2. 目标用户

第一阶段目标用户应聚焦在 AI 方向的硕士研究生和准备进入科研训练的本科高年级学生。

这类用户的共同痛点是：

- 不知道关键词背后有哪些主流技术路线。
- 找到论文后读不出研究脉络和真正的 gap。
- 分不清一篇论文是核心工作、增量工作、工程复现还是边缘改进。
- 想做 idea，但无法判断是否已经被别人做过。
- 看到论文代码仓库后不知道如何复现、改模型、设计 ablation。
- 实验结果出来后不会做对比、统计、画图和写作。
- 论文写作容易变成堆相关工作，缺少问题驱动和证据链。

所以产品应该帮助用户从“论文消费者”变成“可执行研究计划的制定者”。

## 3. 参考 Ddo 的产品形态

可以参考 `Djhhhhhh/Ddo` 的整体呈现方式，但不要照搬它的功能领域。Ddo 的可借鉴点主要是产品组织方式：

- 一个 CLI 作为统一入口，负责初始化、启动、停止、状态查看和 REPL 交互。
- 多服务架构清晰解耦，CLI、后端 API、LLM 服务、Web UI 分层。
- 本地工作空间目录保存配置、日志、知识库和服务状态。
- Web UI / Electron 不是主逻辑，只负责可视化和桌面交互。
- README、设计文档、服务索引、roadmap 写得像一个可发布产品，而不是课程 demo。

你的项目可以做成类似形态：

```text
scholarflow init
scholarflow start
scholarflow status
scholarflow stop
scholarflow ask "VLM hallucination benchmark"
scholarflow plan "我想做多模态可信评测方向"
scholarflow ingest ./papers
scholarflow review ./results.csv
```

本地默认生成：

```text
~/.scholarflow/
├── config.yaml
├── papers/
├── projects/
├── notes/
├── experiments/
├── outputs/
├── vector_store/
├── logs/
└── cache/
```

## 3.1 参考 Claude Code From Scratch 的 Agent 原理

除 Ddo 的产品形态外，ScholarFlow 的 Agent 内核和前端工作流应重点借鉴 `Windy3f3f3f3f/claude-code-from-scratch`。

该项目复现的是 Claude Code 的核心机制：Agent Loop、工具系统、权限检查、Plan Mode、上下文压缩、记忆、技能、多 Agent 和 MCP。对 ScholarFlow 的启发是：

- 用 Agent Loop 驱动科研任务，而不是一次性聊天回答。
- 用 Research Plan Mode 让 Agent 先制定计划，再执行检索、阅读和分析。
- 用工具调用 timeline 展示检索 query、筛选结果、paper card 生成过程和模型成本。
- 用 Artifact Preview 展示论文表、deep paper card、gap board、idea validation report 和 experiment plan。
- 用 Artifact Diff 审阅 Agent 对科研资产的修改。
- 用 Memory/Skills 保存用户偏好、项目决策、论文阅读协议和 novelty check 协议。
- 用 Sub-Agent 拆分 Literature / Reading / Skeptic / Novelty / Experiment 等科研角色。
- 用 MCP 预留 Zotero、GitHub、Hugging Face、Papers with Code 等外部工具接入。

详细分析见：[CLAUDE_CODE_FROM_SCRATCH_ANALYSIS.md](./CLAUDE_CODE_FROM_SCRATCH_ANALYSIS.md)。

## 4. 产品背景

AI 科研的门槛正在从“获取信息”转向“组织信息、验证想法、执行实验”。arXiv、Semantic Scholar、OpenAlex、GitHub 和 Papers with Code 已经让论文和代码更容易获取，但硕士研究生仍然缺少一个能把科研流程串起来的系统。

当前工具大多解决单点问题：

- 文献检索工具擅长找论文，但不一定能生成可执行研究路线。
- 文献图谱工具擅长展示引用关系，但不一定能判断研究 gap。
- 通用聊天模型能解释论文，但容易缺少证据引用和长期项目记忆。
- 代码 Agent 能改代码，但不了解研究目标、实验设计和论文脉络。
- Zotero 等工具擅长文献管理，但不负责科研决策和任务编排。

因此，本项目的机会在于做“科研任务编排层”：把论文、代码、实验、写作和进度管理统一到一个可执行工作流中。

## 5. 核心差异化

项目不能只做“关键词 -> 论文列表”。这个方向太容易被 Elicit、Semantic Scholar、ResearchRabbit、Connected Papers、SciSpace 等工具覆盖。

更合理的差异化是：

1. **AI 领域专用**
   内置 AI 研究任务模板，例如 VLM、LLM、trustworthy AI、image restoration、multimodal alignment、hallucination evaluation、benchmark design、PEFT、agent systems。

2. **从关键词到研究任务**
   用户输入的不是精确 query，而是模糊方向。系统要自动拆解成研究问题、核心术语、技术路线、论文簇和实验切入点。

3. **Novelty check**
   在提出 idea 前，先检索相似工作，输出“已有人做过什么、你的 idea 与它们差在哪、是否只是换数据集/换模型/换指标”。

4. **实验可执行性评估**
   对每个研究方向自动判断：需要哪些数据集、baseline、显卡资源、复现代码、评价指标、预期风险。

5. **代码复现闭环**
   对论文 GitHub 仓库自动生成环境搭建、训练命令、评测命令、数据目录说明和最小复现实验。

6. **研究资产长期沉淀**
   每个项目保存 paper cards、reading notes、gap analysis、experiment plans、run logs、result tables、figures、draft sections。

7. **证据链与可信输出**
   所有研究结论都要回链到论文、代码、实验结果或用户上传材料，避免生成空泛判断。

## 6. 功能模块设计

### 6.1 方向理解 Agent

输入：关键词、自然语言想法、目标领域。

输出：

- 标准化研究方向。
- 核心术语扩展。
- 相关子领域。
- 用户意图分类：综述、找 idea、复现实验、写论文、找代码、分析结果。
- 推荐工作流。

示例：

```text
输入：VLM hallucination benchmark
输出：
- 主方向：trustworthy vision-language model evaluation
- 子问题：object hallucination、evidence faithfulness、visual grounding、benchmark bias
- 推荐流程：先做 survey + benchmark comparison，再做 gap analysis
```

### 6.2 文献检索与筛选 Agent

能力：

- 接入 arXiv、Semantic Scholar、OpenAlex、Crossref、PubMed、GitHub、Papers with Code。
- 自动生成多组检索式。
- 按时间、引用、venue、代码可用性、任务相关性筛选。
- 输出核心论文、代表性论文、最新论文、可复现论文和综述论文。

输出不应该只是列表，而应该是结构化表格：

| 论文 | 年份 | 类型 | 贡献 | 数据集 | 代码 | 与用户方向关系 | 优先级 |
|------|------|------|------|--------|------|----------------|--------|

### 6.3 论文阅读 Agent

论文阅读 Agent 不能只做摘要，而要训练用户理解“为什么这篇论文会被想出来”。因此需要内置一套固定的深度论文分析协议。每次用户上传论文、输入 arXiv 链接或从文献表中选择论文时，系统都按同一结构输出。

#### 6.3.1 深度论文分析协议

1. **研究问题与背景**
   说明论文提出并解决的研究问题是什么。Agent 需要主动补充必要背景，解释为什么这个问题重要，以及解决后能带来哪些科研价值、工程价值或社会价值。

2. **已有研究与不足**
   判断这个问题之前是否已经被解决。总结之前方法的主流路线，并解释它们为什么不足：是数据假设不成立、评价指标不完整、泛化能力差、计算成本高，还是实验设计存在偏差。

3. **作者思考路径重建**
   这是核心能力。Agent 在正式讲方法前，必须模拟作者可能的思考路径。不能把论文自己的贡献当成前提，只能使用论文发表前已有的背景、失败模式、经验观察和相关工作来推导：作者可能看到了什么问题，受到了哪些工作启发，为什么会想到这个 idea。

4. **核心 intuition**
   用简洁语言解释论文方法的本质。目标是让用户先理解“这个 idea 到底聪明在哪里”，再进入技术细节。

5. **具体方法与真实例子**
   结合一个真实或近真实的例子讲完整 pipeline：输入是什么，模型或算法如何处理，中间状态是什么，输出是什么。

6. **数学与理论解释**
   如果论文有核心公式、优化目标、损失函数或理论推导，Agent 需要用 0 基础友好的方式解释。先补充必要数学背景，再解释公式每一项的作用和 intuition。如果论文没有明显数学推导，应明确说明并跳过，不要强行编造理论。

7. **实验如何验证 claim**
   按固定格式总结实验设计：
   `提出了什么问题 -> 设计了什么实验验证这个问题 -> 问题的答案是什么`
   这里不需要堆数据细节，而要解释实验逻辑是否支撑论文 claim。

8. **Take-aways**
   总结用户读完这篇论文应带走的关键认识，包括方法层面、实验层面、研究设计层面和可迁移经验。

9. **最脆弱的假设**
   找出论文最容易被攻击的前提，例如 benchmark 是否代表真实场景、数据分布是否过窄、模型规模假设是否不现实、指标是否能衡量真实能力、人工标注是否可靠。

10. **一周最小复现实验**
    如果用户只有 1 周时间，Agent 应设计一个最小复现实验，只验证论文最关键的一个 claim。输出应包括数据、baseline、运行成本、最小指标和成功/失败判据。

11. **反例设计**
    如果用户要反对这篇论文，Agent 应设计一个能挑战论文核心 claim 的反例。反例必须针对方法缺陷或假设漏洞，而不是泛泛地说“换数据集试试”。

12. **非增量 follow-up idea**
    Agent 需要基于 limitation、未满足需求和反例设计提出一个 follow-up idea。这个 idea 要避免简单换模型、换数据集、加模块，而应从新的失败模式、新的评价视角、新的任务定义或新的机制假设出发。

#### 6.3.2 输出格式

建议将每篇论文的分析结果保存为 `paper_card.md` 和结构化 JSON，方便后续被 gap analysis、idea validation 和 writing agent 调用。

Markdown 输出：

```text
# Paper Card

## 1. Research Problem and Background
## 2. Prior Work and Remaining Gaps
## 3. Reconstructed Author Reasoning Path
## 4. Core Intuition
## 5. Method Pipeline with Example
## 6. Math and Theory Explanation
## 7. Experiment Logic
## 8. Take-aways
## 9. Weakest Assumption
## 10. One-week Minimal Reproduction
## 11. Counterexample Design
## 12. Non-incremental Follow-up Idea
```

结构化字段：

```json
{
  "research_problem": "",
  "importance": "",
  "prior_work_limitations": [],
  "author_reasoning_path": [],
  "core_intuition": "",
  "method_pipeline": {
    "input": "",
    "process": [],
    "output": ""
  },
  "math_theory": {
    "has_core_math": true,
    "background_needed": [],
    "formula_explanations": []
  },
  "experiment_logic": [
    {
      "question": "",
      "experiment": "",
      "answer": ""
    }
  ],
  "takeaways": [],
  "weakest_assumption": "",
  "minimal_reproduction": {
    "time_budget": "1 week",
    "claim_to_test": "",
    "setup": "",
    "success_criterion": ""
  },
  "counterexample": "",
  "follow_up_idea": {
    "idea": "",
    "why_not_incremental": "",
    "new_failure_mode_or_need": "",
    "first_experiment": ""
  }
}
```

#### 6.3.3 Agent 约束

- 不允许只复述 abstract。
- 不允许把论文贡献倒过来当成作者思考路径。
- 不允许把所有 limitation 都写成“需要更多数据”。
- 不允许把 follow-up idea 写成简单加模块、换 backbone、换 benchmark。
- 如果缺少证据，必须标记为“基于当前论文信息的推断”。
- 对数学部分要解释 intuition，不能只翻译公式符号。

这部分要固定模板，保证用户逐渐形成科研阅读习惯，并让后续 novelty check 和实验设计拥有可追踪依据。

### 6.4 文献脉络与 Gap Analysis Agent

对一个方向的论文集合生成：

- 技术路线树。
- 时间线。
- 数据集/benchmark 对比。
- 方法家族对比。
- 常见失败模式。
- 尚未解决的问题。
- 被高频忽视的评价维度。
- 适合硕士生切入的小型研究问题。

关键是要区分三类 gap：

- 真 gap：问题真实存在，已有方法没有解决。
- 工程 gap：可做，但贡献可能偏工程。
- 伪 gap：只是换模型、换数据集、换说法。

### 6.5 Idea 验证 Agent

用户提出 idea 后，系统输出：

- 相似工作检索结果。
- idea 与已有工作的差异。
- novelty risk：高 / 中 / 低。
- feasibility：高 / 中 / 低。
- 实验成本估计。
- 可能被 reviewer 攻击的点。
- 如何改写成更强的研究问题。

这个模块最适合体现你的项目壁垒，因为新手最缺的不是论文，而是判断 idea 是否值得做。

### 6.6 实验设计 Agent

对研究问题生成：

- baseline 列表。
- 数据集选择。
- evaluation metrics。
- ablation plan。
- compute 需求估计。
- 训练/评测流程。
- 实验优先级。
- 失败风险和 fallback plan。

AI 领域建议内置模板：

- VLM hallucination evaluation。
- Multimodal alignment evaluation。
- LLM reasoning benchmark。
- PEFT / LoRA adaptation。
- Image restoration / super-resolution。
- Agent benchmark。
- Robustness / reliability analysis。

### 6.7 代码复现 Agent

输入：论文 GitHub 仓库或本地 repo。

输出：

- repo 结构解释。
- 环境依赖。
- 数据准备方式。
- 最小可运行命令。
- 训练入口。
- 评测入口。
- 模型 checkpoint 位置。
- 常见报错处理。
- 可修改模块定位。

进一步功能：

- 自动生成 `reproduce.md`。
- 自动生成 `run.sh`。
- 自动标记核心模型文件。
- 根据用户实验目标建议改哪些类、函数和配置。

### 6.8 实验结果分析 Agent

输入：CSV、日志、TensorBoard、wandb 导出、表格截图。

输出：

- 指标对比。
- 是否超过 baseline。
- 结果是否稳定。
- ablation 是否支持 claim。
- 可视化图表。
- 论文 Results 段落草稿。
- reviewer 可能质疑的问题。

### 6.9 写作与投稿 Agent

能力：

- 生成 paper outline。
- 写 related work 草稿，但要求每句话绑定引用。
- 写 method section 结构。
- 将实验表格转成论文描述。
- 检查 claim 是否被实验支持。
- 生成 limitations。
- 模拟 reviewer 预审。
- 辅助 rebuttal。

限制：

- 不承诺自动生成可投稿论文。
- 不伪造引用。
- 不把没有实验支持的 claim 写成结论。

### 6.10 研究任务管理 Agent

每个科研项目自动维护：

- 当前阶段：survey / idea / experiment / writing / revision。
- 下一步任务。
- 截止时间。
- 阻塞原因。
- 已读论文。
- 已跑实验。
- 失败实验记录。
- 可复用代码和结论。

这能让项目从“聊天工具”升级成“科研操作系统”。

## 7. 推荐 MVP

第一版不要做全流程。建议做一个能展示产品价值的闭环：

> 关键词输入 -> 论文检索 -> 文献聚类 -> 深度 paper card -> gap analysis -> idea 验证 -> 实验计划 -> 项目卡片保存

MVP 功能：

1. 用户创建 research project。
2. 输入关键词和目标，例如 `VLM hallucination evaluation`。
3. 系统自动调用 arXiv / Semantic Scholar / OpenAlex 检索论文。
4. 生成 20 篇候选论文表格。
5. 自动分成核心论文、最新论文、综述论文、可复现论文。
6. 用户选择 1-3 篇核心论文，系统按 12 步协议生成 deep paper card。
7. 基于 paper card 生成研究脉络图和 gap analysis。
8. 生成 3 个可执行 idea，但每个 idea 必须附带 novelty risk。
9. 选择一个 idea 后，生成实验计划。
10. 保存为项目资产，可在 Web UI 中继续查看。

这版就已经明显强于“论文搜索工具”。

## 8. Ddo 式技术架构

建议采用多服务架构，但比 Ddo 更贴近 AI 科研任务。

```text
User Layer
├── CLI: research-agent
├── Web UI: research workspace dashboard
└── optional Electron: notification / quick capture

Gateway Layer
├── FastAPI or Go API Gateway
├── Project service
├── Paper service
├── Experiment service
├── Task scheduler
└── Auth / config / logs

Agent Layer
├── Intent Agent
├── Literature Agent
├── Reading Agent
├── Gap Analysis Agent
├── Novelty Check Agent
├── Experiment Design Agent
├── Code Reproduction Agent
├── Result Analysis Agent
└── Writing Review Agent

Data Layer
├── PostgreSQL or SQLite: projects, papers, paper_cards, tasks, experiments
├── Vector DB: Chroma / Qdrant / FAISS
├── File storage: PDFs, notes, outputs, figures
└── Cache: API responses and embeddings

External APIs
├── LLM API: OpenAI / OpenRouter / Claude / Gemini
├── Paper APIs: arXiv / Semantic Scholar / OpenAlex / Crossref
├── Code APIs: GitHub REST API
├── Citation tools: Zotero API
└── optional: Papers with Code / Hugging Face
```

## 8.1 用户使用方式

ScholarFlow 应采用“双入口、同一后端”的产品设计：

1. **Web UI 是主入口**
   大多数用户不应该被迫使用 CLI。硕士研究生的核心操作包括创建研究项目、查看论文表格、阅读 deep paper card、比较 gap、选择 idea、查看实验计划，这些都更适合在 Web UI 中完成。

2. **CLI 是开发者和高级用户入口**
   CLI 负责初始化、启动服务、批量导入论文、查看状态、运行批处理任务。它参考 Ddo 的统一入口设计，但不作为普通用户的唯一入口。

推荐使用路径：

```text
第一次使用：
scholarflow init
scholarflow start
浏览器自动打开 http://localhost:5173

日常使用：
1. 在 Web UI 创建 Research Project
2. 输入关键词和研究目标
3. 等待系统生成论文表格
4. 选择核心论文生成 deep paper card
5. 查看 gap analysis
6. 输入或选择 idea 做 novelty validation
7. 生成 experiment plan
8. 保存到项目记忆
```

CLI 命令设计：

```text
scholarflow init                         # 初始化 ~/.scholarflow
scholarflow start                        # 启动 API、Agent、Web UI
scholarflow stop                         # 停止本地服务
scholarflow status                       # 查看服务状态
scholarflow create "VLM hallucination"   # 创建研究项目
scholarflow search "multimodal alignment"
scholarflow read paper.pdf               # 生成 deep paper card
scholarflow validate idea.md             # 做 idea novelty validation
scholarflow plan project-id              # 生成实验计划
scholarflow github connect               # 连接 GitHub 同步
scholarflow github sync project-id        # 手动同步项目进度
```

第一版建议重点做 Web UI，CLI 只做启动和批处理。这样产品更容易被非工程背景的研究生使用。

## 8.2 模型连接策略

ScholarFlow 不应该绑定单一模型，而应该设计成 provider-agnostic，即支持多个模型供应商，通过统一的 `ModelProvider` 接口调用。

推荐分层：

| 任务类型 | 推荐模型策略 | 原因 |
|----------|--------------|------|
| 方向理解、关键词扩展 | 中低成本 fast model | 调用频繁，成本敏感 |
| 论文摘要、paper card 初稿 | 高上下文模型 | 需要处理长论文文本 |
| 作者思考路径、脆弱假设、反例设计 | 强推理模型 | 需要跨论文推理和批判性判断 |
| novelty validation | 强推理模型 + 检索证据 | 容易误判，必须结合相似工作 |
| 实验计划生成 | 强推理模型 | 要同时考虑数据、baseline、指标和资源 |
| embedding / RAG | 专用 embedding model | 用于向量检索和项目记忆 |

推荐默认配置：

```text
LLM 主模型：DeepSeek V4 Pro，模型 ID 使用 `deepseek-v4-pro`
LLM 快速模型：DeepSeek V4 Flash，模型 ID 使用 `deepseek-v4-flash`
Embedding 模型：text-embedding-3-large 或同级 embedding model
备选接入：OpenAI / OpenRouter，用于切换 Claude、Gemini、Qwen、OpenAI 等模型
```

配置文件示例：

```yaml
models:
  default_provider: deepseek
  reasoning_model: deepseek-v4-pro
  fast_model: deepseek-v4-flash
  embedding_model: text-embedding-3-large
  fallback_provider: openrouter

providers:
  deepseek:
    base_url: https://api.deepseek.com
    api_key_env: DEEPSEEK_API_KEY
  openai:
    api_key_env: OPENAI_API_KEY
  openrouter:
    api_key_env: OPENROUTER_API_KEY
```

工程上需要注意：

- 不要把 API key 写进数据库或代码仓库，只读取环境变量。
- 每次模型调用保存输入摘要、输出、证据来源、token 成本和耗时。
- 对高风险输出加 `evidence_required=true`，强制引用论文或检索结果。
- 对 deep paper card、gap analysis、novelty validation 做版本记录，方便用户回看。
- 允许用户在设置页切换模型供应商，但系统内部仍使用统一接口。

## 8.3 借鉴 Claude Code 的前端工作流

ScholarFlow 可以借鉴 Claude Code 的交互思想，但不要照搬代码编辑器。Claude Code 的核心价值是让用户看到 Agent 正在做什么、准备做什么、调用了什么工具、修改了什么结果，并在关键步骤让用户确认。这个思想可以转译成科研工作流前端。

建议设计为“三栏工作台”：

```text
┌──────────────────┬──────────────────────────┬──────────────────────┐
│ Project Navigator│ Agent Workspace           │ Artifact Preview     │
│                  │                          │                      │
│ - Projects       │ - 对话 / 指令输入          │ - Paper table         │
│ - Papers         │ - 当前计划 checklist       │ - Deep paper card     │
│ - Ideas          │ - 工具调用 timeline        │ - Gap board           │
│ - Experiments    │ - 待确认动作              │ - Experiment plan     │
└──────────────────┴──────────────────────────┴──────────────────────┘
```

可以借鉴的机制：

1. **Plan-first**
   Agent 在执行复杂任务前先生成计划，例如“检索论文 -> 筛选核心论文 -> 生成 paper cards -> 做 gap analysis”。用户确认后再执行。

2. **Tool timeline**
   每一步工具调用都可见：调用了 arXiv、Semantic Scholar、OpenAlex、GitHub，检索式是什么，返回了多少结果，筛掉了哪些论文。

3. **Permission gates**
   对高成本或会改变项目状态的动作要求确认，例如批量下载 PDF、生成 10 篇 paper card、调用强推理模型、覆盖已有实验计划、推送内容到 GitHub。

4. **Artifact preview**
   每个 Agent 输出都不是一段聊天，而是可预览、可保存、可版本化的 artifact：paper table、paper card、gap board、idea validation report、experiment plan。

5. **Diff view**
   当 Agent 更新已有 artifact 时，显示变更差异。例如新版 gap analysis 增加了哪些 gap，删除了哪些弱 idea，实验计划改了哪些 baseline。

6. **Interrupt and steer**
   用户可以在 Agent 执行中暂停并改变方向，例如“不要继续找 image restoration，转向 VLM hallucination evaluation”。

7. **Session memory**
   每次执行都保存为 research session，包括用户目标、计划、工具调用、证据、输出版本和最终结论。

这套前端工作流比普通聊天框更适合 ScholarFlow，因为科研任务天然需要长链路、证据追踪和多轮修正。

## 8.4 GitHub Progress Sync

注意：本节是可选产品功能，指“用户把自己的科研项目进度同步到 GitHub”。这不同于 ScholarFlow 项目本身开源。ScholarFlow 本体开源策略见下一节。

ScholarFlow 可以加入 GitHub 进度同步功能，让用户把科研任务进度近实时推送到自己的 GitHub 仓库。这里的“实时”不应该理解成每个 token 都 push，而应该是事件驱动的 near-real-time sync：每完成一个计划步骤、生成一个 artifact、用户确认一个重要决策，系统就生成进度事件，并按队列同步到 GitHub。

推荐设计：

```text
Agent 执行步骤
  -> ProgressEvent
  -> 本地 SessionStore
  -> SyncQueue
  -> GitHubSyncWorker
  -> GitHub Issue / Commit / Project Board
```

### 同步到 GitHub 的三种形式

1. **GitHub Issue 作为进度流**
   每个 ScholarFlow research project 自动创建一个 GitHub Issue。Agent 每完成一个阶段，就在 issue 下追加 comment。

   示例：

   ```text
   [ScholarFlow] VLM hallucination evaluation

   Progress:
   - Created research project
   - Retrieved 42 candidate papers from arXiv / Semantic Scholar / OpenAlex
   - Selected 8 core papers
   - Generated 3 deep paper cards
   - Found 2 high-value gaps
   - Generated experiment plan v1
   ```

2. **Markdown artifact 同步到仓库**
   将核心产物保存为 Markdown，并提交到指定分支，例如 `scholarflow/progress`。

   推荐目录：

   ```text
   research/
   └── vlm-hallucination-evaluation/
       ├── README.md
       ├── progress.md
       ├── papers.md
       ├── paper-cards/
       │   ├── paper-001.md
       │   └── paper-002.md
       ├── gap-board.md
       ├── idea-validation.md
       └── experiment-plan.md
   ```

3. **GitHub Project Board / Labels**
   后续可以把阶段同步到 GitHub Project，例如：

   ```text
   survey -> reading -> gap analysis -> idea validation -> experiment planning -> reproduction -> writing
   ```

   这更适合 Pro / Lab 版，不建议 MVP 第一阶段优先做。

### 同步策略

MVP 建议实现：

- 每个项目对应一个 GitHub Issue。
- 每个 artifact 版本保存为 Markdown 文件。
- 每次重要事件进入 `SyncQueue`。
- 后台 worker 每 30-60 秒批量同步，或在阶段完成时立即同步。
- Web UI 显示同步状态：`pending / syncing / synced / failed`。
- 失败后指数退避重试，不阻塞 Agent 主流程。

不要每次模型输出一个字就推送 GitHub，这会导致 API 限流、commit 噪音和隐私风险。

### ProgressEvent 数据结构

```json
{
  "id": "event_001",
  "project_id": "proj_vlm_hallucination",
  "session_id": "sess_20260629_001",
  "type": "artifact_created",
  "stage": "deep_paper_reading",
  "title": "Generated deep paper card for paper-001",
  "summary": "Completed 12-step paper analysis and identified weakest assumption.",
  "artifact_ids": ["paper_card_001"],
  "created_at": "2026-06-29T12:00:00+09:00",
  "sync_status": "pending"
}
```

### GitHub 权限与安全

GitHub 同步必须是用户显式开启的功能，默认关闭。

安全要求：

- 使用 GitHub fine-grained token 或 GitHub App，不把 token 写入仓库。
- token 只保存在本地配置或系统 keychain。
- 默认不上传论文 PDF 原文。
- 默认不上传完整闭源代码仓库内容。
- 默认不上传 API key、模型响应原始日志、用户隐私信息。
- public repo 模式下只同步 summary 和 artifact markdown。
- private repo 模式下才允许同步更完整的 research session。
- 覆盖远程 artifact 前必须显示 diff 或创建新版本。

### 前端设计

Web UI 增加一个 `GitHub Sync` 面板：

```text
GitHub Sync
├── Connected account
├── Target repository
├── Sync mode: Issue only / Markdown files / Issue + files
├── Branch: scholarflow/progress
├── Visibility warning: public repo / private repo
├── Last synced at
├── Pending events
└── Sync errors
```

在 Agent Workspace 的 Tool Timeline 中显示：

```text
GitHub Sync
Status: synced
Target: hyp666/scholarflow-progress#12
Updated: progress.md, gap-board.md, experiment-plan.md
```

### CLI 设计

```text
scholarflow github connect
scholarflow github status
scholarflow github set-repo hyp666/scholarflow-progress
scholarflow github sync project-id
scholarflow github disconnect
```

### 技术实现建议

MVP 可以先使用 GitHub REST API：

- 创建 / 更新 issue。
- 创建 issue comment。
- 创建或更新 repository file content。
- 查询 branch 和 commit SHA。

后续再支持：

- GitHub App 安装授权。
- GitHub Projects v2。
- GitHub Actions 自动生成项目页面。
- GitHub Pages 发布 research progress dashboard。

## 8.5 ScholarFlow 开源发布策略

ScholarFlow 项目本身应从第一天按开源产品标准组织，而不是先做成本地杂乱 demo，最后再整理。目标是让 GitHub 仓库本身成为简历、申请材料和产品展示的一部分。

### 开源仓库定位

推荐仓库名：

```text
scholarflow
```

一句话定位：

```text
ScholarFlow is an open-source AI research workflow agent that turns ambiguous research goals into traceable literature maps, deep paper cards, gap analysis, novelty validation, and executable experiment plans.
```

中文定位：

```text
ScholarFlow 是一个开源 AI 科研工作流 Agent，将模糊研究方向转化为可追踪的论文图谱、深度论文卡片、研究空白分析、idea 新颖性验证和可执行实验计划。
```

### 推荐开源仓库结构

```text
scholarflow/
├── README.md
├── LICENSE
├── SECURITY.md
├── CONTRIBUTING.md
├── CODE_OF_CONDUCT.md
├── ROADMAP.md
├── CHANGELOG.md
├── .env.example
├── .gitignore
├── docs/
│   ├── architecture.md
│   ├── agent-loop.md
│   ├── deep-paper-card.md
│   ├── github-sync.md
│   └── api-integrations.md
├── apps/
│   ├── web/                 # React + Vite
│   └── cli/                 # Node.js CLI
├── services/
│   └── api/                 # Python FastAPI
├── packages/
│   ├── agent-core/
│   ├── research-tools/
│   └── schemas/
├── examples/
│   ├── sample-project/
│   └── sample-paper-card.md
└── tests/
```

### README 必须展示的内容

README 不要只写安装命令。它应该像产品首页一样清楚展示：

- ScholarFlow 是什么。
- 它解决什么科研痛点。
- 核心工作流截图或 GIF。
- Claude Code 式 Agent Loop 如何迁移到科研任务。
- Deep Paper Card 的 12 步分析协议。
- 支持的外部 API：DeepSeek、arXiv、Semantic Scholar、OpenAlex、GitHub。
- 本地数据与隐私策略。
- 快速开始。
- Roadmap。
- 贡献方式。

推荐 README 首屏结构：

```text
# ScholarFlow

Open-source AI research workflow agent for literature discovery, deep paper reading, gap analysis, novelty validation, and experiment planning.

## Why ScholarFlow
## Core Workflow
## Demo Screenshots
## Quick Start
## Architecture
## Roadmap
```

### License 建议

推荐使用 `MIT License`。

原因：

- 简单。
- 对商业化友好。
- 对个人开源项目传播友好。
- 方便别人 fork、二次开发、引用。

如果你后续担心商业公司直接拿去闭源，可以考虑 `AGPL-3.0`，但它会降低部分开发者和企业试用意愿。第一版建议 MIT。

### 什么可以开源，什么不能开源

可以开源：

- 前端代码。
- CLI 代码。
- Agent 编排逻辑。
- 工具 schema。
- prompt 模板。
- deep paper card 协议。
- mock 数据。
- 示例 paper card。
- API adapter 代码。

不能开源：

- `.env`
- API key。
- 用户真实论文 PDF。
- 用户本地研究项目数据。
- 模型原始响应日志。
- GitHub token。
- 未授权论文全文缓存。
- 任何含个人隐私或申请材料的文件。

`.gitignore` 必须覆盖：

```text
.env
.env.*
!.env.example
data/
storage/
uploads/
papers/
outputs/
logs/
*.sqlite
*.db
*.pdf
*.key
```

### 开源发布里程碑

建议分 4 个公开阶段：

#### v0.1.0 Skeleton

- Monorepo 结构。
- React 前端三栏工作台静态页面。
- FastAPI 后端健康检查。
- CLI `scholarflow init/start/status`。
- README、ROADMAP、架构文档。

#### v0.2.0 Literature MVP

- arXiv / OpenAlex / Semantic Scholar 检索。
- Paper table。
- Research project 创建。
- 基础 artifact store。

#### v0.3.0 Deep Paper Card

- PDF / abstract 输入。
- Deep paper card 12 步协议。
- Paper Reader 页面。
- Artifact versioning。

#### v0.4.0 Research Workflow

- Gap analysis。
- Idea novelty validation。
- Experiment plan。
- GitHub progress sync 可选功能。

### GitHub 仓库展示策略

仓库要让别人一眼看懂项目价值。

建议开启：

- GitHub Issues：收集 bug 和功能请求。
- GitHub Discussions：收集科研工作流建议。
- GitHub Projects：展示 roadmap。
- GitHub Actions：跑 lint/test。
- GitHub Pages：后续发布项目文档站。

推荐 labels：

```text
agent-core
frontend
backend
paper-search
paper-reading
gap-analysis
novelty-check
experiment-plan
github-sync
good-first-issue
research-feedback
```

### 对简历和申请的价值

开源后，项目不只是“我做了一个工具”，而是可以表达为：

> Built and open-sourced ScholarFlow, an AI research workflow agent inspired by Claude Code's agent loop, supporting literature discovery, deep paper cards, gap analysis, novelty validation, and experiment planning through a React + FastAPI + multi-agent architecture.

中文：

> 开源开发 ScholarFlow，一个借鉴 Claude Code Agent Loop 的 AI 科研工作流 Agent，支持文献检索、深度论文卡片、研究空白分析、idea 新颖性验证和实验计划生成，采用 React + FastAPI + 多 Agent 架构。

### 开源与商业化的关系

推荐采用 open-core 路线：

- 开源核心：本地单用户、论文检索、paper card、gap analysis、experiment plan。
- 后续商业功能：云同步、多用户协作、实验室看板、更高 API 额度、GitHub/Zotero 深度集成、团队知识库。

这样既能扩大影响力，也保留未来商业化空间。

## 9. 技术选型建议

为了简历和商用潜力，建议这样选：

| 模块 | 推荐技术 | 原因 |
|------|----------|------|
| CLI | Node.js + Commander | 参考 Ddo，便于 npm 分发 |
| Web UI | React + Vite | 展示工作流和项目资产 |
| Agent 服务 | Python + FastAPI | AI 生态完整，方便接 API |
| 数据库 | SQLite 起步，后续 PostgreSQL | MVP 简单，后续可扩展 |
| 向量库 | Chroma / Qdrant | 支持本地 RAG |
| 任务队列 | Celery / RQ / APScheduler | 处理长任务 |
| PDF 解析 | PyMuPDF / GROBID / marker | 论文结构化 |
| 图谱 | NetworkX + 前端图可视化 | 展示文献关系 |
| LLM 编排 | LangGraph / 自研状态机 | 保证工作流可追踪 |
| API 数据源 | Semantic Scholar、OpenAlex、arXiv、GitHub | 覆盖论文和代码 |
| GitHub 同步 | GitHub REST API / GitHub App | 近实时同步任务进度和 Markdown artifact |

## 10. Web UI 页面设计

参考 Ddo 的简洁工作台，但你的 UI 应围绕科研对象组织。

推荐页面：

1. **Dashboard**
   展示所有 research projects、当前阶段、待读论文、待跑实验、最近输出。

2. **New Project**
   输入关键词、研究目标、用户背景、资源限制。

3. **Literature Map**
   展示论文簇、引用关系、技术路线、时间线。

4. **Paper Table**
   结构化论文表格，支持筛选“有代码 / 最新 / 高相关 / benchmark / survey”。

5. **Paper Reader**
   按 12 步深度论文分析协议展示 paper card，重点突出作者思考路径、核心 intuition、最脆弱假设、最小复现实验、反例设计和非增量 follow-up idea。

6. **Gap Board**
   展示真 gap、工程 gap、伪 gap，以及每个 gap 的证据来源。

7. **Idea Validator**
   用户输入 idea，系统给 novelty / feasibility / risk / experiment cost。

8. **Experiment Planner**
   展示 baseline、dataset、metric、ablation、run commands。

9. **Research Memory**
   保存笔记、结论、失败实验和写作素材。

10. **GitHub Sync**
    连接用户 GitHub 仓库，展示 issue 同步、Markdown artifact 同步、pending events、失败重试和 public/private 可见性提醒。

## 11. 商业化方向

初期不要直接面向“大科研机构”。更现实的路径是：

### 11.1 Free 本地版

- 单用户。
- 本地项目管理。
- arXiv / Semantic Scholar / OpenAlex 检索。
- 基础 literature map。
- 基础 gap analysis。

目标：建立开源影响力和简历项目可信度。

### 11.2 Pro 版

- 更多 API 调用额度。
- 长文 PDF 精读。
- 代码仓库复现分析。
- 自动实验计划。
- 结果分析和论文写作检查。
- Zotero / GitHub / Hugging Face 集成。
- GitHub progress sync，将项目进度、paper cards、gap board 和 experiment plan 同步到用户仓库。

目标用户：硕士、博士、科研训练营、留学生申请群体。

### 11.3 Lab 版

- 多人协作。
- 课题组共享 paper library。
- 学生项目进度管理。
- 每周 research digest。
- PI 查看每个学生的阅读和实验进展。

目标用户：高校实验室、小型 AI 研究团队。

## 12. 项目护城河

真正的壁垒不在“调用大模型”，而在以下几个方面：

- AI 领域任务模板库。
- 深度 paper card 协议，尤其是作者思考路径重建、最脆弱假设识别、反例设计和非增量 follow-up idea 生成。
- 论文、代码、实验、写作之间的数据结构设计。
- 研究 gap 和 novelty check 的评估规则。
- 可追踪证据链，避免空泛生成。
- 长期项目记忆。
- 对新手科研流程的产品化引导。
- 从 idea 到实验的可执行转换。

如果你想把这个项目写进简历，重点应放在：

> Built a multi-agent AI research workflow system that transforms ambiguous research keywords into evidence-grounded literature maps, novelty-risk analysis, executable experiment plans, and persistent research project memory.

## 13. 简历项目描述

中文版本：

> 设计并开发面向 AI 科研流程的多 Agent 工作台，支持从关键词输入到文献检索、论文聚类、深度论文分析、研究空白分析、idea 新颖性验证、实验方案生成和研究资产沉淀的完整流程。系统接入 arXiv、Semantic Scholar、OpenAlex、GitHub 等外部 API，并使用 RAG、向量检索和多 Agent 编排实现证据可追踪的科研辅助决策。

英文版本：

> Designed and implemented a multi-agent AI research workflow workspace that transforms ambiguous research keywords into structured literature maps, deep paper cards, gap analysis, novelty-risk assessment, executable experiment plans, and persistent research memory. Integrated external scholarly and code APIs including arXiv, Semantic Scholar, OpenAlex, and GitHub, with RAG-based evidence grounding and workflow orchestration for reproducible research assistance.

## 14. 第一阶段开发路线

### Week 1: 项目骨架

- CLI 初始化。
- FastAPI 后端。
- SQLite 数据库。
- Web UI 基础 dashboard。
- 本地 workspace 目录。

### Week 2: 文献检索

- 接入 arXiv。
- 接入 Semantic Scholar 或 OpenAlex。
- 论文元数据标准化。
- 论文表格展示。

### Week 3: RAG 与论文卡片

- PDF / abstract 解析。
- embedding。
- deep paper card 生成。
- 12 步单篇论文阅读协议。
- 作者思考路径、最脆弱假设、反例设计、follow-up idea 字段结构化。

### Week 4: Gap Analysis

- 论文聚类。
- 技术路线总结。
- gap 分类。
- novelty risk 初版。

### Week 5: 实验计划

- 数据集、baseline、metric 推荐。
- ablation plan 生成。
- 输出 `experiment_plan.md`。

### Week 6: Demo 打磨

- README。
- 截图。
- 示例项目。
- 英文简历描述。
- 项目视频或 GIF。

## 15. 第一版 Demo 场景

建议用你自己更适合申请的方向做 demo：

```text
关键词：VLM hallucination evaluation
用户目标：我想找一个适合硕士生做的可信多模态评测方向
资源限制：单卡 24GB，2 个月，最好有开源代码
系统输出：
1. 20 篇核心论文表格
2. VLM hallucination 技术路线图
3. 现有 benchmark 的局限
4. 3 个 idea 和 novelty risk
5. 推荐一个最可执行 idea
6. 实验计划和 baseline 列表
```

这个 demo 能同时服务你的简历、申请材料和产品展示。

## 16. 不建议第一阶段做的功能

第一阶段不要做：

- 自动生成完整论文。
- 自动跑任意代码仓库。
- 多人协作系统。
- 复杂权限系统。
- 端到端自动训练模型。
- 大规模私有论文数据库。
- 过早做 Electron。

这些会拖慢 MVP。你应该先证明“从关键词到可执行科研计划”的闭环。

## 17. 下一步决策

项目名、技术栈和 MVP 闭环已经确定。下一步应直接按开源仓库标准搭建 ScholarFlow。

阶段实现细节以 [IMPLEMENTATION_PHASES.md](./IMPLEMENTATION_PHASES.md) 为准。后续开发必须一个阶段一个阶段推进，当前阶段未验收前不进入下一阶段。

推荐优先级：

1. 创建 `scholarflow` GitHub 仓库。
2. 加入 `README.md`、`LICENSE`、`ROADMAP.md`、`CONTRIBUTING.md`、`.env.example`、`.gitignore`。
3. 搭建 monorepo：`apps/web`、`apps/cli`、`services/api`、`packages/schemas`。
4. 先写架构图和 deep paper card 协议文档。
5. 实现 CLI + React + FastAPI + SQLite 基础骨架。
6. 做一个关键词输入到论文表格的最小链路。
7. 再做 deep paper card、gap analysis 和 idea validation。

第一阶段成功标准：

> 用户输入一个 AI 研究方向，系统能在 3-5 分钟内输出结构化文献表、研究脉络、潜在 gap、idea 风险评估和实验计划草稿。
