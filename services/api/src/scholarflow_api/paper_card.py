from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class PaperCardSection:
    id: str
    title: str
    content: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass
class PaperSignals:
    task: str
    method: str
    dataset: str
    metric: str
    baseline: str
    claim: str
    limitation: str
    contribution_type: str
    contribution_evidence: str
    missing_signals: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DeepPaperCard:
    paper_title: str
    evidence_level: str
    signals: PaperSignals
    sections: list[PaperCardSection]
    weakest_assumption: str
    minimal_reproduction: str
    counterexample: str
    follow_up_idea: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "paper_title": self.paper_title,
            "evidence_level": self.evidence_level,
            "signals": self.signals.to_dict(),
            "sections": [section.to_dict() for section in self.sections],
            "weakest_assumption": self.weakest_assumption,
            "minimal_reproduction": self.minimal_reproduction,
            "counterexample": self.counterexample,
            "follow_up_idea": self.follow_up_idea,
        }


SECTION_TITLES = [
    ("research_problem", "1. 研究问题与背景"),
    ("prior_work", "2. 已有研究与不足"),
    ("author_reasoning", "3. 作者可能的思考路径重建"),
    ("intuition", "4. 核心 Intuition"),
    ("method_pipeline", "5. 方法 Pipeline 与真实例子"),
    ("math_theory", "6. 数学与理论解释"),
    ("experiment_logic", "7. 实验逻辑与 Claim 验证"),
    ("takeaways", "8. Take-aways"),
    ("weakest_assumption", "9. 最脆弱的假设"),
    ("minimal_reproduction", "10. 一周最小复现实验"),
    ("counterexample", "11. 反例设计"),
    ("follow_up", "12. 非增量 Follow-up Idea"),
]


def generate_deep_paper_card(paper: dict[str, Any], extra_context: str = "") -> DeepPaperCard:
    title = normalize_space(paper.get("title") or "Untitled Paper")
    abstract = normalize_space(paper.get("abstract") or "")
    venue = normalize_space(paper.get("venue") or paper.get("source") or "unknown venue")
    year = normalize_space(str(paper.get("year") or "unknown year"))
    context = normalize_space(f"{abstract} {extra_context}")
    evidence_level = infer_card_evidence_level(abstract, extra_context)
    signals = extract_paper_signals(title=title, abstract=abstract, paper_text=extra_context, venue=venue)
    focus = infer_focus(title, context)
    limitation = (
        signals.limitation
        if has_signal(signals.limitation)
        else "无法判断：摘要/PDF 原文没有提供 limitation 或 failure mode 证据"
    )
    weakest_assumption = build_weakest_assumption(focus, signals)
    minimal_reproduction = build_minimal_reproduction(signals, title)
    counterexample = build_counterexample(signals, focus)
    follow_up = build_follow_up_idea(signals, focus)
    signal_summary = render_signal_summary(signals)

    sections = apply_evidence_boundary_to_sections(
        [
        PaperCardSection(
            "research_problem",
            "1. 研究问题与背景",
            (
                f"论文 `{title}` ({year}, {venue}) 的可见任务信号是：{signals.task}。"
                f" ScholarFlow 从标题、摘要和可选正文中抽到的关键信号为：{signal_summary}。"
                "这个问题重要与否不应只看论文声称，而要看它是否能把一个真实失败模式、任务瓶颈或评价缺口变成可验证对象。"
                f"当前摘要/正文线索为：{summarize_context(context)}"
            ),
        ),
        PaperCardSection(
            "prior_work",
            "2. 已有研究与不足",
            (
                f"当前可见不足信号：{limitation}。"
                f"如果这篇论文是 `{signals.contribution_type}` 类型工作，需要检查它是否真的补上了 prior work 的关键缺口："
                f"数据集/benchmark 是否明确（{signals.dataset}），指标是否能测到目标能力（{signals.metric}），"
                f"对照 baseline 是否可复核（{signals.baseline}），"
                f"核心 claim 是否能被实验闭环支持（{signals.claim}）。"
                f"{missing_signal_sentence(signals, ['dataset', 'metric', 'baseline', 'claim'])}"
            ),
        ),
        PaperCardSection(
            "author_reasoning",
            "3. 作者可能的思考路径重建",
            (
                "以下是 ScholarFlow 的推断性重建，不把论文自己的贡献倒用为前提："
                f"研究者可能先从 `{signals.task}` 中观察到 {limitation}；"
                f"再发现已有工作无法同时解释任务、方法、数据、指标和 claim 的对应关系。"
                f"在这种前提下，比较自然的思路是围绕 `{signals.claim}` 设计一个更可诊断的切口，"
                "而不是先假设作者的方法一定正确。"
                f"{missing_signal_sentence(signals, ['method', 'dataset', 'metric', 'baseline'])}"
            ),
        ),
        PaperCardSection(
            "intuition",
            "4. 核心 Intuition",
            (
                f"核心 intuition：用 `{signals.method}` 去处理 `{signals.task}`，并通过 `{signals.metric}` 在 `{signals.dataset}` 上相对 `{signals.baseline}` 验证 `{signals.claim}`。"
                "如果上述四个环节都清楚，这篇论文的 idea 才能从“看起来合理”变成“可验证”。"
                f"{missing_signal_sentence(signals, ['method', 'dataset', 'metric', 'baseline', 'claim'])}"
            ),
        ),
        PaperCardSection(
            "method_pipeline",
            "5. 方法 Pipeline 与真实例子",
            build_method_pipeline_section(signals),
        ),
        PaperCardSection(
            "math_theory",
            "6. 数学与理论解释",
            build_math_section(focus, signals),
        ),
        PaperCardSection(
            "experiment_logic",
            "7. 实验逻辑与 Claim 验证",
            build_experiment_logic_section(signals),
        ),
        PaperCardSection(
            "takeaways",
            "8. Take-aways",
            build_takeaways_section(signals, focus),
        ),
        PaperCardSection(
            "weakest_assumption",
            "9. 最脆弱的假设",
            weakest_assumption,
        ),
        PaperCardSection(
            "minimal_reproduction",
            "10. 一周最小复现实验",
            minimal_reproduction,
        ),
        PaperCardSection(
            "counterexample",
            "11. 反例设计",
            counterexample,
        ),
        PaperCardSection(
            "follow_up",
            "12. 非增量 Follow-up Idea",
            follow_up,
        ),
        ],
        evidence_level,
        title,
    )

    return DeepPaperCard(
        paper_title=title,
        evidence_level=evidence_level,
        signals=signals,
        sections=sections,
        weakest_assumption=weakest_assumption,
        minimal_reproduction=minimal_reproduction,
        counterexample=counterexample,
        follow_up_idea=follow_up,
    )


