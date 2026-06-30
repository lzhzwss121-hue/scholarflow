from __future__ import annotations

import json
import re
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
class ExperimentAnchor:
    paper_title: str
    paper_id: str
    card: dict[str, Any]
    paper: dict[str, Any]
    claim: str
    dataset: str
    baseline: str
    metrics: list[str]
    minimal_reproduction: str
    reason: str
    score: float

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
    anchor = select_experiment_anchor(papers, paper_cards)

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

    experiment = build_experiment_plan_from_anchor(anchor, focus)

    return ResearchDecisionBundle(
        project_title=project.get("title") or "ScholarFlow Project",
        gaps=gaps,
        validation=validation,
        experiment=experiment,
    )


def select_experiment_anchor(papers: list[dict[str, Any]], paper_cards: list[dict[str, Any]]) -> ExperimentAnchor | None:
    paper_by_id = {paper.get("id", ""): paper for paper in papers if paper.get("id")}
    candidates: list[ExperimentAnchor] = []
    for card in paper_cards:
        paper = paper_by_id.get(card.get("paper_id", "") or "", {})
        merged_paper = merge_card_paper(card, paper)
        if is_survey_like(merged_paper, card):
            continue
        anchor = build_experiment_anchor_candidate(merged_paper, card)
        if anchor and anchor.score >= 3.0:
            candidates.append(anchor)
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: item.score, reverse=True)[0]


def merge_card_paper(card: dict[str, Any], paper: dict[str, Any]) -> dict[str, Any]:
    merged = dict(paper)
    field_map = {
        "paper_title": "title",
        "paper_authors": "authors",
        "paper_abstract": "abstract",
        "paper_year": "year",
        "paper_type": "type",
        "paper_venue": "venue",
        "paper_source": "source",
        "paper_url": "url",
        "paper_relation": "relation",
        "paper_priority": "priority",
        "paper_code": "code",
        "paper_relevance_score": "relevance_score",
    }
    for card_key, paper_key in field_map.items():
        value = card.get(card_key)
        if value not in (None, ""):
            merged[paper_key] = value
    if card.get("paper_id") and not merged.get("id"):
        merged["id"] = card["paper_id"]
    return merged


def build_experiment_anchor_candidate(paper: dict[str, Any], card: dict[str, Any]) -> ExperimentAnchor | None:
    title = normalize_space(paper.get("title") or card.get("paper_title") or card.get("id") or "Untitled paper")
    minimal = normalize_space(card.get("minimal_reproduction", ""))
    if not minimal or is_invalid_minimal_reproduction(minimal):
        return None
    combined = normalize_space(
        " ".join(
            [
                title,
                paper.get("type", ""),
                paper.get("abstract", ""),
                card.get("weakest_assumption", ""),
                card.get("sections_json", ""),
                minimal,
            ],
        ),
    )
    claim = extract_anchor_claim(minimal, combined)
    dataset = extract_anchor_dataset(minimal, combined)
    metrics = extract_anchor_metrics(minimal, combined)
    baseline = extract_anchor_baseline(minimal, combined)
    score = 0.0
    reasons: list[str] = []

    if claim:
        score += 1.4
        reasons.append("包含可测试 claim")
    if dataset:
        score += 1.4
        reasons.append("包含 dataset/subset")
    if metrics:
        score += 1.4
        reasons.append("包含 metric")
    if baseline:
        score += 0.8
        reasons.append("包含 baseline")
    if has_benchmark_signal(combined):
        score += 0.6
        reasons.append("包含 benchmark 信号")
    if has_method_signal(combined):
        score += 0.4
        reasons.append("包含 method 信号")
    if normalize_space(paper.get("priority", "")).lower() == "high":
        score += 0.2
        reasons.append("High priority paper")

    if not ((claim and dataset and metrics) or (has_benchmark_signal(combined) and baseline)):
        return None
    return ExperimentAnchor(
        paper_title=title,
        paper_id=paper.get("id", "") or card.get("paper_id", "") or "",
        card=card,
        paper=paper,
        claim=claim or f"复核 `{title}` 的核心 benchmark claim",
        dataset=dataset or "论文 benchmark 中可抽样的 50-100 条样本",
        baseline=baseline or "一个公开强 baseline + 一个简单 baseline",
        metrics=metrics or ["论文主指标", "counterexample pass rate"],
        minimal_reproduction=minimal,
        reason="；".join(reasons),
        score=score,
    )


