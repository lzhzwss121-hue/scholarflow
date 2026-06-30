from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from scholarflow_api.baseline_map import BaselineMap
from scholarflow_api.evidence import EvidencePack, build_paper_evidence_pack


@dataclass
class ResearchSight:
    motivation_sharpness: str
    solution_elegance: str
    evaluation_integrity: str
    paradigm_inspiration: str
    why_good: str
    why_not_good: str
    better_angle: str
    baseline_comparison: str
    next_step_proposal: str
    evidence_pack: EvidencePack

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["evidence_pack"] = self.evidence_pack.to_dict()
        return data


def build_research_sight(
    paper: dict[str, Any],
    sections: list[dict[str, Any]],
    baseline_map: BaselineMap,
    direction: str,
) -> ResearchSight:
    text = paper_text(paper, sections)
    title = normalize_space(paper.get("title", "该论文"))
    baseline_reference = pick_baseline_reference(paper, baseline_map)
    method_family = infer_method_family(text)
    benchmark_risk = baseline_map.evaluation_risks[0] if baseline_map.evaluation_risks else "当前评估风险需要继续补充。"
    evidence_pack = build_paper_evidence_pack(paper, sections, direction)

    return ResearchSight(
        motivation_sharpness=build_motivation_sharpness(title, text, direction),
        solution_elegance=build_solution_elegance(title, text, method_family),
        evaluation_integrity=build_evaluation_integrity(title, text, benchmark_risk),
        paradigm_inspiration=build_paradigm_inspiration(title, text, baseline_map),
        why_good=build_why_good(title, text, method_family),
        why_not_good=build_why_not_good(title, text, benchmark_risk),
        better_angle=build_better_angle(title, text, baseline_map, method_family),
        baseline_comparison=build_baseline_comparison(title, baseline_reference, method_family),
        next_step_proposal=build_next_step_proposal(title, direction, baseline_map, method_family),
        evidence_pack=evidence_pack,
    )


def build_motivation_sharpness(title: str, text: str, direction: str) -> str:
    if any(term in text for term in ["hallucination", "faithfulness", "trustworthy", "evidence"]):
        return (
            f"`{title}` 的动机相对锋利：它触及模型输出与证据是否一致的问题，而不是只追求平均性能。"
            "下一步需要确认它是否把失败模式定义得足够可测。"
        )
    if "benchmark" in text or "evaluation" in text:
        return f"`{title}` 的动机偏向评价协议建设，价值取决于它是否揭示了旧 benchmark 无法暴露的真实缺陷。"
    if "efficient" in text or "linear" in text or "mamba" in text:
        return f"`{title}` 的动机在效率或复杂度瓶颈上较清楚，适合用部署成本和长上下文/高分辨率场景检验。"
    return f"`{title}` 与 `{direction}` 相关，但当前元数据不足以证明它抓住了该方向最核心的痛点。"


def build_solution_elegance(title: str, text: str, method_family: str) -> str:
    if method_family == "state-space":
        return f"`{title}` 的优雅性可能来自线性复杂度或全局状态建模，关键要看它是否减少了不必要的注意力堆叠。"
    if method_family == "transformer":
        return (
            f"`{title}` 可能仍属于 Transformer 内部结构改良。它是否优雅，取决于核心机制是否足够简洁，"
            "还是主要依赖更多 block、更多 token 或更多训练技巧。"
        )
    if method_family == "evaluation":
        return f"`{title}` 的解法优雅性不在模型结构，而在问题拆解和评价协议是否能用更少假设暴露关键失败。"
    if method_family == "retrieval":
        return f"`{title}` 的优雅性取决于检索证据是否真的约束生成，而不是只把更多上下文塞给模型。"
    return f"`{title}` 的方法范式信号还不强，需要回到 method 部分判断是否存在第一性原理式简化。"


def build_evaluation_integrity(title: str, text: str, benchmark_risk: str) -> str:
    if "human" in text or "preference" in text:
        return f"`{title}` 至少意识到自动指标的局限。仍需检查人类评价规模、标注一致性和是否覆盖反例场景。"
    if "benchmark" in text or "dataset" in text:
        return f"`{title}` 的评估完整性重点在 benchmark 设计。需要检查数据分布是否泄露、负样本是否足够强，以及 {benchmark_risk}"
    return f"`{title}` 的评估真实性需要保守看待：当前摘要级信息无法证明它避免了 benchmark-specific tuning。{benchmark_risk}"


def build_paradigm_inspiration(title: str, text: str, baseline_map: BaselineMap) -> str:
    if "new paradigm" in text or "framework" in text:
        return f"`{title}` 可能提供框架级启发，但要警惕把工程流程包装成范式转移。"
    if baseline_map.alternative_paradigms:
        alternative = baseline_map.alternative_paradigms[0]
        return (
            f"`{title}` 的范式启发性应与 `{alternative.title}` 这类异质路线交叉比较："
            "如果只在同类方法内提升，它更像增量；如果能改变问题建模方式，才具备方向价值。"
        )
    return f"`{title}` 暂时缺少异质范式参照，不能轻易判断它是否具备范式启发性。"


