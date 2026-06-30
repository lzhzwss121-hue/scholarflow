export type ViewId =
  | "dashboard"
  | "new-project"
  | "paper-table"
  | "direction-review"
  | "paper-memory"
  | "paper-reader"
  | "gap-board"
  | "experiment-planner";

export type PlanStatus = "done" | "active" | "queued" | "blocked";

export interface NavItem {
  id: ViewId;
  label: string;
  count?: number;
}

export interface PlanStep {
  id: string;
  title: string;
  detail: string;
  status: PlanStatus;
}

export interface TimelineEvent {
  time: string;
  tool: string;
  status: "done" | "running" | "queued";
  summary: string;
}

export interface PaperRow {
  id: string;
  title: string;
  authors: string;
  abstract: string;
  year: string;
  type: string;
  venue: string;
  source: string;
  url: string;
  relation: string;
  priority: "High" | "Medium" | "Watch";
  code: string;
  relevanceScore: number;
}

export interface GapItem {
  title: string;
  weakness: string;
  opportunity: string;
  risk: "high" | "medium" | "low";
}

export interface ExperimentItem {
  week: string;
  goal: string;
  deliverable: string;
  cost: string;
}

export interface ArtifactContent {
  title: string;
  markdown: string;
  json: string;
  diff: string;
}

export const navItems: NavItem[] = [
  { id: "dashboard", label: "项目总览" },
  { id: "new-project", label: "新建项目" },
  { id: "paper-table", label: "文献检索" },
  { id: "direction-review", label: "方向精读" },
  { id: "paper-memory", label: "论文记忆" },
  { id: "paper-reader", label: "单篇精读" },
  { id: "gap-board", label: "Gap 分析" },
  { id: "experiment-planner", label: "实验计划" },
];

export const planSteps: PlanStep[] = [
  {
    id: "intent",
    title: "方向理解",
    detail: "将用户输入的研究方向拆成任务、方法、数据集、评价指标和潜在失败模式。",
    status: "done",
  },
  {
    id: "retrieval",
    title: "文献检索",
    detail: "生成 6 组 query，按近两年、代码可用性和任务相关性筛选。",
    status: "done",
  },
  {
    id: "reading",
    title: "Deep Paper Card",
    detail: "对优先级最高的论文重建作者思路、最脆弱假设和一周复现实验。",
    status: "active",
  },
  {
    id: "gap",
    title: "Gap Analysis",
    detail: "从 evaluation blind spot 和 evidence requirement 中提炼可验证 gap。",
    status: "queued",
  },
  {
    id: "experiment",
    title: "Experiment Plan",
    detail: "输出最小复现、反例设计、baseline、指标和算力预算。",
    status: "queued",
  },
];

export const timelineEvents: TimelineEvent[] = [
  {
    time: "13:42",
    tool: "query.expand",
    status: "done",
    summary: "根据用户研究方向生成多组检索式。",
  },
  {
    time: "13:45",
    tool: "paper.rank",
    status: "done",
    summary: "按任务相关性、年份、代码可用性重排 18 篇候选论文。",
  },
  {
    time: "13:49",
    tool: "paper.card",
    status: "running",
    summary: "正在生成第一篇论文的 12 段 deep paper card。",
  },
  {
    time: "Next",
    tool: "gap.skeptic",
    status: "queued",
    summary: "等待 paper card 完成后执行反例和脆弱假设分析。",
  },
];

export const papers: PaperRow[] = [
  {
    id: "paper_research_agent_workflow",
    title: "Synthetic Example: Research Workflow Agents for Literature Review",
    authors: "unknown",
    abstract: "Synthetic example showing how an agent organizes literature review workflows.",
    year: "2025",
    type: "System",
    venue: "Demo",
    source: "seed",
    url: "",
    relation: "展示从方向到论文表的工作流",
    priority: "High",
    code: "demo",
    relevanceScore: 1.5,
  },
  {
    id: "paper_memory_retrieval",
    title: "Synthetic Example: Memory-Augmented Paper Reading",
    authors: "unknown",
    abstract: "Synthetic example showing how structured paper memory supports follow-up questions.",
    year: "2025",
    type: "Method",
    venue: "Demo",
    source: "seed",
    url: "",
    relation: "展示 Paper Memory 如何支持后续问答",
    priority: "High",
    code: "demo",
    relevanceScore: 1.4,
  },
  {
    id: "paper_gap_analysis_protocol",
    title: "Synthetic Example: Evidence-Bounded Gap Analysis",
    authors: "unknown",
    abstract: "Synthetic example showing how paper evidence becomes research gaps.",
    year: "2024",
    type: "Protocol",
    venue: "Demo",
    source: "seed",
    url: "",
    relation: "展示如何从论文证据生成研究 gap",
    priority: "High",
    code: "demo",
    relevanceScore: 1.3,
  },
  {
    id: "paper_experiment_anchor_selection",
    title: "Synthetic Example: Selecting Reproducible Experiment Anchors",
    authors: "unknown",
    abstract: "Synthetic example showing how to choose a reproducible experiment anchor.",
    year: "2026",
    type: "Guide",
    venue: "Demo",
    source: "seed",
    url: "",
    relation: "展示实验计划如何避免选择综述论文",
    priority: "Medium",
    code: "demo",
    relevanceScore: 0.9,
  },
];

