# ScholarFlow 分阶段实现计划

更新时间：2026-06-30

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

目标：实现本地启动和工作区管理。

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
- `OpenRouterProvider`，默认使用 `minimax/minimax-m2.5` OpenRouter 模型配置。
- 可选 `DeepSeekProvider` fallback。
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

- 本阶段不做批量精读；方向级多论文精读作为后续独立阶段处理。
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

## Phase 10: 方向级三轮论文精读

目标：根据用户给出的研究方向，每轮筛选并精读近三年高相关论文 10 篇，最多三轮累计 30 篇。

当前状态：complete。

交付物：

- Direction Review API。
- Direction Review React 页面。
- 每轮 10 篇论文卡片。
- 每篇论文保存：
  - 摘要中文内容
  - 12 条精读协议内容
  - 最脆弱假设
  - 一周最小复现实验
  - 反例设计
  - follow-up idea
- 每轮方向级总结。
- 用户本人最值得精读的 3 篇论文推荐。

验收标准：

- 摘要中文内容和 12 条精读内容不直接铺在论文列表里。
- 用户点击论文卡片后才能查看该论文详情。
- 第 2、3 轮会避开已读论文，并用累计阅读数量生成方向理解。
- 顶会/顶刊优先作为检索排序信号，但不伪造 venue 结论。

当前边界：

- 仍以 arXiv/OpenAlex 元数据和摘要为主要输入。
- 尚未实现 PDF 全文批量下载、解析和逐段证据引用。
- 顶会/顶刊过滤是启发式 venue/source 信号，需要后续接入更严格的 venue metadata。

## Phase 11: Paper Memory Bank

目标：让系统长期记住方向精读生成的 30 篇论文结构化结果，并在用户后续提问时按相关性检索 3-8 篇论文后回答。

当前状态：complete。

交付物：

- `paper_memories` 数据表。
- `direction_memories` 数据表。
- Paper Memory Query API。
- Paper Memory React 页面。
- 方向精读完成后自动写入 memory bank。
- 支持从旧的 direction review artifact 回填 memory。
- 每次问答保存 memory-grounded answer artifact。

验收标准：

- 不依赖聊天上下文保存 30 篇论文。
- 用户提问时检索 3-8 篇相关论文记忆。
- 回答中保留命中论文、分数、片段、最脆弱假设、一周验证和反例设计。
- Direction Memory 说明累计覆盖论文数量和轮次。

当前边界：

- 当前检索是结构化关键词排序，不是 embedding 向量检索。
- Paper Memory 来自摘要和 12 条规则卡片，不等同于全文证据。
- 正式写作和引用前仍需要回到原文核查。

## Phase 13: BaselineMap 与 Research Sight 科研审美层

目标：让方向精读不只总结论文，还能基于 baseline 背景判断“为什么好”“为什么不好”和“有什么更好角度”。

当前状态：complete for heuristic first version。

交付物：

- `BaselineMap` 数据结构。
- `ResearchSight` 数据结构。
- Baseline Curator 启发式模块：
  - 经典 baseline
  - 近三年强 baseline
  - 异质范式论文
  - 常见 benchmark
  - 评价风险
  - 开放问题
- Research Sight 生成模块：
  - 动机锋利度
  - 解法优雅性
  - 评估真实性
  - 范式启发性
  - 为什么好
  - 为什么不好
  - 更好角度
  - baseline 对比
  - 下一步 proposal
- Direction Review API 接入。
- Paper Memory Bank 接入。
- 方向精读 UI 增加 BaselineMap。
- 论文详情 UI 增加 ResearchSight。

验收标准：

- 每轮方向精读先基于候选池生成 BaselineMap，再生成 10 张论文卡片。
- 每张论文卡片包含 ResearchSight，而不是只包含 12 条规则精读。
- Paper Memory 能保存 ResearchSight，并在后续问答中检索“审美批判”和“更好角度”。
- Direction Memory 能保存 BaselineMap 线索。
- 列表页不直接铺开长文本，用户点击论文卡片后查看细节。

当前边界：

- BaselineMap 当前来自检索候选池的启发式分类，不是严格 citation graph。
- ResearchSight 当前为 deterministic rule-based generation，后续可替换为 OpenRouter 多角色 Agent。
- 尚未接入 Best Paper / Meta Review RAG。
- 尚未做全文 PDF 证据级引用，因此批判结论仍需用户回到原论文核查。

## Phase 14: Evidence-Grounded Sight 证据约束层

目标：让 ScholarFlow 的“科研审美评价”不再像无依据定论，而是明确展示每个判断基于什么证据、置信度多高、还缺什么证据。

