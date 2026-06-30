from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any


TOP_VENUE_KEYWORDS = [
    "neurips",
    "nips",
    "icml",
    "iclr",
    "cvpr",
    "iccv",
    "eccv",
    "acl",
    "emnlp",
    "naacl",
    "aaai",
    "ijcai",
    "kdd",
    "sigir",
    "www",
    "the web conference",
    "tmlr",
    "jmlr",
    "tpami",
    "ijcv",
]

METHOD_FAMILIES = {
    "transformer": ["transformer", "attention", "swin", "vit"],
    "state-space": ["mamba", "state space", "ssm", "selective scan"],
    "diffusion": ["diffusion", "score-based", "denoising"],
    "retrieval": ["retrieval", "rag", "memory", "search"],
    "alignment": ["alignment", "preference", "rlhf", "dpo"],
    "evaluation": ["benchmark", "evaluation", "metric", "assessment"],
    "agent": ["agent", "tool", "workflow", "planning"],
    "dataset": ["dataset", "data", "corpus", "annotation"],
}

COMMON_BENCHMARK_TERMS = [
    "imagenet",
    "coco",
    "vqa",
    "gqa",
    "mme",
    "mmbench",
    "pope",
    "set5",
    "set14",
    "bsd100",
    "urban100",
    "div2k",
    "human preference",
    "win rate",
]


@dataclass
class BaselineReference:
    title: str
    year: str
    venue: str
    source: str
    url: str
    category: str
    reason: str
    strengths: str
    risks: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BaselineMap:
    direction: str
    task_definition: str
    classic_baselines: list[BaselineReference]
    recent_strong_baselines: list[BaselineReference]
    alternative_paradigms: list[BaselineReference]
    common_benchmarks: list[str]
    evaluation_risks: list[str]
    open_questions: list[str]
    generated_from: list[str]
    curator_notes: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "direction": self.direction,
            "task_definition": self.task_definition,
            "classic_baselines": [baseline.to_dict() for baseline in self.classic_baselines],
            "recent_strong_baselines": [baseline.to_dict() for baseline in self.recent_strong_baselines],
            "alternative_paradigms": [baseline.to_dict() for baseline in self.alternative_paradigms],
            "common_benchmarks": self.common_benchmarks,
            "evaluation_risks": self.evaluation_risks,
            "open_questions": self.open_questions,
            "generated_from": self.generated_from,
            "curator_notes": self.curator_notes,
        }


def build_baseline_map(direction: str, candidate_papers: list[dict[str, Any]], selected_papers: list[dict[str, Any]]) -> BaselineMap:
    normalized_direction = normalize_space(direction)
    papers = dedupe_papers([*candidate_papers, *selected_papers])
    scored = sorted(papers, key=lambda paper: score_reference_candidate(paper, normalized_direction), reverse=True)
    family_buckets = group_by_method_family(scored)
    recent = select_recent_strong_baselines(scored, normalized_direction, limit=5)
    classic = select_classic_baselines(scored, recent, limit=4)
    alternatives = select_alternative_paradigms(family_buckets, recent, classic, limit=5)
    benchmarks = infer_common_benchmarks(normalized_direction, scored)
    risks = infer_evaluation_risks(normalized_direction, benchmarks, scored)
    questions = infer_open_questions(normalized_direction, alternatives, risks)
    generated_from = [paper.get("title", "") for paper in scored[:12] if paper.get("title")]

    return BaselineMap(
        direction=normalized_direction,
        task_definition=build_task_definition(normalized_direction),
        classic_baselines=classic,
        recent_strong_baselines=recent,
        alternative_paradigms=alternatives,
        common_benchmarks=benchmarks,
        evaluation_risks=risks,
        open_questions=questions,
        generated_from=generated_from,
        curator_notes=(
            "BaselineMap 当前由检索候选池和本轮入选论文启发式生成；它是可追溯的方向背景包，"
            "后续可替换为引用追踪、Best Paper 先验库和向量检索。"
        ),
    )


def render_baseline_map_markdown(baseline_map: BaselineMap) -> str:
    sections = [
        f"# BaselineMap: {baseline_map.direction}",
        "## Task Definition",
        baseline_map.task_definition,
        "## Classic Baselines",
        render_reference_list(baseline_map.classic_baselines),
        "## Recent Strong Baselines",
        render_reference_list(baseline_map.recent_strong_baselines),
        "## Alternative Paradigms",
        render_reference_list(baseline_map.alternative_paradigms),
        "## Common Benchmarks",
        "\n".join(f"- {item}" for item in baseline_map.common_benchmarks) or "- No stable benchmark signal yet.",
        "## Evaluation Risks",
        "\n".join(f"- {item}" for item in baseline_map.evaluation_risks),
        "## Open Questions",
        "\n".join(f"- {item}" for item in baseline_map.open_questions),
        "## Curator Notes",
        baseline_map.curator_notes,
    ]
    return "\n\n".join(sections)