def build_experiment_plan_from_anchor(anchor: ExperimentAnchor | None, focus: str) -> ExperimentPlan:
    if anchor is None:
        return ExperimentPlan(
            claim="缺少可复现 anchor：当前 paper cards 中没有找到非 survey/review 且同时具备 claim、dataset、metric 或 benchmark+baseline 信号的论文。",
            dataset="暂不指定数据集。需要先补充至少一篇方法/benchmark 论文的 PDF 实验细节，或重新执行方向精读生成更完整 Paper Card。",
            baseline="暂不指定 baseline。原因是没有合格 anchor 时，强行选择 baseline 会变成泛泛实验计划。",
            metrics=["anchor availability", "claim/dataset/metric completeness", "paper type is not survey/review"],
            ablations=[
                "补充 PDF 后重新抽取 claim、dataset、metric。",
                "排除 title/type 含 survey、review、overview 的论文。",
                "优先选择 benchmark 或 method paper，而不是综述。",
            ],
            resources="先投入 30-60 分钟补全论文元数据或 PDF 实验段；暂不进入 7 天复现实验。",
            timeline=[
                "Day 1: 缺少可复现 anchor，先补充至少一篇非 survey/review 的方法或 benchmark 论文。",
                "Day 1: 检查该论文是否包含 claim、dataset、metric 和 baseline。",
                "Day 2+: 只有 anchor 合格后，才生成 7 天复现实验计划。",
            ],
            success_criterion="找到一篇可实验论文，其 Paper Card 明确包含 claim、dataset、metric 或 benchmark+baseline。",
            failure_criterion="继续只能命中 survey/review/overview，或 Paper Card 明确写着需要补充 PDF/实验细节。",
        )

    return ExperimentPlan(
        claim=f"Anchor paper: `{anchor.paper_title}`。待验证 claim：{anchor.claim}",
        dataset=anchor.dataset,
        baseline=anchor.baseline,
        metrics=unique_preserve_order([*anchor.metrics, "counterexample pass rate", "failure-mode frequency by slice"]),
        ablations=[
            "移除或遮挡 claim 依赖的关键输入证据，观察指标是否显著变化。",
            "替换属性词、物体上下文或选项顺序，检查 benchmark shortcut。",
            "按样本难度、问题类型和失败模式分层分析。",
        ],
        resources=(
            f"Anchor reason: {anchor.reason}。单卡推理或 API 推理；50-100 条样本；人工标注约 4-6 小时；总周期 7 天以内。"
        ),
        timeline=[
            f"Day 1: Anchor paper 指向 `{anchor.paper_title}`；复核原论文 claim、dataset、metric 和 baseline。",
            f"Day 2-3: 从 `{anchor.dataset}` 抽 50-100 条样本并跑 `{anchor.baseline}`。",
            "Day 4: 按论文指标和反例指标标注 failure slices。",
            "Day 5: 构造 20 条能攻击核心 claim 的 counterexamples。",
            "Day 6: 做 ablation 和错误分析，确认失败是否稳定。",
            "Day 7: 输出复现实验报告、失败样本表和下一步 thesis-scale 计划。",
        ],
        success_criterion=f"在 `{anchor.paper_title}` 的小规模设置下复现 claim 相关现象，并定位至少一个稳定失败模式。",
        failure_criterion="现象只来自个别样本、标注争议、prompt 不稳定或 benchmark-specific tuning，无法支持 anchor claim。",
    )


def is_survey_like(paper: dict[str, Any], card: dict[str, Any]) -> bool:
    text = normalize_space(
        " ".join(
            [
                paper.get("title", ""),
                paper.get("type", ""),
                paper.get("abstract", ""),
                card.get("minimal_reproduction", ""),
                card.get("sections_json", ""),
            ],
        ),
    ).lower()
    survey_markers = ["survey", "review", "overview", "taxonomy", "综述", "调研", "文献图谱"]
    return any(marker in text for marker in survey_markers)