当前状态：complete for metadata/abstract/paper-card evidence packs。

交付物：

- `EvidenceSnippet` 数据结构。
- `EvidencePack` 数据结构。
- BaselineReference 增加：
  - evidence snippets
  - confidence
  - evidence gap
- BaselineMap 增加 evidence summary。
- ResearchSight 增加：
  - evidence level
  - confidence
  - supporting snippets
  - missing evidence
  - grounding summary
- Direction Review UI 增加证据等级和缺失证据展示。
- Paper Memory UI 增加命中论文的 EvidencePack 摘要。

验收标准：

- 每个 baseline 参照都显示置信度和证据缺口。
- 每篇论文的 ResearchSight 都显示证据等级、证据片段和缺失证据。
- 旧 memory / 旧 artifact 没有 evidence 字段时仍能被 API 兼容读取。
- 证据描述明确区分 metadata、abstract、generated paper card 和缺失的全文证据。

当前边界：

- EvidencePack 当前来自 metadata、abstract 和 ScholarFlow 生成的 paper card。
- 证据片段不是 PDF 原文逐段引用。
- 尚未接入 citation graph、venue verification、代码仓库证据或 Best Paper meta-review RAG。
- 批判性结论仍需用户回到原论文核查后才能用于正式写作。

## Phase 15: 科研可信度与产品体验加固

目标：先提高系统判断的可信度，再提高产品体验。重点是减少模板化输出，让 ScholarFlow 明确说明“基于什么证据判断、缺什么证据、为什么命中这篇论文”。

当前状态：in progress。

### Phase 15.1: Paper Memory 检索质量

当前状态：complete。

交付物：

- 新增 `text_utils.py`，统一提供 `extract_terms()`、`score_term_overlap()`。
- 英文 token 至少 3 个字符，过滤常见 stopwords。
- 匹配时使用词边界，避免 `text.count(term)` 造成 `in`、`on`、`at`、`te` 等噪声命中。
- 加入领域短语白名单，例如 evidence faithfulness、visual grounding、object hallucination、counterexample evaluation。
- `PaperMemoryHit.score` 拆成 title / keyword / section / priority 分数。
- Paper Memory UI 显示命中分数来源。

验收标准：

- Memory summary 关键词应接近 hallucination、evidence、faithfulness、grounding、benchmark，而不是碎片字符。
- Paper Memory 命中能解释为什么相关。

### Phase 15.2: PaperSignals 与证据驱动 Paper Card

当前状态：complete for abstract/metadata/pasted-text signals。

交付物：

- 新增 `PaperSignals` 数据结构：
  - task
  - method
  - dataset
  - metric
  - claim
  - limitation
  - contribution type
  - missing signals
- Deep Paper Card 先抽取 signals，再生成 12 个 section。
- 方法、实验和最小复现段落绑定具体 claim / dataset / metric。
- 如果方法或实验信息缺失，明确写“当前证据不足”，不补写泛泛解释。
- survey / review 论文不再被包装成可复现实验论文。
- Direction Review 和单篇 Paper Card API 返回 signals。
- 前端论文详情页显示 Paper Signals。

验收标准：

- Paper Card 能说明“这篇论文提供了什么证据，缺什么证据”。
- minimal reproduction 必须绑定具体 claim / dataset / metric；缺失时降级为“需要补充 PDF/实验细节”。
- 旧 artifact / 旧数据库记录没有 signals 时不影响读取。

边界：

- PaperSignals 当前为启发式抽取，来源于 title、abstract 和用户粘贴的 `paper_text`。
- 尚未做 PDF 结构化解析、表格抽取或实验章节定位。

### Phase 15.3: ResearchSight 类型化与证据锚定

当前状态：complete for signal-aware deterministic ResearchSight。

交付物：

- `build_research_sight()` 接收 `PaperSignals`。
- ResearchSight 按论文类型生成不同评价逻辑：
  - benchmark paper：检查数据构造、负样本、metric 是否能暴露失败模式。
  - method paper：检查是否改变核心机制，还是 prompt / decoding / scale trick。
  - survey paper：不再按复现实验评价，只评价文献图谱价值、覆盖范围和分类轴。
  - system paper：检查 workflow 状态、工具调用、artifact 和失败恢复。
- 新增 `ResearchSightJudgment`：
  - field
  - evidence_snippet_id
  - confidence
  - rationale
- 每条 ResearchSight 判断都有结构化证据锚点。
- Direction Review 对同一轮 10 篇论文的 `why_good` 做重复度检查；相似度过高时用 PaperSignals 重写为更具体评价。
- 前端论文详情页展示每条 critique 的 evidence snippet id、confidence 和 rationale。