def render_reference_list(references: list[BaselineReference]) -> str:
    if not references:
        return "- No reliable reference found in current candidate pool."
    return "\n".join(
        f"- **{item.title}** ({item.year or 'year unknown'}, {item.venue or item.source or 'source unknown'}): {item.reason}"
        for item in references
    )


def build_task_definition(direction: str) -> str:
    lower = direction.lower()
    if any(term in lower for term in ["hallucination", "幻觉", "faithfulness", "可信", "trustworthy"]):
        return (
            f"`{direction}` 的任务核心是识别模型输出是否被真实证据支撑，并区分 benchmark 分数提升与真实可靠性提升。"
        )
    if any(term in lower for term in ["agent", "workflow", "科研"]):
        return f"`{direction}` 的任务核心是把检索、阅读、批判、记忆和实验规划组织成可追溯的科研工作流。"
    if any(term in lower for term in ["restoration", "super-resolution", "超分", "image"]):
        return f"`{direction}` 的任务核心是恢复视觉细节，同时平衡感知质量、计算成本和可部署性。"
    return f"`{direction}` 的任务核心需要同时界定研究对象、失败模式、评价协议和可验证的改进目标。"


def select_recent_strong_baselines(papers: list[dict[str, Any]], direction: str, limit: int) -> list[BaselineReference]:
    recent = [paper for paper in papers if parse_year(paper.get("year", "")) >= 2024]
    if len(recent) < limit:
        recent.extend([paper for paper in papers if paper not in recent])
    return [
        to_reference(
            paper,
            "recent_strong",
            build_reason(paper, direction, "近三年强相关候选，可作为当前路线的直接比较对象。"),
        )
        for paper in recent[:limit]
    ]


def select_classic_baselines(
    papers: list[dict[str, Any]],
    recent: list[BaselineReference],
    limit: int,
) -> list[BaselineReference]:
    recent_titles = {normalize_title_key(item.title) for item in recent}
    older_or_foundational = [
        paper
        for paper in papers
        if normalize_title_key(paper.get("title", "")) not in recent_titles and parse_year(paper.get("year", "")) <= 2023
    ]
    if len(older_or_foundational) < limit:
        older_or_foundational.extend(
            paper for paper in papers if normalize_title_key(paper.get("title", "")) not in recent_titles
        )
    return [
        to_reference(
            paper,
            "classic",
            "在候选池中更像该方向的基础参照；用于判断新论文是否真的超越了已有问题定义或方法范式。",
        )
        for paper in older_or_foundational[:limit]
    ]


def select_alternative_paradigms(
    family_buckets: dict[str, list[dict[str, Any]]],
    recent: list[BaselineReference],
    classic: list[BaselineReference],
    limit: int,
) -> list[BaselineReference]:
    used = {normalize_title_key(item.title) for item in [*recent, *classic]}
    output: list[BaselineReference] = []
    for family, papers in family_buckets.items():
        for paper in papers:
            key = normalize_title_key(paper.get("title", ""))
            if key in used:
                continue
            output.append(
                to_reference(
                    paper,
                    "alternative_paradigm",
                    f"代表 `{family}` 路线，可用于检查目标论文是否只是同范式内微调，或是否存在降维打击角度。",
                ),
            )
            used.add(key)
            break
        if len(output) >= limit:
            break
    return output