INSUFFICIENT_PREFIX = "当前证据不足"

DATASET_NAMES = [
    "MMBench",
    "MMMU",
    "MM-Vet",
    "POPE",
    "HallusionBench",
    "LLaVA-Bench",
    "SEED-Bench",
    "RealWorldQA",
    "ScienceQA",
    "MathVista",
    "ChartQA",
    "DocVQA",
    "TextVQA",
    "VizWiz",
    "VQA v2",
    "OK-VQA",
    "A-OKVQA",
    "GQA",
    "RefCOCO",
    "COCO",
    "ImageNet",
    "Set5",
    "Set14",
    "BSD100",
    "Urban100",
    "Manga109",
    "DIV2K",
]

METRIC_NAMES = [
    "accuracy",
    "acc",
    "F1",
    "precision",
    "recall",
    "AUC",
    "mAP",
    "IoU",
    "win rate",
    "human evaluation",
    "PSNR",
    "SSIM",
    "LPIPS",
    "FID",
    "BLEU",
    "ROUGE",
    "CIDEr",
    "faithfulness",
    "grounding accuracy",
    "hallucination rate",
]

METHOD_MARKERS = [
    "we propose",
    "we introduce",
    "we present",
    "our method",
    "our framework",
    "our model",
    "architecture",
    "algorithm",
    "pipeline",
    "training",
    "decoding",
    "prompt",
]

CLAIM_MARKERS = [
    "we show",
    "we demonstrate",
    "outperform",
    "improve",
    "achieve",
    "state-of-the-art",
    "sota",
    "effective",
    "robust",
    "reveals",
    "find that",
    "we find",
]

LIMITATION_MARKERS = [
    "limitation",
    "limited",
    "however",
    "challenge",
    "failure",
    "fails",
    "bias",
    "shortcut",
    "spurious",
    "mismatch",
    "hides",
    "brittle",
    "inadequate",
    "gap",
]


def infer_card_evidence_level(abstract: str, paper_text: str) -> str:
    supplemental = normalize_space(paper_text)
    lower = supplemental.lower()
    full_text_markers = [
        "method",
        "experiment",
        "results",
        "dataset",
        "baseline",
        "ablation",
        "evaluation",
        "we propose",
        "we compare",
        "we evaluate",
    ]
    marker_count = sum(1 for marker in full_text_markers if marker in lower)
    if len(supplemental) >= 800 or (len(supplemental) >= 220 and marker_count >= 3):
        return "full_text"
    if normalize_space(abstract) or supplemental:
        return "abstract_only"
    return "metadata_only"


