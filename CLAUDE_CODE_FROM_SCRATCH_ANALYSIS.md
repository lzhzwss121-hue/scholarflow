# Claude Code From Scratch 项目理解与 ScholarFlow 迁移设计

更新时间：2026-06-29

分析对象：`Windy3f3f3f3f/claude-code-from-scratch`

## 1. 这个项目到底复现了什么

这个仓库不是 Claude Code 官方源码，也不是 Claude Code 的前端复刻。它是一个教学型最小实现，用约 4300 行 TypeScript 和约 3800 行 Python 复现 Claude Code 的核心 Agent 架构。

它复现的重点包括：

- Agent Loop：模型输出 tool call，系统执行工具，再把结果喂回模型，循环直到完成。
- 工具系统：读文件、写文件、编辑文件、搜索、Shell、Web Fetch、技能、子 Agent、Plan Mode、MCP。
- 权限系统：默认模式、Plan 模式、自动批准编辑、绕过权限、自动拒绝。
- 上下文管理：大结果持久化、工具结果裁剪、snip、microcompact、auto-compact。
- 记忆系统：项目级记忆索引、语义召回、异步预取。
- 技能系统：通过 `SKILL.md` 定义可复用工作流 prompt。
- 多 Agent：主 Agent 通过 `agent` 工具派生 explore / plan / general 子 Agent。
- MCP：通过 JSON-RPC over stdio 动态连接外部工具服务器。
- 会话持久化：保存消息历史，支持 resume。

对 ScholarFlow 最有价值的不是代码编辑功能，而是它把一个复杂任务拆成了：计划、工具调用、权限确认、执行轨迹、结果回填、上下文压缩、长期记忆、可复用技能。

## 2. Claude Code 的核心原理

### 2.1 Agent Loop

Claude Code 的本质不是“模型一次性回答”，而是一个循环：

```text
用户输入
  -> 组装 system prompt + 当前上下文 + 工具 schema
  -> 调用模型
  -> 模型返回 text 或 tool_use
  -> 如果有 tool_use，系统执行工具
  -> 工具结果作为新消息回填给模型
  -> 模型基于工具结果继续推理
  -> 没有 tool_use 时结束
```

这个循环解释了为什么 Claude Code 能完成复杂任务：模型不是凭空猜，而是不断向外部环境取证、操作、验证。

迁移到 ScholarFlow：

```text
用户输入研究方向
  -> Intent Agent 判断任务
  -> Literature Tool 检索论文
  -> Paper Parser Tool 解析论文
  -> Reading Agent 生成 deep paper card
  -> Gap Agent 生成 gap board
  -> Novelty Agent 调用检索工具查重
  -> Experiment Agent 生成实验计划
  -> 所有结果保存为 project artifacts
```

### 2.2 工具系统

这个项目的工具不是普通函数，而是模型可调用的能力。每个工具都有：

- `name`
- `description`
- `input_schema`
- 执行函数
- 权限检查
- 结果截断或持久化

Claude Code 的关键思想是：**模型负责决定调用什么工具，系统负责安全执行工具**。

ScholarFlow 应该有科研工具，而不是代码工具：

| Claude Code 工具 | ScholarFlow 对应工具 |
|------------------|----------------------|
| `read_file` | `read_paper`, `read_pdf`, `read_project_note` |
| `grep_search` | `search_papers`, `search_claims`, `search_similar_work` |
| `web_fetch` | `fetch_arxiv`, `fetch_semantic_scholar`, `fetch_openalex` |
| `edit_file` | `update_paper_card`, `update_gap_board`, `update_experiment_plan` |
| `run_shell` | `run_reproduction_command`, `run_metric_analysis` |
| `agent` | `literature_agent`, `skeptic_agent`, `experiment_agent` |
| `skill` | `paper_reading_protocol`, `novelty_check_protocol` |
| MCP tools | Zotero、GitHub、Hugging Face、Papers with Code、local filesystem |

### 2.3 Plan Mode

Plan Mode 的核心不是“只规划不执行”，而是：

