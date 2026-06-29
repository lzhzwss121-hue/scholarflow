from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class GapDecision:
    id: str
    title: str
    kind: str
    evidence: str
    weakness: str
    opportunity: str
    novelty_risk: str
    feasibility: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass
class IdeaValidation:
    idea: str
    why_not_incremental: str
    difference_from_existing_work: str
    novelty_risk: str
    feasibility: str
    key_risks: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExperimentPlan:
    claim: str
    dataset: str
    baseline: str
    metrics: list[str]
    ablations: list[str]
    resources: str
    timeline: list[str]
    success_criterion: str
    failure_criterion: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ResearchDecisionBundle:
    project_title: str
    gaps: list[GapDecision]
    validation: IdeaValidation
    experiment: ExperimentPlan

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_title": self.project_title,
            "gaps": [gap.to_dict() for gap in self.gaps],
            "validation": self.validation.to_dict(),
            "experiment": self.experiment.to_dict(),
        }


def generate_research_decisions(
    project: dict[str, Any],
    papers: list[dict[str, Any]],
    paper_cards: list[dict[str, Any]],
    goal: str = "",
) -> ResearchDecisionBundle:
    focus = infer_focus(project, papers, paper_cards, goal)
    top_papers = ", ".join(paper.get("title", "") for paper in papers[:3] if paper.get("title")) or "当前 paper table"
    weakest = first_nonempty([card.get("weakest_assumption", "") for card in paper_cards])
    minimal = first_nonempty([card.get("minimal_reproduction", "") for card in paper_cards])

    gaps = [
        GapDecision(
            id="gap_evidence_mismatch",
            title="答案正确但证据链错误",
            kind="true_gap",
            evidence=f"来自 paper table / paper card 的线索：{top_papers}。{weakest or '多篇工作关注最终指标，但证据一致性仍缺少稳定诊断。'}",
            weakness="只看最终答案或平均分，会把真实视觉理解、语言先验和 benchmark shortcut 混在一起。",
            opportunity="构建 evidence-aware split，把 answer accuracy、evidence consistency、counterexample pass rate 分开评价。",
            novelty_risk="medium",
            feasibility="one-week",
        ),
        GapDecision(
            id="gap_counterexample_naturalness",
            title="反例不够自然，难以代表真实用户失败",
            kind="engineering_gap",
            evidence="现有 hallucination / grounding 评测常依赖人工构造负样本或模板化冲突样本。",
            weakness="如果反例痕迹过强，模型失败可能来自数据风格而不是真实视觉推理缺陷。",
            opportunity="从真实图像和真实问题出发生成轻微属性冲突、遮挡和罕见物体组合，再人工复核。",
            novelty_risk="low",
            feasibility="one-week",
        ),
        GapDecision(
            id="gap_benchmark_overclaim",
            title="把 benchmark 分数提升误认为能力提升",
            kind="pseudo_gap",
            evidence="如果一个 idea 只是在现有 benchmark 上换 prompt、换 backbone 或调指标名称，它很可能只是局部工程优化。",
            weakness="这类 gap 难以证明新科学问题，只能证明某个配置更适合某个测试集。",
            opportunity="除非能定义新的失败模式和反例协议，否则不要把它作为核心研究贡献。",
            novelty_risk="high",
            feasibility="one-month",
        ),
    ]

    validation = IdeaValidation(
        idea=(
            f"围绕 `{focus}` 建立 evidence-aware counterexample evaluation："
            "先定义最脆弱失败模式，再设计能攻击该假设的样本和指标。"
        ),
        why_not_incremental=(
            "它不是只换模型、加模块或换数据集，而是改变研究入口：从优化平均分转为验证模型是否能通过针对性反例。"
        ),
        difference_from_existing_work=(
            "区别在于同时要求答案、视觉证据和反例鲁棒性三者一致；现有工作通常只覆盖其中一到两个层面。"
        ),
        novelty_risk="medium",
        feasibility="one-week",
        key_risks=[
            "人工证据标签可能主观，需双人复核或明确标注规则。",
            "反例生成可能引入模板痕迹，需要自然性检查。",
            "如果 baseline 本身无法回答原任务，实验会退化成能力筛选而不是证据诊断。",
        ],
    )

    experiment = ExperimentPlan(
        claim="VLM 在答案正确时仍可能依赖错误或不足的视觉证据，平均准确率会掩盖该失败模式。",
        dataset="50-100 条 VQA / image-text 样本；优先选包含属性、计数、遮挡、罕见物体和上下文冲突的样本。",
        baseline="一个公开强 VLM baseline + 一个轻量 baseline；记录 prompt、temperature、模型版本和失败样本。",
        metrics=[
            "answer accuracy",
            "evidence consistency",
            "counterexample pass rate",
            "failure-mode frequency by slice",
        ],
        ablations=[
            "去掉图像或遮挡关键区域，观察答案是否保持不变。",
            "替换属性词或物体上下文，观察 hallucination 是否增加。",
            "按物体罕见度、遮挡程度、问题类型分层。",
        ],
        resources="单卡推理或 API 推理；人工标注约 4-6 小时；总周期 7 天以内。",
        timeline=[
            "Day 1: 定义失败模式、样本字段和标注规则。",
            "Day 2-3: 收集 50-100 条样本并跑 baseline。",
            "Day 4: 标注 evidence consistency 和 failure slices。",
            "Day 5: 构造 20 条 counterexamples。",
            "Day 6: 做 ablation 和错误分析。",
            "Day 7: 输出实验报告和下一步 thesis-scale 计划。",
        ],
        success_criterion="至少发现一个稳定样本簇：answer accuracy 高但 evidence consistency 明显低，并能用反例复现。",
        failure_criterion="失败只来自个别样本、标注争议或 prompt 不稳定，无法形成可复用 failure mode。",
    )

    if minimal:
        experiment.timeline[0] = f"Day 1: 复用 paper card 的最小复现切口：{minimal[:120]}"

    return ResearchDecisionBundle(
        project_title=project.get("title") or "ScholarFlow Project",
        gaps=gaps,
        validation=validation,
        experiment=experiment,
    )