def apply_evidence_boundary_to_sections(
    sections: list[PaperCardSection],
    evidence_level: str,
    paper_title: str,
) -> list[PaperCardSection]:
    if evidence_level == "metadata_only":
        prompts = {
            "research_problem": "需要补充 abstract 后确认论文实际研究问题、背景与价值。",
            "prior_work": "需要原文 related work 或 abstract 才能判断已有研究不足。",
            "author_reasoning": "没有作者动机或失败模式原文，不能重建作者思考路径。",
            "intuition": "没有 method/claim 原文，不能概括核心 intuition。",
            "method_pipeline": "需要 PDF 方法段后再拆解 input、processing 与 output。",
            "math_theory": "没有公式、目标函数或方法描述，不能生成数学解释。",
            "experiment_logic": "需要 dataset、metric、baseline 与 claim 原文后判断实验闭环。",
            "takeaways": "当前只能记录标题线索，不能形成论文级 take-away。",
            "weakest_assumption": "没有 claim/limitation/dataset/metric 原文，无法判断最脆弱假设。",
            "minimal_reproduction": "缺少可验证 anchor，本节保持 blocked。",
            "counterexample": "没有可测试 claim，不能为该论文设计反例。",
            "follow_up": "没有 limitation/claim/evaluation 证据，不提出论文专属 follow-up。",
        }
        return [
            PaperCardSection(
                section.id,
                section.title,
                f"`{paper_title}` 当前仅有 metadata/title。{prompts.get(section.id, '需要补充原文证据后再判断。')}",
            )
            for section in sections
        ]
    # Abstract/full-text cards keep distinct paper-specific content. The global
    # evidence boundary is rendered once instead of being repeated 12 times.
    return sections


def evidence_boundary_sentence(evidence_level: str) -> str:
    if evidence_level == "metadata_only":
        return (
            "证据边界（metadata_only）：当前没有 abstract/PDF/正文，下面是基于标题和元数据的阅读提纲，"
            "不是完整正文阅读结论。"
        )
    return (
        "证据边界（abstract_only）：当前没有 PDF/完整正文，下面是基于标题、摘要和可选片段的阅读提纲，"
        "不能当作已讲清整篇论文。"
    )


def evidence_gap_sentence(evidence_level: str) -> str:
    if evidence_level == "metadata_only":
        return "缺少 abstract、method、experiment、baseline、dataset、metric 和 failure case 原文证据。"
    return "缺少 PDF/完整正文中的 method、experiment、baseline、ablation、failure case 和表格证据。"


def extract_paper_signals(title: str, abstract: str, paper_text: str = "", venue: str = "") -> PaperSignals:
    title_text = normalize_space(title)
    abstract_text = normalize_space(abstract)
    full_text = normalize_space(paper_text)
    combined = normalize_space(f"{title_text}. {abstract_text} {full_text}")
    evidence_text = full_text or abstract_text or combined
    contribution_type, contribution_evidence = infer_contribution_type(title, abstract_text, full_text, venue)
    task = extract_task_signal(title, abstract, combined, contribution_type)
    method = extract_method_signal(evidence_text, contribution_type)
    dataset = extract_named_signal_priority(
        [full_text, abstract_text, title_text],
        DATASET_NAMES,
        "未发现明确 dataset/benchmark 名称",
    )
    metric = extract_named_signal_priority(
        [full_text, abstract_text, title_text],
        METRIC_NAMES,
        "未发现明确 metric/evaluation 指标",
    )
    baseline = extract_baseline_signal(evidence_text)
    claim = extract_claim_signal(evidence_text, title)
    limitation = extract_limitation_signal(evidence_text)
    signals = PaperSignals(
        task=task,
        method=method,
        dataset=dataset,
        metric=metric,
        baseline=baseline,
        claim=claim,
        limitation=limitation,
        contribution_type=contribution_type,
        contribution_evidence=contribution_evidence,
        missing_signals=[],
    )
    signals.missing_signals = [
        field
        for field in ["method", "dataset", "metric", "baseline", "claim", "limitation"]
        if not has_signal(getattr(signals, field))
    ]
    return signals