验收标准：

- benchmark / method / survey 类型论文的 ResearchSight 不再使用同一套批判模板。
- 每条核心 critique 都能看到证据片段 id 和置信度。
- survey 不再被建议为一周模型复现实验 anchor。
- 旧 memory / 旧 artifact 没有 `critique_evidence` 时仍能被 API 兼容读取。

边界：

- ResearchSight 仍是 deterministic heuristic，不是多角色 LLM 审稿。
- evidence_snippet_id 指向 ScholarFlow 当前的 EvidencePack，不是 PDF 原文段落定位。
- 重复度校正只在当前方向精读一轮内生效，尚未做跨轮/跨项目风格去重。

### Phase 15.4: Experiment Plan Anchor Selection

当前状态：complete for stored paper cards and paper metadata。

目标：避免 Experiment Plan 把 survey / review 当成 Day 1 复现实验切口，确保一周实验计划指向真正可实验的论文。

交付物：

- 新增 `select_experiment_anchor(papers, paper_cards)`。
- 从 `paper_cards` 读取时 left join `papers`，让 decision 模块能看到论文标题、类型、摘要、venue、priority 等 metadata。
- 排除 title / type / card content 含 survey、review、overview、taxonomy、综述、调研、文献图谱的论文。
- 排除 Paper Card 已明确写“需要补充 PDF/实验细节”或“不应作为一周复现实验 anchor”的论文。
- 优先选择同时包含 claim、dataset、metric 的论文；也支持 benchmark + baseline 信号作为候选。
- Experiment Plan 的 Day 1 明确指向 anchor paper。
- 没有合格 anchor 时，Experiment Plan 输出“缺少可复现 anchor”，不硬生成 7 天复现实验。

验收标准：

- Experiment Plan 的 Day 1 必须指向一篇可实验论文，而不是综述。
- 只有 survey/review 命中时，系统要求补充非 survey 的方法或 benchmark 论文。
- anchor 必须能解释为什么被选中，例如包含 claim、dataset、metric、baseline 或 benchmark 信号。

边界：

- anchor 解析当前基于 paper metadata、Paper Card 的 `minimal_reproduction` 和 section 文本。
- 尚未解析 PDF 实验表格，也未自动运行 benchmark。
- 如果历史 Paper Card 缺少完整 minimal reproduction，系统会保守降级为缺少 anchor。

### Phase 15.5: Real Agent Tool Chain

当前状态：complete for registered Web/API tools。

目标：让 Agent Loop 不再只是 mock demo，而是按 plan 顺序执行 ScholarFlow 已有真实科研工具。

交付物：

- OpenRouter planning prompt 的 allowed tools 改为：
  - `literature_search`
  - `direction_review`
  - `research_memory_query`
  - `research_decision`
  - `save_artifact`
  - `update_timeline`
- local fallback plan 默认生成真实工具链，而不是 mock paper table。
- `execute_agent_run()` 按 `plan["steps"]` 顺序逐步执行已注册工具，不再硬编码 `search_mock_papers -> save_artifact -> update_timeline`。
- Tool Registry 新增真实工具：
  - `literature_search`：检索 arXiv / OpenAlex 并保存 paper table。
  - `direction_review`：生成 BaselineMap、Paper Card、ResearchSight、Paper Memory。
  - `research_memory_query`：检索 Paper Memory Bank 并保存 memory-grounded answer。
  - `research_decision`：生成 Gap Board、Idea Validation、Experiment Plan。
- `search_mock_papers` 保留为 Demo Mode 工具，但默认 plan 不再使用。
- Agent Run 最终 artifact 聚合 papers、tool outputs 和中间 artifacts。
- Web UI 在 Agent Plan 面板显示 `Real Tools` / `Demo Mode` badge。

验收标准：

- 默认 local fallback plan 不包含 `search_mock_papers`。
- Agent 执行逻辑来自 plan steps，而不是固定 mock 工具列表。
- Mock 工具仍可用于离线演示，并在 UI 标记为 Demo Mode。

边界：

- 真实工具仍是 Web/API 内部同步执行，尚未实现后台队列、取消、重试和流式进度。
- `direction_review` 工具会触发真实文献检索，依赖外部 arXiv / OpenAlex 可用性。
- Tool failure 目前仍由 API 异常中断，下一步可增加 step-level failed status 和恢复策略。

## 阶段推进规则

每个阶段完成时必须回答：

1. 本阶段交付物是否完成？
2. 是否有测试或手动验证？
3. 是否有安全或隐私风险？
4. 是否有文档同步？
5. 是否进入下一阶段？

如果任一问题答案不清楚，不进入下一阶段。
