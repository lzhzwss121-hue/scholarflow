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
class DeepPaperCard:
    paper_title: str
    sections: list[PaperCardSection]
    weakest_assumption: str
    minimal_reproduction: str
    counterexample: str
    follow_up_idea: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "paper_title": self.paper_title,
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
    authors = normalize_space(paper.get("authors") or "unknown authors")
    context = normalize_space(f"{abstract} {extra_context}")
    focus = infer_focus(title, context)
    limitation = infer_limitation(focus)
    weakest_assumption = infer_weakest_assumption(focus)
    minimal_reproduction = build_minimal_reproduction(focus, title)
    counterexample = build_counterexample(focus)
    follow_up = build_follow_up_idea(focus)

    sections = [
        PaperCardSection(
            "research_problem",
            "1. 研究问题与背景",
            (
                f"论文 `{title}` ({year}, {venue}) 关注的问题可以先理解为：{focus}。"
                f" 从背景上看，这类工作重要是因为 AI 系统的整体分数经常掩盖具体失败模式，"
                f"而科研任务需要知道模型为什么成功、在哪里失败、失败是否可复现。"
                f" 当前输入中的摘要线索为：{summarize_context(context)}"
                f" 解决这个问题的价值在于把模糊的能力判断转成可比较、可验证、可复用的研究资产。"
            ),
        ),
        PaperCardSection(
            "prior_work",
            "2. 已有研究与不足",
            (
                f"这个问题通常并不是完全没人做过，而是之前的解决方式存在 `{limitation}`。"
                f" 典型 prior work 往往依赖单一 benchmark、最终准确率或粗粒度人工标签。"
                f"这些做法可以回答“模型整体是否更强”，但不一定能回答“失败来自数据、证据、指标还是推理路径”。"
                f"因此本论文真正要补的是一个更可诊断的研究切口，而不只是再报一个分数。"
            ),
        ),
        PaperCardSection(
            "author_reasoning",
            "3. 作者可能的思考路径重建",
            (
                "以下是 ScholarFlow 的推断性重建，不把论文自己的贡献倒用为前提："
                f" 研究者可能先观察到 `{focus}` 中存在稳定但未被充分解释的失败模式；"
                "再看到已有 benchmark 或方法只能给出粗粒度结论，无法定位具体失败原因；"
                "于是自然会想到把问题拆成更小的可观测变量，例如输入条件、证据需求、输出质量、评价指标和反例集合。"
                "这个思路的 inspiration 更可能来自 prior work 的盲点和实验观察，而不是突然提出一个全新模块。"
            ),
        ),
        PaperCardSection(
            "intuition",
            "4. 核心 Intuition",
            (
                f"核心 intuition 是：不要只问模型是否表现好，而要问 `{focus}` 是否能被明确暴露、测量和反驳。"
                "换句话说，论文的本质不是“让模型更大”，而是让研究对象变得更可诊断。"
                "这个 idea 合理，是因为很多 AI 失败并不会体现在最终平均分上，而会体现在特定输入、证据链或评价切片中。"
            ),
        ),
        PaperCardSection(
            "method_pipeline",
            "5. 方法 Pipeline 与真实例子",
            (
                "Input: 一篇论文的任务设定、摘要、实验 claim 和候选样本。\n"
                f"Processing: 先识别 `{focus}`，再拆出该问题依赖的输入条件、模型行为、评价标准和失败模式。\n"
                "Intermediate states: 形成 paper table、claim list、failure-mode list、可复现实验子集。\n"
                "Output: 一个能够说明问题、方法、实验逻辑和弱点的 structured paper card。\n"
                "例子：如果输入是一篇 VLM hallucination benchmark 论文，处理过程应把“答案是否正确”和“视觉证据是否被正确使用”分开，"
                "输出则应包含哪些样本最能暴露幻觉、哪些指标可能失真，以及怎样用一周时间验证一个核心 claim。"
            ),
        ),
        PaperCardSection(
            "math_theory",
            "6. 数学与理论解释",
            build_math_section(focus),
        ),
        PaperCardSection(
            "experiment_logic",
            "7. 实验逻辑与 Claim 验证",
            (
                "Question: 论文提出的诊断切口是否真的能暴露原有方法看不到的问题？\n"
                "Experiment: 应设计对照实验，把整体指标、分层指标、失败样本和 baseline 行为分开观察。\n"
                "Answer: 如果新切口能稳定发现 baseline 的隐藏失败，并且这些失败不是标注噪声或数据偶然性造成的，"
                "那么实验支持论文 claim；否则 claim 只说明该数据集上有现象，并不足以证明方法具有一般性。"
            ),
        ),
        PaperCardSection(
            "takeaways",
            "8. Take-aways",
            (
                f"方法层面：围绕 `{focus}` 的工作应优先建立可诊断对象，而不是只优化平均分。"
                " 实验层面：claim 需要用对照、分层和反例来验证。"
                " 研究定位层面：强 idea 往往来自“已有评价无法暴露某类失败”的具体缺口。"
                " 可迁移经验：把复杂能力拆成可观测变量，是从读论文走向做研究的重要步骤。"
            ),
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
    ]

    return DeepPaperCard(
        paper_title=title,
        sections=sections,
        weakest_assumption=weakest_assumption,
        minimal_reproduction=minimal_reproduction,
        counterexample=counterexample,
        follow_up_idea=follow_up,
    )


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


def build_math_section(focus: str) -> str:
    if "hallucination" in focus or "证据" in focus or "benchmark" in focus:
        return (
            "这类论文通常不一定依赖复杂数学推导，更关键的是指标定义。"
            "可以从 0 基础理解为：最终分数不是一个单独数字，而应拆成多个可解释变量，"
            "例如 answer accuracy、evidence consistency、failure rate、分层样本难度。"
            "直觉上，平均准确率像总成绩，证据一致性像解题过程；总成绩高但过程错，说明模型能力判断不可靠。"
            "如果论文有公式，应重点检查公式是否真的对应它声称要测的能力。"
        )
    if "agent" in focus:
        return (
            "科研 agent 工作更偏系统流程，数学核心通常不是损失函数，而是状态转移："
            "task -> plan -> tool call -> observation -> artifact -> next step。"
            "理论直觉是把不可控的长回答拆成可检查的中间状态，从而降低幻觉和不可追踪风险。"
        )
    return (
        "当前输入没有足够信息判断论文是否包含关键数学推导。Phase 7 不应编造公式。"
        "如果后续提供论文正文或公式段落，ScholarFlow 再解释每个变量、目标函数和理论假设。"
    )


def build_minimal_reproduction(focus: str, title: str) -> str:
    return (
        f"Claim to test: `{title}` 中最核心的一个 claim 是否能在小规模设置下复现。\n"
        "Minimal dataset/subset: 50-100 条与核心失败模式直接相关的样本。\n"
        "Baseline: 选择一个公开可调用的强 baseline 和一个简单 baseline。\n"
        "Compute: 优先单卡推理或 API 推理，不做大规模训练。\n"
        "Steps: 1) 复现输入格式；2) 跑 baseline；3) 按论文指标和一个反例指标同时评价；4) 手动检查失败样本；5) 写出复现实验报告。\n"
        "Success criterion: 能观察到论文 claim 中描述的核心现象，并能定位至少一类稳定失败模式。\n"
        "Failure criterion: 现象只出现在少量样本或高度依赖人工挑选，无法支持论文主张。\n"
        f"Expected risks: `{focus}` 可能依赖原论文未公开的标注、过滤规则或 prompt 细节。"
    )


def build_counterexample(focus: str) -> str:
    if "hallucination" in focus or "证据" in focus:
        return (
            "设计一个答案容易猜对但视觉证据被遮挡、冲突或替换的样本集。"
            "如果模型仍然高置信输出正确答案，但 grounding 或证据解释错误，"
            "就能反驳“最终答案分数足以代表真实视觉理解”的隐含假设。"
        )
    if "benchmark" in focus:
        return (
            "构造一组语义等价但模板、选项顺序、物体频率或上下文先验被打乱的样本。"
            "如果模型分数大幅下降，说明 benchmark 可能测到捷径而非目标能力。"
        )
    return (
        "把论文方法放到一个目标不变但输入分布、评价约束或用户需求发生变化的场景中。"
        "如果方法无法保持核心 claim，就说明它依赖了未显式说明的分布假设。"
    )


def build_follow_up_idea(focus: str) -> str:
    return (
        f"Follow-up idea: 从 `{focus}` 出发，建立一个“反例优先”的诊断协议：先生成能攻击核心假设的样本，"
        "再反向设计评价指标和最小实验，而不是先固定 benchmark 再报告平均分。"
        "它不是简单增量，因为它改变了研究问题的入口：从优化已有指标，转向发现并形式化最脆弱失败模式。"
        "潜在价值是让后续方法必须解释为什么能通过反例，而不只是为什么在标准数据上更高分。"
    )


def render_card_markdown(card: DeepPaperCard, paper: dict[str, Any]) -> str:
    header = [
        "# Deep Paper Card",
        f"Paper: {card.paper_title}",
        f"Authors: {paper.get('authors') or 'unknown'}",
        f"Venue/Year: {paper.get('venue') or paper.get('source') or 'unknown'} / {paper.get('year') or 'unknown'}",
        "",
    ]
    sections = [f"## {section.title}\n\n{section.content}" for section in card.sections]
    return "\n".join(header + sections)


def render_card_json(card: DeepPaperCard, paper: dict[str, Any]) -> str:
    return json.dumps(
        {
            "paper": {
                "title": paper.get("title") or card.paper_title,
                "authors": paper.get("authors") or "",
                "year": paper.get("year") or "",
                "venue": paper.get("venue") or "",
                "source": paper.get("source") or "",
                "url": paper.get("url") or "",
            },
            "card": card.to_dict(),
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