def infer_contribution_type(title: str, abstract: str, paper_text: str, venue: str) -> tuple[str, str]:
    """Classify the contribution from an explicit claim, not incidental citations.

    Full papers routinely contain phrases such as "we review related work" or
    cite survey papers. Those mentions must not turn an analysis or benchmark
    paper into a survey. Survey classification therefore needs a title signal
    or an explicit self-description near the abstract/introduction.
    """
    title_text = normalize_space(title)
    abstract_text = normalize_space(abstract)
    body_text = normalize_space(paper_text)
    title_lower = title_text.lower()
    survey_title_patterns = [
        r"\b(?:a|an|the)?\s*(?:comprehensive\s+)?survey\b",
        r"\b(?:a|an|the)?\s*(?:systematic\s+)?review\b",
        r"\boverview\b",
        r"\btaxonomy\b",
    ]
    for pattern in survey_title_patterns:
        if re.search(pattern, title_lower):
            return "survey", f"标题证据：{truncate_text(title_text)}"

    survey_self_description_patterns = [
        r"\b(?:this (?:paper|work)|we)\s+(?:present|provide|conduct|offer|develop|introduce)\s+(?:a|an|the)?\s*(?:comprehensive\s+|systematic\s+)?(?:survey|review|overview|taxonomy)\b",
        r"\b(?:this (?:paper|work)|we)\s+(?:survey|review)\s+(?:the\s+)?(?:literature|field|research|studies)\b",
        r"\b(?:a|an)\s+(?:comprehensive\s+|systematic\s+)?(?:survey|review)\s+of\b",
    ]
    for source_name, source_text in (("摘要", abstract_text), ("正文", body_text[:12000])):
        for sentence in split_sentences(source_text):
            if any(re.search(pattern, sentence, flags=re.IGNORECASE) for pattern in survey_self_description_patterns):
                return "survey", f"{source_name}证据：{truncate_text(sentence)}"

    # The abstract is the paper's concise self-description. Prefer it over a
    # body-wide keyword hit, where related-work citations can otherwise look
    # like the paper's own contribution.
    evidence_sources = [abstract_text, body_text, title_text, normalize_space(venue)]
    benchmark_evidence = find_first_evidence_sentence(
        evidence_sources,
        ["benchmark", "dataset", "evaluation protocol", "evaluation suite"],
    )
    if benchmark_evidence:
        return "benchmark", benchmark_evidence

    method_evidence = find_first_evidence_sentence(
        evidence_sources,
        ["we propose", "we introduce", "we present", "our method", "our framework", "architecture", "algorithm"],
    )
    if method_evidence:
        return "method", method_evidence

    analysis_evidence = find_first_evidence_sentence(
        evidence_sources,
        ["analysis", "analyze", "analyse", "investigate", "characterize", "study"],
    )
    if analysis_evidence:
        return "analysis", analysis_evidence

    system_evidence = find_first_evidence_sentence(evidence_sources, ["agent", "workflow", "system"])
    if system_evidence:
        return "system", system_evidence
    return "unknown", "未发现可定位的贡献类型证据。"


def find_first_evidence_sentence(texts: list[str], markers: list[str]) -> str:
    for text in texts:
        sentence = find_sentence(text, markers)
        if sentence:
            return f"贡献证据：{sentence}"
    return ""


def extract_task_signal(title: str, abstract: str, text: str, contribution_type: str) -> str:
    lower = text.lower()
    if contribution_type == "survey":
        return f"围绕 `{title}` 的文献图谱、问题分类或研究脉络梳理"
    match = re.search(r"\bfor\s+([^:.;!?]{4,120})", title, flags=re.IGNORECASE)
    if match:
        return truncate_text(match.group(1))
    if "hallucination" in lower or "幻觉" in lower:
        return "vision-language model hallucination 的检测、评估或缓解"
    if "visual grounding" in lower or "grounded" in lower or "evidence" in lower or "faithful" in lower:
        return "模型输出是否与可验证视觉证据一致"
    if "benchmark" in lower or "evaluation" in lower:
        return "benchmark/evaluation 是否真实测到目标 AI 能力"
    if "super-resolution" in lower or "image restoration" in lower:
        return "图像恢复/超分辨率中的质量提升与可部署性问题"
    if "agent" in lower or "workflow" in lower:
        return "科研 agent 的流程规划、工具调用与结果追踪"
    return infer_focus(title, abstract)


def extract_method_signal(text: str, contribution_type: str) -> str:
    if contribution_type == "survey":
        return "综述/调研型贡献：主要方法应是组织、比较和归纳已有文献，而不是提出可训练模型。"
    sentence = find_sentence(text, METHOD_MARKERS)
    if sentence:
        return f"方法证据：{sentence}"
    if contribution_type == "benchmark":
        benchmark_sentence = find_sentence(text, ["benchmark", "dataset", "evaluation", "protocol"])
        if benchmark_sentence:
            return f"评测/benchmark 构造方法：{benchmark_sentence}"
    return insufficient("摘要/正文中没有抽到明确方法机制、模型结构、训练策略或评测协议")


def extract_claim_signal(text: str, title: str) -> str:
    sentence = find_sentence(text, CLAIM_MARKERS)
    if sentence:
        return f"核心 claim 证据：{sentence}"
    if "?" in title:
        return insufficient("标题更像研究问题，摘要/正文未给出明确结论型 claim")
    return insufficient("未发现 we show/demonstrate/outperform/improve 等明确 claim 句")


def extract_limitation_signal(text: str) -> str:
    sentence = find_sentence(text, LIMITATION_MARKERS)
    if sentence:
        return f"显式或隐含不足：{sentence}"
    return insufficient("摘要/正文未明确说明已有方法不足或 failure mode")