def build_why_good(title: str, text: str, method_family: str) -> str:
    if "benchmark" in text:
        return f"真正好的地方可能是 `{title}` 重新定义了该怎么测问题，这比单纯刷分更可能影响后续研究。"
    if method_family in {"state-space", "retrieval", "evaluation"}:
        return f"亮点在于它可能绕开主流路线的低效环节，给出更贴近失败模式的建模视角。"
    return f"如果 `{title}` 的贡献成立，它的价值在于把该方向的某个具体瓶颈转化成可复现的模型或评估设计。"


def build_why_not_good(title: str, text: str, benchmark_risk: str) -> str:
    if "large" in text or "scale" in text:
        return f"被高估的风险是 `{title}` 的提升可能主要来自规模、数据或算力，而不是核心机制创新。"
    if "attention" in text or "transformer" in text:
        return f"致命弱点可能是缺乏架构审美：如果只是继续堆叠注意力模块，复杂度和部署成本会削弱论文价值。"
    return f"主要风险是 claim 可能依赖有限实验设置。{benchmark_risk}"


def build_better_angle(title: str, text: str, baseline_map: BaselineMap, method_family: str) -> str:
    if method_family == "transformer":
        return (
            "更好的角度是从复杂度和状态建模重新审视问题：是否可以用 state-space、检索约束或更强评价协议，"
            "替代继续修补注意力结构。"
        )
    if "benchmark" in text or method_family == "evaluation":
        return "更好的角度是把评估从平均分数升维为失败模式定位：专门设计反例、长尾样本和跨模型族测试。"
    if baseline_map.alternative_paradigms:
        return f"可以从 `{baseline_map.alternative_paradigms[0].title}` 所代表的异质路线切入，寻找降维打击式改写。"
    return "更好的角度是先找出方法最依赖的隐含假设，再围绕该假设设计更小但更尖锐的验证任务。"


def build_baseline_comparison(title: str, reference: str, method_family: str) -> str:
    if reference:
        return (
            f"与 `{reference}` 相比，`{title}` 需要证明自己不是同范式微调。"
            f"当前判断的关键是：它是否在 `{method_family}` 路线之外改变了问题定义、复杂度或评价方式。"
        )
    return f"当前候选池缺少足够明确的 baseline，`{title}` 的优劣判断需要补充经典论文或最新强 baseline。"


def build_next_step_proposal(title: str, direction: str, baseline_map: BaselineMap, method_family: str) -> str:
    first_risk = baseline_map.evaluation_risks[0] if baseline_map.evaluation_risks else "当前评价协议可能过窄"
    if "hallucination" in direction.lower() or "faithfulness" in direction.lower():
        return (
            "下一步可以做一个证据敏感反例集：固定答案正确性，系统性改变视觉证据可见性、遮挡和文本诱导，"
            f"检验 `{title}` 是否真的降低幻觉，而不是适配 benchmark。"
        )
    if method_family == "transformer":
        return (
            "下一步可以用一个小规模 ablation 比较 Transformer 修补路线与线性状态建模路线：控制参数量和训练数据，"
            "只比较长程依赖、部署延迟和失败样本恢复能力。"
        )
    return f"下一步建议围绕 `{first_risk}` 设计一周最小实验，验证 `{title}` 的核心机制是否仍然成立。"


def pick_baseline_reference(paper: dict[str, Any], baseline_map: BaselineMap) -> str:
    paper_key = normalize_title_key(paper.get("title", ""))
    for group in [
        baseline_map.recent_strong_baselines,
        baseline_map.classic_baselines,
        baseline_map.alternative_paradigms,
    ]:
        for reference in group:
            if normalize_title_key(reference.title) != paper_key:
                return reference.title
    return ""


def infer_method_family(text: str) -> str:
    if any(term in text for term in ["mamba", "state space", "ssm", "selective scan"]):
        return "state-space"
    if any(term in text for term in ["transformer", "attention", "vit", "swin"]):
        return "transformer"
    if any(term in text for term in ["benchmark", "evaluation", "metric"]):
        return "evaluation"
    if any(term in text for term in ["retrieval", "rag", "memory"]):
        return "retrieval"
    if any(term in text for term in ["diffusion", "score-based"]):
        return "diffusion"
    return "general"


def paper_text(paper: dict[str, Any], sections: list[dict[str, Any]]) -> str:
    section_text = " ".join(
        f"{section.get('title', '')} {section.get('content', '')}" for section in sections
    )
    return normalize_space(
        f"{paper.get('title', '')} {paper.get('abstract', '')} {paper.get('venue', '')} {section_text}",
    ).lower()


def normalize_title_key(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", title.lower())


def normalize_space(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()