1. 进入只读模式。
2. Agent 先探索上下文。
3. 生成计划文件。
4. 用户审批。
5. 审批后再执行。

对 ScholarFlow 来说，Plan Mode 应该变成 **Research Plan Mode**：

```text
输入：我想做 VLM hallucination evaluation
Agent 先不生成最终 idea，而是：
1. 解释它准备查哪些论文源
2. 说明会如何筛选论文
3. 说明会如何判断 novelty
4. 说明会输出哪些 artifacts
5. 等用户确认后再执行
```

这能防止科研 Agent 直接给出空泛结论。

### 2.4 权限系统

Claude Code 的权限模式很重要，因为 Agent 能执行真实操作。它区分：

- 只读工具自动允许。
- 编辑类工具按模式确认。
- 危险命令需要确认。
- Plan Mode 禁止修改。
- CI 模式自动拒绝需要确认的操作。

ScholarFlow 也需要权限系统，但权限对象不是代码文件，而是科研资产和成本：

| 动作 | 默认策略 |
|------|----------|
| 检索论文 | 自动允许 |
| 读取本地论文 | 自动允许 |
| 下载大量 PDF | 需要确认 |
| 调用强推理模型生成 10 篇 paper card | 需要确认成本 |
| 覆盖已有 paper card | 需要确认 |
| 覆盖 experiment plan | 需要确认 |
| 运行外部 GitHub 代码 | 需要确认 |
| 删除项目资产 | 禁止或强确认 |

### 2.5 上下文压缩

Claude Code 解决长任务上下文爆炸的方式是分层压缩：

- 大工具结果先保存到磁盘，只把预览和路径放入上下文。
- 根据上下文压力动态裁剪工具结果。
- 旧的搜索结果和文件读取结果可以 snip。
- 空闲后 microcompact。
- 超过阈值时 auto-compact，总结成摘要。

ScholarFlow 也必须这样设计，因为论文、PDF、检索结果、代码仓库都很大。

推荐策略：

```text
完整 PDF / paper text -> 文件存储
论文摘要 / chunk embedding -> 向量库
deep paper card -> 结构化数据库
Agent 上下文 -> 只放必要片段、证据引用和 artifact ID
```

不要把整篇论文反复塞进模型上下文。Agent 应该通过 artifact ID 和检索工具按需读取。

### 2.6 记忆系统

该项目的记忆系统有两个关键点：

- `MEMORY.md` 是索引，不是正文容器。
- 真正的记忆按文件保存，按需语义召回。

ScholarFlow 的研究记忆也应该这样做：

```text
~/.scholarflow/projects/{project_id}/memory/
├── MEMORY.md
├── user_preference.md
├── project_decisions.md
├── rejected_ideas.md
├── failed_experiments.md
└── reviewer_style_feedback.md
```

Agent 每次工作前只读取索引，真正需要时再召回具体记忆。

### 2.7 技能系统

技能系统本质是可复用的 prompt 工作流。Claude Code 用 `.claude/skills/<name>/SKILL.md` 保存技能。

ScholarFlow 应该内置科研技能：

```text
skills/
├── deep-paper-reading/
│   └── SKILL.md
├── novelty-check/
│   └── SKILL.md
├── gap-analysis/
│   └── SKILL.md
├── experiment-plan/
│   └── SKILL.md
├── rebuttal-draft/
│   └── SKILL.md
└── related-work-writing/
    └── SKILL.md
```

你之前提出的 12 步论文分析流程就应该做成 `deep-paper-reading` 技能。

### 2.8 多 Agent

该项目的多 Agent 是 fork-return 模式：主 Agent 创建子 Agent，子 Agent 独立完成任务，最后只返回结果。

ScholarFlow 应该用类似模式：

| 子 Agent | 角色 |
----------|------|
| Literature Agent | 检索和筛选论文 |
| Reading Agent | 生成 deep paper card |
| Skeptic Agent | 找脆弱假设和反例 |
| Novelty Agent | 检索相似工作，判断是否重复 |
| Experiment Agent | 设计 baseline、dataset、metric、ablation |
| Writing Agent | 把研究资产转成论文段落 |