def infer_focus(project: dict[str, Any], papers: list[dict[str, Any]], paper_cards: list[dict[str, Any]], goal: str) -> str:
    text = " ".join(
        [
            project.get("title", ""),
            project.get("keyword", ""),
            project.get("field", ""),
            goal,
            " ".join(paper.get("title", "") for paper in papers[:5]),
            " ".join(card.get("weakest_assumption", "") for card in paper_cards[:3]),
        ],
    ).lower()
    if "hallucination" in text or "vlm" in text or "vision-language" in text:
        return "VLM hallucination and evidence faithfulness"
    if "agent" in text or "workflow" in text:
        return "AI research workflow agent reliability"
    if "benchmark" in text or "evaluation" in text:
        return "benchmark reliability and hidden failure modes"
    return project.get("field") or project.get("keyword") or "AI research reliability"


def render_gap_board_markdown(bundle: ResearchDecisionBundle) -> str:
    blocks = ["# Gap Board", f"Project: {bundle.project_title}"]
    for gap in bundle.gaps:
        blocks.append(
            "\n".join(
                [
                    f"## {gap.title}",
                    f"- Type: {gap.kind}",
                    f"- Novelty risk: {gap.novelty_risk}",
                    f"- Feasibility: {gap.feasibility}",
                    f"- Evidence: {gap.evidence}",
                    f"- Weakness: {gap.weakness}",
                    f"- Opportunity: {gap.opportunity}",
                ],
            ),
        )
    return "\n\n".join(blocks)


def render_validation_markdown(bundle: ResearchDecisionBundle) -> str:
    report = bundle.validation
    return "\n\n".join(
        [
            "# Idea Validation Report",
            f"Project: {bundle.project_title}",
            f"## Idea\n{report.idea}",
            f"## Why Not Incremental\n{report.why_not_incremental}",
            f"## Difference From Existing Work\n{report.difference_from_existing_work}",
            f"## Novelty Risk\n{report.novelty_risk}",
            f"## Feasibility\n{report.feasibility}",
            "## Key Risks\n" + "\n".join(f"- {risk}" for risk in report.key_risks),
        ],
    )


def render_experiment_markdown(bundle: ResearchDecisionBundle) -> str:
    plan = bundle.experiment
    return "\n\n".join(
        [
            "# Experiment Plan",
            f"Project: {bundle.project_title}",
            f"## Claim\n{plan.claim}",
            f"## Dataset\n{plan.dataset}",
            f"## Baseline\n{plan.baseline}",
            "## Metrics\n" + "\n".join(f"- {metric}" for metric in plan.metrics),
            "## Ablations\n" + "\n".join(f"- {ablation}" for ablation in plan.ablations),
            f"## Resources\n{plan.resources}",
            "## Timeline\n" + "\n".join(f"- {step}" for step in plan.timeline),
            f"## Success Criterion\n{plan.success_criterion}",
            f"## Failure Criterion\n{plan.failure_criterion}",
        ],
    )


def render_decision_json(bundle: ResearchDecisionBundle) -> str:
    return json.dumps(bundle.to_dict(), ensure_ascii=False, indent=2)


def first_nonempty(values: list[str]) -> str:
    for value in values:
        if value:
            return value
    return ""
