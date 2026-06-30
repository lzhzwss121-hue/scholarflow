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
  { id: "dashboard", label: "Dashboard" },
  { id: "new-project", label: "New Project" },
  { id: "paper-table", label: "Paper Table", count: 18 },
  { id: "direction-review", label: "方向精读", count: 10 },
  { id: "paper-memory", label: "论文记忆", count: 30 },
  { id: "paper-reader", label: "Paper Reader", count: 3 },
  { id: "gap-board", label: "Gap Board", count: 5 },
  { id: "experiment-planner", label: "Experiment Planner", count: 2 },
];

export const planSteps: PlanStep[] = [
  {
    id: "intent",
    title: "方向理解",
    detail: "将 VLM hallucination benchmark 拆成 visual grounding、faithfulness、benchmark bias 三个子问题。",
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
    summary: "生成 VLM hallucination / visual grounding / faithfulness 相关检索式。",
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
    id: "paper_object_hallucination",
    title: "Evaluating Object Hallucination in Large Vision-Language Models",
    authors: "unknown",
    abstract: "Evaluates object hallucination in large vision-language models.",
    year: "2025",
    type: "Benchmark",
    venue: "arXiv",
    source: "seed",
    url: "",
    relation: "直接对应 hallucination evaluation",
    priority: "High",
    code: "available",
    relevanceScore: 1.5,
  },
  {
    id: "paper_faithful_vqa",
    title: "Faithful Visual Question Answering Requires Grounded Evidence",
    authors: "unknown",
    abstract: "Separates answer correctness from grounded visual evidence.",
    year: "2025",
    type: "Method",
    venue: "ACL",
    source: "seed",
    url: "",
    relation: "把答案正确性和证据一致性分开",
    priority: "High",
    code: "partial",
    relevanceScore: 1.4,
  },
  {
    id: "paper_benchmark_bias",
    title: "Benchmark Bias in Multimodal Foundation Model Evaluation",
    authors: "unknown",
    abstract: "Analyzes benchmark shortcuts and distribution bias.",
    year: "2024",
    type: "Analysis",
    venue: "NeurIPS",
    source: "seed",
    url: "",
    relation: "解释评测集捷径和分布偏差",
    priority: "High",
    code: "available",
    relevanceScore: 1.3,
  },
  {
    id: "paper_trustworthy_vlm_survey",
    title: "A Survey of Trustworthy Vision-Language Models",
    authors: "unknown",
    abstract: "Surveys trustworthy vision-language model research.",
    year: "2026",
    type: "Survey",
    venue: "arXiv",
    source: "seed",
    url: "",
    relation: "补全研究图谱和术语",
    priority: "Medium",
    code: "none",
    relevanceScore: 0.9,
  },
];

export const gapItems: GapItem[] = [
  {
    title: "答案正确但证据错误",
    weakness: "多数 benchmark 只检查最终答案，弱化了视觉证据链。",
    opportunity: "设计 evidence-aware hallucination split，把答案、定位、解释分开评分。",
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
      "# VLM Hallucination Benchmark\n\n- 方向：trustworthy VLM evaluation\n- 当前阶段：Deep Paper Card\n- 下一步：Gap Analysis\n- 资产：18 papers, 3 paper cards, 5 gaps",
    json:
      '{\n  "project": "vlm-hallucination-benchmark",\n  "stage": "paper-card",\n  "papers": 18,\n  "gaps": 5\n}',
    diff:
      "+ Added benchmark bias as a first-class subtopic\n+ Added evidence faithfulness as the main evaluation lens",
  },
  "new-project": {
    title: "project_brief.md",
    markdown:
      "# Project Brief\n\n关键词：VLM hallucination benchmark\n\n目标：从评测缺陷出发，找到可复现、可反驳、可扩展的研究切入点。",
    json:
      '{\n  "keyword": "VLM hallucination benchmark",\n  "language": "zh-CN",\n  "workflow": "survey-to-experiment"\n}',
    diff:
      "+ Set default workflow to survey-to-experiment\n+ Added Chinese-first artifact policy",
  },
  "paper-table": {
    title: "paper_table.md",
    markdown:
      "| Paper | Year | Type | Priority |\n| --- | --- | --- | --- |\n| Evaluating Object Hallucination | 2025 | Benchmark | High |\n| Faithful VQA Requires Grounded Evidence | 2025 | Method | High |",
    json:
      '{\n  "rows": 18,\n  "filters": ["recent", "code_available", "task_relevance"],\n  "top_priority": 3\n}',
    diff:
      "+ Added code availability column\n+ Added relation-to-user-direction column",
  },
  "direction-review": {
    title: "direction_review_round_1.md",
    markdown:
      "# Direction Review Round 1\n\n方向：VLM hallucination benchmark\n\n- 近三年 10 篇高相关论文\n- 每篇保存摘要中文翻译与 12 条精读内容\n- 推荐 3 篇用户亲自精读\n- 生成方向级总结",
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
      "# Deep Paper Card\n\n1. 研究问题：VLM 在答案正确时仍可能使用错误视觉证据。\n2. 作者思路：从 benchmark shortcut 和 grounding failure 推导出 evidence-aware evaluation。\n3. 最脆弱假设：人工证据标签能代表真实视觉依据。",
    json:
      '{\n  "sections": 12,\n  "weakest_assumption": "evidence labels represent real visual grounding",\n  "minimal_reproduction": "one-week evidence mismatch test"\n}',
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