def extract_named_signal(text: str, names: list[str], missing_reason: str) -> str:
    found: list[str] = []
    for name in names:
        pattern = r"(?<![A-Za-z0-9])" + re.escape(name) + r"(?![A-Za-z0-9])"
        if re.search(pattern, text, flags=re.IGNORECASE):
            found.append(name)
    if found:
        return ", ".join(unique_preserve_order(found))
    return insufficient(missing_reason)


def extract_named_signal_priority(texts: list[str], names: list[str], missing_reason: str) -> str:
    for text in texts:
        if not normalize_space(text):
            continue
        signal = extract_named_signal(text, names, missing_reason)
        if has_signal(signal):
            return signal
    return insufficient(missing_reason)


def extract_baseline_signal(text: str) -> str:
    normalized = normalize_space(text)
    if not normalized:
        return insufficient("摘要/正文未发现 baseline、comparison 或对照方法")
    patterns = [
        r"\b[Bb]aselines?\s*(?:include|are|:)\s*([^.;。！？!?]{2,160})",
        r"\b[Cc]ompared\s+(?:with|against|to)\s+([^.;。！？!?]{2,140})",
        r"\b[Cc]omparison\s+(?:with|against|to)\s+([^.;。！？!?]{2,140})",
        r"\b[Oo]utperform(?:s|ed|ing)?\s+([^.;。！？!?]{2,120})",
        r"\bvs\.?\s+([^.;。！？!?]{2,100})",
    ]
    for pattern in patterns:
        match = re.search(pattern, normalized)
        if match:
            return f"Baseline evidence: {truncate_text(match.group(1), 180)}"
    return insufficient("未发现 Baseline:, compared with, outperform, vs. 或 comparison 等对照信号")


def find_sentence(text: str, markers: list[str]) -> str:
    for sentence in split_sentences(text):
        lower = sentence.lower()
        if any(marker.lower() in lower for marker in markers):
            return truncate_text(sentence)
    return ""


def split_sentences(text: str) -> list[str]:
    normalized = normalize_space(text)
    if not normalized:
        return []
    sentences = re.split(r"(?<=[.!?。！？])\s+", normalized)
    return [sentence.strip() for sentence in sentences if sentence.strip()]


def truncate_text(value: str, limit: int = 260) -> str:
    normalized = normalize_space(value)
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 3]}..."


def insufficient(reason: str) -> str:
    return f"{INSUFFICIENT_PREFIX}：{reason}。"


def has_signal(value: str) -> bool:
    normalized = normalize_space(value)
    return bool(normalized) and not normalized.startswith(INSUFFICIENT_PREFIX)


def render_signal_summary(signals: PaperSignals) -> str:
    return (
        f"task={signals.task}; method={signals.method}; dataset={signals.dataset}; "
        f"metric={signals.metric}; baseline={signals.baseline}; claim={signals.claim}; limitation={signals.limitation}; "
        f"type={signals.contribution_type}; contribution_evidence={signals.contribution_evidence}"
    )


def missing_signal_sentence(signals: PaperSignals, fields: list[str]) -> str:
    # Missing fields are already explicit in PaperSignals. Repeating a generic
    # boundary sentence across sections made artifacts and memories unreadable.
    return ""


def unique_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def infer_focus(title: str, context: str) -> str:
    text = f"{title} {context}".lower()
    if "hallucination" in text or "幻觉" in text:
        return "vision-language model hallucination 是否能被更细粒度、更证据化地评测"
    if "ground" in text or "evidence" in text or "faithful" in text:
        return "模型输出是否真正依赖可验证证据，而不是依赖语言先验或数据捷径"
    if "benchmark" in text or "evaluation" in text:
        return "现有 benchmark 是否真实测到了目标能力，而不是测到数据偏差或模板捷径"
    if "agent" in text or "workflow" in text:
        return "科研 agent 的任务流程是否能被拆解、追踪和可靠复用"
    return "论文所定义的 AI 能力或失败模式是否能被清晰建模、测量和验证"


def infer_limitation(focus: str) -> str:
    if "hallucination" in focus or "证据" in focus:
        return "最终答案正确率无法区分真实视觉理解和偶然猜对"
    if "benchmark" in focus:
        return "benchmark 可能混入数据偏差、模板线索和不真实的分布假设"
    if "agent" in focus:
        return "只展示最终回答，缺少 plan、tool call、artifact 和失败恢复记录"
    return "评价目标、实验设置和失败模式之间缺少可验证映射"


def infer_weakest_assumption(focus: str) -> str:
    if "hallucination" in focus or "证据" in focus:
        return "最脆弱假设：标注或指标能代表模型真实使用的视觉证据。若模型答对但证据链错误，论文的核心判断会被削弱。"
    if "benchmark" in focus:
        return "最脆弱假设：benchmark 分布足以代表真实任务分布。若模型只利用模板或数据偏差，结论会高估能力。"
    if "agent" in focus:
        return "最脆弱假设：任务流程可被固定 schema 覆盖。若真实科研任务需要频繁改写目标，固定流程会变得僵硬。"
    return "最脆弱假设：论文定义的评价对象和真实目标能力一致。只要二者错位，实验结论就会变得不可泛化。"