最重要的是：不同 Agent 要有不同工具权限和输出格式。不能让所有 Agent 共用一个泛化 prompt。

### 2.9 MCP

MCP 的价值是让 Agent 动态接外部工具。Claude Code 通过 `mcp__server__tool` 命名避免冲突。

ScholarFlow 后续可以接：

- Zotero MCP：读用户文献库。
- GitHub MCP：读论文代码仓库。
- filesystem MCP：访问本地论文和实验输出。
- database MCP：访问项目数据库。
- Hugging Face MCP：查模型和数据集。

MCP 不是 MVP 必需，但架构上应该预留。

## 3. ScholarFlow 应该如何借鉴 Claude Code

### 3.1 不要只做聊天框

Claude Code 的强点不是聊天，而是用户能看到：

- Agent 正在做什么。
- 调用了什么工具。
- 工具返回了什么。
- 哪些操作需要确认。
- 最终改了什么。

ScholarFlow 的前端也应该这样：

```text
左栏：项目导航
中栏：Agent 工作流和执行轨迹
右栏：Artifact 预览
```

### 3.2 前端工作台设计

推荐三栏结构：

```text
┌──────────────────┬──────────────────────────┬──────────────────────┐
│ Project Navigator│ Agent Workspace           │ Artifact Preview     │
│                  │                          │                      │
│ - Projects       │ - User instruction        │ - Paper table         │
│ - Papers         │ - Plan checklist          │ - Deep paper card     │
│ - Ideas          │ - Tool timeline           │ - Gap board           │
│ - Experiments    │ - Permission gates        │ - Experiment plan     │
└──────────────────┴──────────────────────────┴──────────────────────┘
```

中栏不是普通 chat，而是 Claude Code 式执行面板：

- 当前计划。
- 正在执行的步骤。
- 工具调用 timeline。
- 模型成本。
- 当前上下文状态。
- 可中断按钮。
- 可继续按钮。
- 人工确认卡片。

右栏展示 artifact：

- 论文表格。
- deep paper card。
- gap board。
- novelty validation report。
- experiment plan。
- writing draft。

### 3.3 ScholarFlow 的 Agent Loop

推荐第一版 Agent Loop：

```text
UserInstruction
  -> Orchestrator 制定 Plan
  -> 前端显示 Plan，等待用户确认
  -> 执行 Step 1: search_papers
  -> 保存 PaperTable artifact
  -> 执行 Step 2: rank_papers
  -> 用户选择核心论文
  -> 执行 Step 3: generate_paper_card
  -> 保存 PaperCard artifact
  -> 执行 Step 4: generate_gap_board
  -> 执行 Step 5: validate_idea
  -> 执行 Step 6: generate_experiment_plan
  -> 保存 ResearchSession
```

每一步都是可观察、可暂停、可回滚、可版本化的。

### 3.4 工具调用应在前端可见

例如 Literature Agent 检索论文时，前端不要只显示“正在检索”。

应该显示：

```text
Tool: search_arxiv
Query: "vision language model hallucination evaluation"
Result: 50 papers
Filtered: 18 papers after year/code/venue criteria

Tool: search_semantic_scholar
Query: "object hallucination VLM benchmark"
Result: 72 papers
Filtered: 21 papers
```

这样用户能判断 Agent 是否查偏了。

### 3.5 Artifact diff

Claude Code 编辑代码后显示 diff。ScholarFlow 更新研究资产也要显示 diff。

例如：

```text
Gap Board v1 -> v2
+ 新增 gap: evidence faithfulness in multi-image VQA
- 删除 weak gap: adding more benchmarks
~ 修改 novelty risk: medium -> high
```

这会让用户把关科研质量，而不是被动接受答案。

## 4. ScholarFlow 第一版工程设计

### 4.1 服务结构

```text
scholarflow/
├── apps/
│   ├── web/                 # React + Vite
│   └── cli/                 # Node.js CLI
├── services/
│   └── api/                 # Python FastAPI
├── packages/
│   ├── agent-core/          # Agent loop, tool registry, provider abstraction
│   ├── research-tools/      # paper/search/pdf/github tools
│   └── schemas/             # shared artifact schemas
└── data/
    └── examples/
```