def group_by_method_family(papers: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    for paper in papers:
        text = paper_text(paper)
        family = "general"
        for name, terms in METHOD_FAMILIES.items():
            if any(term in text for term in terms):
                family = name
                break
        buckets.setdefault(family, []).append(paper)
    return buckets


def infer_common_benchmarks(direction: str, papers: list[dict[str, Any]]) -> list[str]:
    text = " ".join(paper_text(paper) for paper in papers)
    found = [term for term in COMMON_BENCHMARK_TERMS if term in text]
    lower = direction.lower()
    if "hallucination" in lower and "POPE" not in found:
        found.append("POPE / object hallucination style evaluation")
    if ("super-resolution" in lower or "超分" in lower) and "DIV2K" not in found:
        found.extend(["DIV2K", "Set5 / Set14 / Urban100"])
    if not found:
        found.extend(["task-specific benchmark", "human or expert validation", "cross-dataset generalization"])
    return unique_preserve_order(found)[:8]


def infer_evaluation_risks(direction: str, benchmarks: list[str], papers: list[dict[str, Any]]) -> list[str]:
    risks = [
        "只在对方法有利的单一 benchmark 上刷分，无法证明真实场景稳健性。",
        "指标可能测到表层相关性，而不是用户真正关心的可靠性、感知质量或任务完成质量。",
        "缺少跨数据集、跨模型族或长尾场景验证时，claim 容易被 benchmark bias 放大。",
    ]
    lower = direction.lower()
    if any(term in lower for term in ["hallucination", "faithfulness", "可信", "multimodal", "vlm"]):
        risks.append("VLM 评价如果只看答案对错，可能忽略输出是否被图像证据支撑。")
    if any(term in lower for term in ["agent", "workflow", "科研"]):
        risks.append("科研 Agent 评估如果只看生成文本流畅度，无法证明它真的减少科研时间或降低新手门槛。")
    if any("psnr" in paper_text(paper) or "ssim" in paper_text(paper) for paper in papers):
        risks.append("PSNR/SSIM 提升不一定对应人类感知质量提升，需要感知指标或用户研究补充。")
    if benchmarks:
        risks.append(f"当前候选池反复出现 `{benchmarks[0]}`，需要防止 benchmark-specific tuning。")
    return unique_preserve_order(risks)[:6]


def infer_open_questions(direction: str, alternatives: list[BaselineReference], risks: list[str]) -> list[str]:
    questions = [
        "这个方向真正不可替代的问题定义是什么，还是只是把旧任务包装成新术语？",
        "是否存在一个更简单的机制可以解释同样的性能提升，从而削弱复杂方法的必要性？",
        "如果把评价从平均分数改成失败模式定位，当前方法是否仍然成立？",
    ]
    if alternatives:
        questions.append(f"与 `{alternatives[0].category}` 路线相比，目标方法的优势是否来自核心机制，而不是实验设置？")
    if risks:
        questions.append("能否设计一个反例 benchmark，专门打穿当前方法最依赖的假设？")
    return questions[:5]


def to_reference(paper: dict[str, Any], category: str, reason: str) -> BaselineReference:
    text = paper_text(paper)
    return BaselineReference(
        title=normalize_space(paper.get("title", "")) or "Untitled paper",
        year=normalize_space(str(paper.get("year", ""))),
        venue=normalize_space(paper.get("venue", "")),
        source=normalize_space(paper.get("source", "")),
        url=normalize_space(paper.get("url", "")),
        category=category,
        reason=reason,
        strengths=build_strength_signal(text),
        risks=build_risk_signal(text),
    )


def build_reason(paper: dict[str, Any], direction: str, fallback: str) -> str:
    overlap = [term for term in significant_terms(direction) if term in paper_text(paper)]
    venue = paper.get("venue") or paper.get("source") or "source metadata insufficient"
    if overlap:
        return f"匹配方向关键词：{', '.join(overlap[:4])}；来源信号：{venue}。{fallback}"
    return f"来源信号：{venue}。{fallback}"


def build_strength_signal(text: str) -> str:
    if "benchmark" in text or "evaluation" in text:
        return "可能强在任务定义或评价协议，可用于检查目标论文的评估真实性。"
    if "attention" in text or "transformer" in text:
        return "可能强在架构表达能力，可作为复杂模型路线的直接参照。"
    if "dataset" in text:
        return "可能强在数据构造，可用于判断方法提升是否依赖数据分布。"
    return "提供同方向问题定义或方法路线参照。"


def build_risk_signal(text: str) -> str:
    if "benchmark" in text:
        return "需要警惕 benchmark 设计是否偏向特定模型或答案分布。"
    if "large" in text or "scale" in text:
        return "需要警惕性能提升是否主要来自规模或算力。"
    if "attention" in text:
        return "需要关注复杂度和部署成本。"
    return "需要人工复核其与当前方向的真实相关性。"


def score_reference_candidate(paper: dict[str, Any], direction: str) -> float:
    text = paper_text(paper)
    terms = significant_terms(direction)
    score = sum(0.4 for term in terms if term in text)
    if any(keyword in text for keyword in TOP_VENUE_KEYWORDS):
        score += 0.7
    year = parse_year(paper.get("year", ""))
    if year >= 2024:
        score += 0.5
    if "benchmark" in text or "survey" in text or "baseline" in text:
        score += 0.35
    score += float(paper.get("relevance_score") or 0.0)
    return score


def dedupe_papers(papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for paper in papers:
        key = normalize_title_key(paper.get("title", ""))
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(paper)
    return output


def paper_text(paper: dict[str, Any]) -> str:
    return normalize_space(
        f"{paper.get('title', '')} {paper.get('abstract', '')} {paper.get('venue', '')} {paper.get('source', '')}",
    ).lower()


def parse_year(value: Any) -> int:
    match = re.search(r"(19|20)\d{2}", str(value or ""))
    return int(match.group(0)) if match else 0


def significant_terms(query: str) -> set[str]:
    stop_words = {
        "the",
        "and",
        "for",
        "with",
        "from",
        "into",
        "based",
        "model",
        "models",
        "paper",
        "research",
        "direction",
        "方向",
        "论文",
        "科研",
        "研究",
        "了解",
    }
    return {
        term
        for term in re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]+", query.lower())
        if len(term) > 1 and term not in stop_words
    }


def unique_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        normalized = normalize_space(value)
        key = normalized.lower()
        if key and key not in seen:
            seen.add(key)
            output.append(normalized)
    return output


def normalize_title_key(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", title.lower())


def normalize_space(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()