def build_method_pipeline_section(signals: PaperSignals) -> str:
    if not has_signal(signals.method):
        return (
            "当前证据不足：标题、摘要和可选正文没有给出明确方法机制。"
            "因此不能把这篇论文写成完整 pipeline。需要补充 PDF 中的方法/实验段后，再拆成："
            "Input（任务输入与数据来源）-> Processing（模型、训练、prompt、评测协议或数据构造步骤）-> "
            "Output（预测、指标、错误类型或分析结论）。"
        )
    return (
        f"Input: 面向 `{signals.task}` 的样本或实验设置，当前数据集信号为 `{signals.dataset}`。\n"
        f"Processing: {signals.method}\n"
        f"Output: 用 `{signals.metric}` 相对 `{signals.baseline}` 支撑或反驳 `{signals.claim}`。\n"
        "真实例子：如果输入是一篇 VLM hallucination benchmark 论文，不能只记录最终答案是否正确，"
        "还要记录视觉证据是否被使用、负样本如何构造、指标是否能暴露 answer-correct-evidence-wrong 的失败模式。"
        f"{missing_signal_sentence(signals, ['dataset', 'metric', 'baseline', 'claim'])}"
    )


def build_experiment_logic_section(signals: PaperSignals) -> str:
    if signals.contribution_type == "survey":
        return (
            "这篇论文更像 survey/review，不适合按方法论文写“复现实验”。"
            "实验层面应改为验证它的文献图谱是否完整：它覆盖了哪些范式，遗漏了哪些近三年关键 baseline，"
            "以及分类轴是否能帮助研究者定位真实 gap。"
        )
    if not all(has_signal(getattr(signals, field)) for field in ["claim", "dataset", "metric", "baseline"]):
        return (
            f"Question: {signals.claim}\n"
            "Experiment: 当前证据不足，缺少可闭环的 claim/dataset/metric/baseline 组合。"
            f"{missing_signal_sentence(signals, ['claim', 'dataset', 'metric', 'baseline'])}\n"
            "Answer: 不能直接判断论文实验是否支持 claim；需要补充 PDF 实验表、ablation、baseline 和数据构造细节后再评估。"
        )
    return (
        f"提出了什么问题 -> `{signals.task}` 是否被论文方法真正改善或更好测量。\n"
        f"设计了什么实验 -> 在 `{signals.dataset}` 上使用 `{signals.metric}`，对照 `{signals.baseline}` 来验证 `{signals.claim}`。\n"
        "问题的答案是什么 -> 如果指标提升来自核心机制且失败样本分析能支持 claim，则实验较可信；"
        "如果只在有利 benchmark 上提升或缺少反例切片，则 claim 仍然脆弱。"
    )


def build_takeaways_section(signals: PaperSignals, focus: str) -> str:
    if signals.contribution_type == "survey":
        return (
            "Take-away 不是复现某个模型，而是提取它的文献组织价值：它如何划分问题空间、哪些范式被认为重要、"
            "哪些失败模式仍未解决。读这类论文时要特别检查 survey 的覆盖面和分类轴是否有明确纳入规则。"
        )
    if not all(has_signal(getattr(signals, field)) for field in ["claim", "dataset", "metric"]):
        return (
            "无法判断：当前摘要/PDF 原文没有同时提供 claim、dataset 与 metric，"
            "因此不能把任务归类或通用方法描述写成这篇论文的 take-away。"
        )
    return (
        f"任务层面：这篇论文应被理解为 `{signals.task}` 下的 `{signals.contribution_type}` 工作。"
        f" 证据层面：可信判断依赖 `{signals.claim}`、`{signals.dataset}`、`{signals.metric}` 和 `{signals.baseline}` 是否形成闭环。"
        f" 方法层面：{signals.method}"
        f" 迁移层面：围绕 `{focus}` 做后续研究时，应优先攻击最脆弱假设，而不是只延续论文的平均指标。"
        f"{missing_signal_sentence(signals, ['method', 'dataset', 'metric', 'baseline', 'claim'])}"
    )


def build_weakest_assumption(focus: str, signals: PaperSignals) -> str:
    required_fields = ["claim", "limitation", "dataset", "metric"]
    missing = [field for field in required_fields if not has_signal(getattr(signals, field))]
    if not missing:
        return (
            f"推断性弱假设：原文 limitation `{signals.limitation}` 可能使 `{signals.metric}` 在 `{signals.dataset}` 上"
            f"不足以支持 `{signals.claim}`。该判断锚定上述四项原文信号，仍需回到对应段落复核。"
        )
    return (
        f"无法判断：缺少 {', '.join(missing)} 的摘要/PDF 原文证据，"
        "不能把通用 benchmark 风险或任务假设包装成该论文最脆弱的假设。"
    )