export const gapItems: GapItem[] = [
  {
    title: "答案正确但证据错误",
    weakness: "多数 benchmark 只检查最终答案，弱化了视觉证据链。",
    opportunity: "设计证据边界清晰的评价协议，把结论、证据和失败模式分开检查。",
    risk: "high",
  },
  {
    title: "负样本过于人工",
    weakness: "反事实图像或错误描述常带有明显模板痕迹。",
    opportunity: "构造更接近真实用户输入的自然反例。",
    risk: "medium",
  },
  {
    title: "模型规模掩盖失败模式",
    weakness: "大模型在整体分数上更强，但局部证据错误不一定减少。",
    opportunity: "按 object rarity、occlusion、attribute conflict 分层分析。",
    risk: "medium",
  },
];

export const experiments: ExperimentItem[] = [
  {
    week: "Day 1-2",
    goal: "复现最小评测集",
    deliverable: "100 条 VQA 样本、人工证据标签、baseline 输出表",
    cost: "CPU + 单卡推理",
  },
  {
    week: "Day 3-4",
    goal: "验证 evidence mismatch",
    deliverable: "答案准确率与证据一致性拆分指标",
    cost: "8-12 小时",
  },
  {
    week: "Day 5",
    goal: "构造反例",
    deliverable: "20 条属性冲突与遮挡样本",
    cost: "人工标注",
  },
  {
    week: "Day 6-7",
    goal: "写出最小实验报告",
    deliverable: "claim、实验、失败模式、下一步 idea",
    cost: "文档整理",
  },
];

export const artifacts: Record<ViewId, ArtifactContent> = {
  dashboard: {
    title: "research_overview.md",
    markdown:
      "# AI 研究方向探索示例\n\n- 输入自己的研究方向\n- 检索近三年相关论文\n- 生成方向精读、Paper Memory、Gap Board 和 Experiment Plan",
    json:
      '{\n  "project": "ai-research-direction-example",\n  "stage": "paper-card",\n  "papers": 0,\n  "gaps": 0\n}',
    diff:
      "+ Added user-defined research direction workflow\n+ Removed domain-specific default topic",
  },
  "new-project": {
    title: "project_brief.md",
    markdown:
      "# Project Brief\n\n关键词：等待用户输入\n\n目标：围绕用户自己的研究方向，找到可复现、可反驳、可扩展的研究切入点。",
    json:
      '{\n  "keyword": "",\n  "language": "zh-CN",\n  "workflow": "survey-to-experiment"\n}',
    diff:
      "+ Set default workflow to survey-to-experiment\n+ Added Chinese-first artifact policy",
  },
  "paper-table": {
    title: "paper_table.md",
    markdown:
      "| Paper | Year | Type | Priority |\n| --- | --- | --- | --- |\n| Synthetic Example: Research Workflow Agents | 2026 | System | High |\n| Synthetic Example: Memory-Augmented Paper Reading | 2025 | Method | High |",
    json:
      '{\n  "rows": 18,\n  "filters": ["recent", "code_available", "task_relevance"],\n  "top_priority": 3\n}',
    diff:
      "+ Added code availability column\n+ Added relation-to-user-direction column",
  },
  "direction-review": {
    title: "direction_review_round_1.md",
    markdown:
      "# Direction Review Round 1\n\n方向：用户输入的研究方向\n\n- 近三年 10 篇高相关论文\n- 每篇保存摘要中文翻译与 12 条精读内容\n- 推荐 3 篇用户亲自精读\n- 生成方向级总结",
    json:
      '{\n  "round": 1,\n  "papers": 10,\n  "max_rounds": 3,\n  "total_limit": 30\n}',
    diff:
      "+ Added ten-paper direction review workflow\n+ Added interactive paper cards",
  },
  "paper-memory": {
    title: "research_memory_answer.md",
    markdown:
      "# Research Memory Answer\n\n基于 Paper Memory Bank 检索 3-8 篇相关论文后回答用户问题。\n\n- 每篇论文来自方向精读的结构化 Paper Card\n- 每 10 篇保留 round summary\n- 累计 30 篇形成 direction memory",
    json:
      '{\n  "top_k": 5,\n  "total_memories": 30,\n  "retrieval": "keyword-ranked paper memory"\n}',
    diff:
      "+ Added paper memory retrieval\n+ Added memory-grounded answer artifact",
  },
  "paper-reader": {
    title: "paper_card.md",
    markdown:
      "# Deep Paper Card\n\n1. 研究问题：论文解决了什么具体科研问题。\n2. 作者思路：从已有失败模式和相关工作重建 idea 来源。\n3. 最脆弱假设：指出方法或实验最容易被反例攻击的前提。",
    json:
      '{\n  "sections": 12,\n  "weakest_assumption": "to be extracted from the selected paper",\n  "minimal_reproduction": "one-week claim test"\n}',
    diff:
      "+ Added reconstructed author reasoning path\n+ Added counterexample design section",
  },
  "gap-board": {
    title: "gap_board.md",
    markdown:
      "# Gap Board\n\n- Gap 1: 答案正确但证据错误\n- Gap 2: 负样本过于人工\n- Gap 3: 模型规模掩盖失败模式",
    json:
      '{\n  "gaps": 3,\n  "primary_gap": "answer-correct-evidence-wrong",\n  "risk": "high"\n}',
    diff:
      "+ Promoted evidence mismatch to primary gap\n+ Added attackable assumption field",
  },
  "experiment-planner": {
    title: "experiment_plan.md",
    markdown:
      "# One-Week Experiment Plan\n\n目标：验证答案准确率和证据一致性是否出现分离。\n\n成功判据：baseline 出现高 answer accuracy 但低 evidence consistency 的稳定样本簇。",
    json:
      '{\n  "duration": "7 days",\n  "claim": "answer accuracy can hide evidence mismatch",\n  "compute": "single GPU inference"\n}',
    diff:
      "+ Added failure criterion\n+ Added compute budget and baseline scope",
  },
};