def is_invalid_minimal_reproduction(value: str) -> bool:
    lower = value.lower()
    invalid_markers = [
        "需要补充 pdf",
        "缺少 claim",
        "缺少可复现 anchor",
        "不应作为一周复现实验 anchor",
        "不适合按方法论文写",
        "survey/review",
        "not suitable",
        "insufficient evidence",
    ]
    return any(marker in lower for marker in invalid_markers)


def extract_anchor_claim(minimal: str, combined: str) -> str:
    line = extract_labeled_value(minimal, ["Claim to test", "Claim", "claim"])
    if line:
        return line
    match = re.search(r"(we show|we demonstrate|we find|核心 claim 证据：)([^。.!?\n]{12,220})", combined, flags=re.IGNORECASE)
    if match:
        return normalize_space(match.group(0))[:260]
    return ""


def extract_anchor_dataset(minimal: str, combined: str) -> str:
    line = extract_labeled_value(minimal, ["Minimal dataset/subset", "Dataset", "dataset"])
    if line:
        return line
    named = find_named_terms(
        combined,
        [
            "HallusionBench",
            "MMBench",
            "MMMU",
            "POPE",
            "MM-Vet",
            "LLaVA-Bench",
            "SEED-Bench",
            "RealWorldQA",
            "ScienceQA",
            "MathVista",
            "ChartQA",
            "DocVQA",
            "TextVQA",
            "VQA v2",
            "OK-VQA",
            "GQA",
            "COCO",
            "ImageNet",
            "Set5",
            "Set14",
            "Urban100",
            "DIV2K",
        ],
    )
    if named:
        return ", ".join(named)
    if re.search(r"\b\d{2,4}\s*-\s*\d{2,4}\b.*?(samples|样本)", combined, flags=re.IGNORECASE):
        return "论文建议的小规模样本子集"
    return ""


def extract_anchor_metrics(minimal: str, combined: str) -> list[str]:
    metric_line = extract_labeled_value(minimal, ["Metric", "Metrics", "metric", "指标"])
    source = metric_line or combined
    candidates = find_named_terms(
        source,
        [
            "answer accuracy",
            "accuracy",
            "evidence consistency",
            "counterexample pass rate",
            "failure-mode frequency",
            "hallucination rate",
            "grounding accuracy",
            "faithfulness",
            "precision",
            "recall",
            "F1",
            "AUC",
            "mAP",
            "IoU",
            "PSNR",
            "SSIM",
            "LPIPS",
            "FID",
            "BLEU",
            "ROUGE",
            "CIDEr",
        ],
    )
    return unique_preserve_order(candidates)


def extract_anchor_baseline(minimal: str, combined: str) -> str:
    line = extract_labeled_value(minimal, ["Baseline", "baseline"])
    if line:
        return line
    match = re.search(r"(strong baseline|simple baseline|公开强 baseline|轻量 baseline|baseline[^。.!?\n]{0,160})", combined, flags=re.IGNORECASE)
    if match:
        return normalize_space(match.group(0))[:220]
    return ""


def extract_labeled_value(text: str, labels: list[str]) -> str:
    for line in re.split(r"[\n\r]+", text):
        normalized = normalize_space(line)
        for label in labels:
            pattern = rf"^{re.escape(label)}\s*[:：]\s*(.+)$"
            match = re.match(pattern, normalized, flags=re.IGNORECASE)
            if match:
                return normalize_space(match.group(1))[:260]
    return ""


def find_named_terms(text: str, names: list[str]) -> list[str]:
    found: list[str] = []
    for name in names:
        pattern = r"(?<![A-Za-z0-9])" + re.escape(name) + r"(?![A-Za-z0-9])"
        if re.search(pattern, text, flags=re.IGNORECASE):
            found.append(name)
    return unique_preserve_order(found)


def has_benchmark_signal(text: str) -> bool:
    lower = text.lower()
    return any(term in lower for term in ["benchmark", "dataset", "evaluation", "metric", "评测", "数据集", "指标"])


def has_method_signal(text: str) -> bool:
    lower = text.lower()
    return any(term in lower for term in ["method", "model", "architecture", "framework", "training", "方法", "模型", "架构"])


def unique_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = normalize_space(value)
        key = normalized.lower()
        if not normalized or key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result


def normalize_space(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


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