def build_math_section(focus: str, signals: PaperSignals) -> str:
    if not has_signal(signals.metric) and not has_signal(signals.method):
        return (
            "当前证据不足：摘要/正文没有提供可解释的公式、指标或方法机制，因此不应编造数学推导。"
            "补充 PDF 后，应优先解释：每个变量代表什么、优化目标和任务 claim 如何对应、指标是否真的测到目标能力。"
        )
    if "hallucination" in focus or "证据" in focus or "benchmark" in focus or has_signal(signals.metric):
        return (
            f"理论上先把论文目标拆成三个变量：任务对象 `{signals.task}`、评价指标 `{signals.metric}`、核心 claim `{signals.claim}`。"
            "0 基础可以这样理解：平均准确率像总成绩，证据一致性、failure rate 或分层指标像解题过程；"
            "总成绩高但过程错，说明模型能力判断不可靠。若论文有公式，重点检查公式是否真的对应它声称要测的能力。"
        )
    if "agent" in focus:
        return (
            "科研 agent 工作更偏系统流程，数学核心通常不是损失函数，而是状态转移："
            "task -> plan -> tool call -> observation -> artifact -> next step。"
            "理论直觉是把不可控的长回答拆成可检查的中间状态，从而降低幻觉和不可追踪风险。"
        )
    return (
        "当前输入没有足够信息判断论文是否包含关键数学推导。这里仅保留待核验问题："
        "如果后续提供论文正文或公式段落，再解释每个变量、目标函数和理论假设。"
    )


def build_minimal_reproduction(signals: PaperSignals, title: str) -> str:
    if signals.contribution_type == "survey":
        return (
            "这篇论文更像 survey/review，不应作为一周复现实验 anchor。"
            "更合适的一周任务是：用它的分类轴抽取 10 篇候选方法/benchmark 论文，检查是否遗漏近三年关键 baseline，"
            "并产出一个可复现论文图谱，而不是复现模型性能。"
        )
    required_fields = ["claim", "dataset", "metric", "baseline"]
    missing = [field for field in required_fields if not has_signal(getattr(signals, field))]
    if missing:
        checklist = "\n".join(
            f"- [ ] 补充 {field}: {unblock_hint_for_signal(field)}"
            for field in missing
        )
        return (
            "Status: blocked\n"
            f"当前缺少 {', '.join(missing)}，不能生成可信的一周最小复现实验。\n"
            "Unblock checklist:\n"
            f"{checklist}\n"
            "补齐后，最小复现必须同时绑定 claim + dataset + metric + baseline；否则只会退化成泛泛跑模型。"
        )
    return (
        "Status: ready\n"
        f"Claim to test: `{signals.claim}`\n"
        f"Minimal dataset/subset: 从 `{signals.dataset}` 中抽 50-100 条与核心失败模式直接相关的样本。\n"
        f"Baseline: {signals.baseline}；同时加入一个 simple/no-op baseline。\n"
        "Compute: 优先单卡推理或 API 推理，不做大规模训练。\n"
        f"Metric: 同时记录论文指标 `{signals.metric}` 和一个反例指标。\n"
        "Steps: 1) 复现输入格式；2) 跑 baseline；3) 按论文指标和反例指标同时评价；4) 手动检查失败样本；5) 写出复现实验报告。\n"
        f"Success criterion: 在小规模设置下观察到 `{title}` 的核心现象，并能定位至少一类稳定失败模式。\n"
        "Failure criterion: 现象只出现在少量样本或高度依赖人工挑选，无法支持论文主张。"
    )


def unblock_hint_for_signal(field: str) -> str:
    hints = {
        "claim": "从 introduction/abstract/results 中找到 Claim: ... 或 we show/demonstrate 句子。",
        "dataset": "从 experiment setup 中找到 Dataset: ... 或 benchmark/subset 名称。",
        "metric": "从 evaluation metrics 中找到 Metric: ...，至少包含论文主指标。",
        "baseline": "从 comparisons 中找到 Baseline: ...、compared with、vs. 或 outperform 对照对象。",
    }
    return hints.get(field, "补充原文证据。")


def build_counterexample(signals: PaperSignals, focus: str) -> str:
    if all(has_signal(getattr(signals, field)) for field in ["claim", "dataset", "metric"]):
        return (
            f"原文信号表明待检验 claim 是 `{signals.claim}`。围绕 `{signals.dataset}` 构造目标不变但分布、证据或模板被破坏的样本，"
            f"再继续用 `{signals.metric}` 评估。若反例失败，才能反驳该 claim 的泛化假设。"
        )
    return (
        "无法判断：摘要/PDF 原文尚未同时给出可测试 claim、dataset 与 metric。"
        "不能把通用的 counterexample-first 模板冒充成该论文的反例设计；请先补齐实验段原文。"
    )