### 4.2 核心后端模块

```text
AgentOrchestrator
├── ModelProvider
│   ├── DeepSeekProvider
│   ├── OpenAIProvider
│   └── OpenRouterProvider
├── ToolRegistry
│   ├── search_papers
│   ├── fetch_paper
│   ├── parse_pdf
│   ├── generate_paper_card
│   ├── search_similar_work
│   └── update_artifact
├── PermissionManager
├── ArtifactStore
├── MemoryStore
└── SessionStore
```

### 4.3 数据对象

```text
ResearchProject
ResearchSession
ToolCall
ToolResult
Artifact
Paper
PaperCard
GapBoard
IdeaValidationReport
ExperimentPlan
MemoryEntry
```

### 4.4 前端关键组件

```text
ProjectSidebar
AgentCommandBox
PlanChecklist
ToolTimeline
PermissionPrompt
ArtifactPreview
ArtifactDiff
ModelCostBadge
SessionMemoryPanel
```

这些组件对应 Claude Code 的 CLI 交互，只是转成科研工作台 UI。

## 5. 对 ScholarFlow 的关键启发

1. **Agent 的核心不是回答，而是循环执行**
   模型要能调用工具、看结果、再决定下一步。

2. **所有输出都应该成为 artifact**
   论文表、paper card、gap board、实验计划都应保存和版本化。

3. **用户要看到 Agent 的中间过程**
   科研判断需要把关，不能只给最终答案。

4. **Plan-first 很重要**
   长任务先计划、后执行，避免检索方向跑偏。

5. **权限系统不只是安全，也是成本控制**
   强模型调用、批量 PDF 下载、覆盖产物都要确认。

6. **上下文不能靠硬塞**
   论文全文、检索结果、代码仓库必须存储在外部，模型按需读取。

7. **技能系统可以成为产品壁垒**
   你的 12 步论文分析协议、novelty check、反例设计都应做成技能。

8. **多 Agent 要按任务拆，而不是堆模型**
   每个科研 Agent 都应该有明确角色、工具权限和输出 schema。

## 6. 需要你把关的地方

这个项目能帮我们理解 Claude Code 的工程骨架，但 ScholarFlow 的科研质量还需要你把关：

1. **Research Plan Mode 的默认流程**
   你要判断一条科研任务在执行前应该先展示哪些计划。

2. **Deep Paper Card 的质量标准**
   尤其是作者思考路径、最脆弱假设、反例设计和非增量 follow-up idea。

3. **工具调用可视化的颗粒度**
   前端到底显示多少检索 query、筛选原因、模型推理过程、成本信息。

4. **权限确认策略**
   哪些操作必须用户确认，哪些操作可以自动执行。

5. **科研 Agent 拆分**
   是先做 4 个 Agent，还是一步到位做 8 个 Agent。建议 MVP 先做 Orchestrator、Literature、Reading、Gap/Novelty、Experiment。

6. **Artifact 审阅方式**
   你要决定用户如何修改或否决 Agent 生成的 gap、idea 和实验计划。

## 7. 推荐迁移结论

ScholarFlow 应该借鉴 Claude Code 的“Agent 操作系统”思路，而不是复制它的代码编辑器定位。

具体来说：

- 用 Claude Code 的 Agent Loop 做 ScholarFlow 的执行内核。
- 用 Claude Code 的 Plan Mode 做 Research Plan Mode。
- 用 Claude Code 的 Tool Timeline 做科研工具调用轨迹。
- 用 Claude Code 的 diff 思路做 artifact diff。
- 用 Claude Code 的 Memory/Skills 做科研记忆和论文分析协议。
- 用 Claude Code 的 Sub-Agent 做 Literature / Reading / Skeptic / Experiment 多 Agent。
- 用 Claude Code 的 MCP 思路预留 Zotero、GitHub、Hugging Face 接入。

最终产品应该是：

> Claude Code for AI Research Workflow, not for editing code but for turning ambiguous research goals into traceable, evidence-grounded research artifacts.