def build_follow_up_idea(signals: PaperSignals, focus: str) -> str:
    if not all(has_signal(getattr(signals, field)) for field in ["claim", "limitation", "dataset", "metric"]):
        return (
            "无法判断：没有同时定位该论文的 claim、limitation、dataset 与 metric 原文证据。"
            "在这些字段缺失时，不提出论文专属 follow-up，避免把通用 benchmark 批判包装成新 idea。"
        )
    limitation = signals.limitation
    return (
        f"Follow-up idea（推断）：从原文 limitation `{limitation}` 出发，围绕 `{signals.dataset}` 中的 `{signals.claim}` "
        f"设计一个能暴露该限制的评测切片，并继续用 `{signals.metric}` 检查它是否成立。"
        "这是一条待验证推断，而不是论文已经证明的结论；下一步需要先在原文实验设置内验证该限制是否稳定出现。"
    )


def render_card_markdown(
    card: DeepPaperCard,
    paper: dict[str, Any],
    full_text: dict[str, Any] | None = None,
) -> str:
    provenance = full_text or {}
    boundary = "" if card.evidence_level == "full_text" else evidence_boundary_sentence(card.evidence_level)
    header = [
        f"# {card_markdown_title(card.evidence_level)}",
        f"Paper: {card.paper_title}",
        f"Authors: {paper.get('authors') or 'unknown'}",
        f"Venue/Year: {paper.get('venue') or paper.get('source') or 'unknown'} / {paper.get('year') or 'unknown'}",
        f"Evidence level: {card.evidence_level}",
        f"Full-text status: {provenance.get('status') or 'not_available'}",
        f"Full-text source: {provenance.get('source') or 'none'}",
        f"PDF URL: {provenance.get('pdf_url') or paper.get('pdf_url') or 'none'}",
        f"Parsed pages/chars: {provenance.get('page_count') or 0} / {provenance.get('character_count') or 0}",
        f"Full-text note: {provenance.get('error') or 'none'}",
        f"Evidence boundary: {boundary or 'PDF 文本已解析；关键 claim 仍需回原文页码、表格和公式复核。'}",
        "",
        "## Paper Signals",
        f"- Task: {card.signals.task}",
        f"- Contribution type: {card.signals.contribution_type}",
        f"- Method: {card.signals.method}",
        f"- Dataset: {card.signals.dataset}",
        f"- Metric: {card.signals.metric}",
        f"- Baseline: {card.signals.baseline}",
        f"- Claim: {card.signals.claim}",
        f"- Limitation: {card.signals.limitation}",
        f"- Missing signals: {', '.join(card.signals.missing_signals) if card.signals.missing_signals else 'none'}",
        "",
    ]
    sections = [f"## {section.title}\n\n{section.content}" for section in card.sections]
    return "\n".join(header + sections)


def card_markdown_title(evidence_level: str) -> str:
    if evidence_level == "full_text":
        return "Full-text Paper Card"
    if evidence_level == "abstract_only":
        return "Abstract-level Paper Card"
    return "Metadata Reading Outline"


def render_card_json(
    card: DeepPaperCard,
    paper: dict[str, Any],
    full_text: dict[str, Any] | None = None,
    updated_at: str = "",
) -> str:
    paper_id = paper.get("id") or ""
    return json.dumps(
        {
            "schema_version": "paper_card.v2",
            "paper_id": paper_id,
            "updated_at": updated_at,
            "paper": {
                "id": paper_id,
                "project_id": paper.get("project_id") or "",
                "title": paper.get("title") or card.paper_title,
                "authors": paper.get("authors") or "",
                "abstract": paper.get("abstract") or "",
                "year": paper.get("year") or "",
                "type": paper.get("type") or "",
                "venue": paper.get("venue") or "",
                "source": paper.get("source") or "",
                "url": paper.get("url") or "",
                "pdf_url": paper.get("pdf_url") or "",
                "priority": paper.get("priority") or "",
            },
            "card": card.to_dict(),
            "evidence_level": card.evidence_level,
            "evidence_quality": card.evidence_level,
            "full_text": full_text or {
                "status": "not_available",
                "pdf_url": paper.get("pdf_url") or "",
                "source": "",
                "page_count": 0,
                "character_count": 0,
                "error": "",
            },
        },
        ensure_ascii=False,
        indent=2,
    )


def paper_slug(title: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return normalized[:64] or "paper"


def summarize_context(context: str) -> str:
    if not context:
        return "当前只提供了标题或元数据，因此分析会明确标记为基于有限信息的结构化推断。"
    if len(context) <= 280:
        return context
    return f"{context[:277]}..."


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()
