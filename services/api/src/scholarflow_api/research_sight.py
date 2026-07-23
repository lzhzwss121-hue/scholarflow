from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from scholarflow_api.baseline_map import BaselineMap
from scholarflow_api.evidence import EvidencePack, EvidenceSnippet, build_paper_evidence_pack
from scholarflow_api.paper_card import PaperSignals, SignalEvidence, SignalEvidenceRef


@dataclass
class ResearchSightJudgment:
    field: str
    evidence_snippet_id: str
    confidence: str
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


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
    critique_evidence: list[ResearchSightJudgment]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["evidence_pack"] = self.evidence_pack.to_dict()
        data["critique_evidence"] = [judgment.to_dict() for judgment in self.critique_evidence]
        return data


def build_research_sight(
    paper: dict[str, Any],
    sections: list[dict[str, Any]],
    baseline_map: BaselineMap,
    direction: str,
    signals: PaperSignals | dict[str, Any] | None = None,
) -> ResearchSight:
    text = paper_text(paper, sections)
    title = normalize_space(paper.get("title", "该论文"))
    baseline_reference = pick_baseline_reference(paper, baseline_map)
    signal_view = normalize_signals(signals)
    method_family = infer_method_family(f"{text} {signal_view.method}")
    contribution_type = signal_view.contribution_type or infer_contribution_type(text)
    benchmark_risk = baseline_map.evaluation_risks[0] if baseline_map.evaluation_risks else "当前评估风险需要继续补充。"
    evidence_pack = build_paper_evidence_pack(paper, sections, direction)
    supported_signal_fields = append_signal_evidence_snippets(evidence_pack, paper, signal_view)
    evidence_profile = build_evidence_profile(evidence_pack)
    source_evidence = first_source_evidence(evidence_pack)
    if source_evidence is None:
        values = build_evidence_bounded_sight(
            title=title,
            source_evidence=source_evidence,
            missing_required=["claim", "dataset", "metric", "baseline", "limitation"],
            contribution_type=contribution_type,
        )
    else:
        values = build_signal_aware_sight_values(
            title=title,
            text=text,
            direction=direction,
            baseline_map=baseline_map,
            baseline_reference=baseline_reference,
            method_family=method_family,
            contribution_type=contribution_type,
            benchmark_risk=benchmark_risk,
            signals=signal_view,
        )
        values = apply_field_evidence_boundaries(
            values,
            signals=signal_view,
            supported_signal_fields=supported_signal_fields,
            contribution_type=contribution_type,
        )
    critique_evidence = build_critique_evidence(values, evidence_profile, contribution_type)

    return ResearchSight(
        motivation_sharpness=values["motivation_sharpness"],
        solution_elegance=values["solution_elegance"],
        evaluation_integrity=values["evaluation_integrity"],
        paradigm_inspiration=values["paradigm_inspiration"],
        why_good=values["why_good"],
        why_not_good=values["why_not_good"],
        better_angle=values["better_angle"],
        baseline_comparison=values["baseline_comparison"],
        next_step_proposal=values["next_step_proposal"],
        evidence_pack=evidence_pack,
        critique_evidence=critique_evidence,
    )


def apply_field_evidence_boundaries(
    values: dict[str, str],
    *,
    signals: PaperSignals,
    supported_signal_fields: set[str],
    contribution_type: str,
) -> dict[str, str]:
    if contribution_type == "survey":
        return values
    requirements = {
        "motivation_sharpness": ["claim"],
        "solution_elegance": ["method"],
        "evaluation_integrity": ["claim", "dataset", "metric"],
        "paradigm_inspiration": ["method"],
        "why_good": ["claim", "dataset", "metric"],
        "why_not_good": ["claim", "dataset", "metric"],
        "better_angle": ["claim", "dataset", "metric"],
        "baseline_comparison": ["baseline"],
        "next_step_proposal": ["claim", "dataset", "metric"],
    }
    bounded = dict(values)
    for field, required_fields in requirements.items():
        missing = [
            signal_field
            for signal_field in required_fields
            if not has_research_signal(getattr(signals, signal_field))
            or signal_field not in supported_signal_fields
        ]
        if missing:
            bounded[field] = (
                f"无法判断：该字段缺少 {', '.join(missing)} 的可定位原文证据；"
                "其他已提取字段不受此项缺失影响。"
            )
    if not has_research_signal(signals.limitation):
        for field in ["why_not_good", "better_angle"]:
            if not bounded[field].startswith("无法判断"):
                bounded[field] = (
                    "待验证推断（作者未明确陈述 limitation）："
                    f"{bounded[field]}"
                )
    return bounded


def build_evidence_bounded_sight(
    title: str,
    source_evidence,
    missing_required: list[str],
    contribution_type: str,
) -> dict[str, str]:
    if source_evidence is None:
        evidence_note = "事实证据：无法找到 metadata.abstract 或 pdf.full_text 原文片段。"
    else:
        evidence_note = (
            f"事实证据（{source_evidence.id}，{source_evidence.source}）："
            f"{truncate_evidence(source_evidence.text)}"
        )
    missing = ", ".join(missing_required) if missing_required else "方法或评测细节"
    unknown = f"无法判断：缺少 {missing} 的原文证据，不能把通用科研批判写成该论文结论。"
    if contribution_type == "survey" and source_evidence is not None:
        return {
            "motivation_sharpness": f"{evidence_note} 推断：它可能用于组织文献，但分类价值仍需核验。",
            "solution_elegance": "无法判断：没有足够原文说明其分类轴或纳入标准。",
            "evaluation_integrity": "无法判断：survey 不应按方法论文的实验模板评价；需要原文覆盖范围与纳入规则。",
            "paradigm_inspiration": "无法判断：需要原文证明它连接了哪些此前分离的路线。",
            "why_good": "无法判断：当前不能从有限片段确认其文献图谱价值。",
            "why_not_good": "无法判断：当前不能从有限片段确认其遗漏、选择偏差或覆盖缺口。",
            "better_angle": "无法判断：先补充 survey 的分类轴、纳入规则与代表论文证据。",
            "baseline_comparison": "无法判断：缺少可核验的 baseline map 证据。",
            "next_step_proposal": "下一步：回到摘要或全文，抽取分类轴、纳入规则与代表论文，再做文献图谱核验。",
        }
    return {
        "motivation_sharpness": f"{evidence_note} 推断：{unknown}",
        "solution_elegance": unknown,
        "evaluation_integrity": unknown,
        "paradigm_inspiration": unknown,
        "why_good": f"无法判断：{title} 的方法或 benchmark 价值缺少可闭环的原文证据。",
        "why_not_good": f"无法判断：不能在缺少 {missing} 时断言它存在某种 benchmark 或机制缺陷。",
        "better_angle": f"无法判断：先补齐 {missing}，再针对该论文的 claim 或 limitation 设计反例。",
        "baseline_comparison": "无法判断：缺少具体 baseline 与比较协议的原文证据。",
        "next_step_proposal": f"下一步：补充 {missing} 的摘要/PDF 原文片段；在此之前不提出该论文专属 follow-up。",
    }


def append_signal_evidence_snippets(
    evidence_pack: EvidencePack,
    paper: dict[str, Any],
    signals: PaperSignals,
) -> set[str]:
    supported: set[str] = set()
    existing_ids = {snippet.id for snippet in evidence_pack.snippets}
    for field, signal_evidence in signals.signal_evidence.items():
        if field not in {"method", "claim", "dataset", "metric", "baseline", "limitation"}:
            continue
        evidence = signal_evidence if isinstance(signal_evidence, SignalEvidence) else None
        if evidence is None or evidence.validation_errors or not evidence.quote:
            continue
        refs = evidence.evidence_refs or [
            SignalEvidenceRef(
                canonical_value=evidence.canonical_value,
                raw_value=evidence.raw_value,
                source=evidence.source,
                section=evidence.section,
                page=evidence.page,
                quote=evidence.quote,
                confidence=evidence.confidence,
                validation_errors=evidence.validation_errors,
            )
        ]
        valid_refs = [ref for ref in refs if not ref.validation_errors and ref.quote]
        if not valid_refs:
            continue
        supported.add(field)
        for index, ref in enumerate(valid_refs):
            source_label = "pdf" if ref.source == "pdf.full_text" else "abstract"
            snippet_id = f"signal_{field}_{source_label}_{index + 1}"
            if snippet_id in existing_ids:
                continue
            evidence_pack.snippets.append(
                EvidenceSnippet(
                    id=snippet_id,
                    source=ref.source,
                    kind={
                        "method": "method",
                        "claim": "evaluation",
                        "dataset": "evaluation",
                        "metric": "evaluation",
                        "baseline": "evaluation",
                        "limitation": "risk",
                    }[field],
                    text=ref.quote[:360],
                    note=(
                        f"PaperSignals.{field}={ref.canonical_value} 的定位证据；"
                        f"section={ref.section or 'unknown'}。"
                    ),
                    confidence=ref.confidence,
                    section=ref.section,
                    page=ref.page,
                ),
            )
            existing_ids.add(snippet_id)

    source_texts = [
        ("pdf.full_text", normalize_space(paper.get("full_text", "")), "high"),
        ("metadata.abstract", normalize_space(paper.get("abstract", "")), "medium"),
    ]
    kind_by_field = {
        "method": "method",
        "claim": "evaluation",
        "dataset": "evaluation",
        "metric": "evaluation",
        "baseline": "evaluation",
        "limitation": "risk",
    }
    for field, kind in kind_by_field.items():
        if field in supported:
            continue
        signal = normalize_space(getattr(signals, field, ""))
        if not has_research_signal(signal):
            continue
        match_terms = signal_match_terms(signal)
        for source, source_text, confidence in source_texts:
            sentence = find_signal_source_sentence(source_text, match_terms)
            if not sentence:
                continue
            supported.add(field)
            snippet_id = f"signal_{field}_{'pdf' if source == 'pdf.full_text' else 'abstract'}"
            if snippet_id not in existing_ids:
                evidence_pack.snippets.append(
                    EvidenceSnippet(
                        id=snippet_id,
                        source=source,
                        kind=kind,
                        text=sentence[:360],
                        note=f"该原文片段用于验证 PaperSignals.{field}，不支持超出片段的结论。",
                        confidence=confidence,
                    ),
                )
                existing_ids.add(snippet_id)
            break
    return supported


def signal_match_terms(signal: str) -> list[str]:
    normalized = re.sub(
        r"^(方法证据|评测/benchmark 构造方法|核心 claim 证据|显式或隐含不足|Baseline evidence|贡献证据)\s*[：:]\s*",
        "",
        normalize_space(signal),
        flags=re.IGNORECASE,
    )
    phrases = [normalize_space(item).lower() for item in re.split(r"[,;/]", normalized) if normalize_space(item)]
    if normalized:
        phrases.append(normalized.lower())
    tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9_.-]{2,}|[\u4e00-\u9fff]{2,}", normalized.lower())
    stop_words = {"the", "and", "with", "from", "that", "this", "evidence", "claim", "method", "baseline"}
    return list(dict.fromkeys([*phrases, *[token for token in tokens if token not in stop_words]]))[:12]


def find_signal_source_sentence(source_text: str, match_terms: list[str]) -> str:
    if not source_text or not match_terms:
        return ""
    sentences = [normalize_space(item) for item in re.split(r"(?<=[.!?。！？])\s+", source_text) if normalize_space(item)]
    for sentence in sentences:
        lower = sentence.lower()
        if any(term in lower for term in match_terms):
            return sentence
    return ""


def build_signal_aware_sight_values(
    title: str,
    text: str,
    direction: str,
    baseline_map: BaselineMap,
    baseline_reference: str,
    method_family: str,
    contribution_type: str,
    benchmark_risk: str,
    signals: PaperSignals,
) -> dict[str, str]:
    if contribution_type == "survey":
        return build_survey_sight(title, direction, baseline_map, signals)
    if contribution_type == "benchmark":
        return build_benchmark_sight(title, benchmark_risk, baseline_map, baseline_reference, signals)
    if contribution_type == "method":
        return build_method_sight(title, baseline_reference, method_family, signals)
    if contribution_type == "system":
        return build_system_sight(title, baseline_reference, signals)
    return build_unknown_sight(title, text, direction, baseline_map, baseline_reference, method_family, signals)


def build_benchmark_sight(
    title: str,
    benchmark_risk: str,
    baseline_map: BaselineMap,
    baseline_reference: str,
    signals: PaperSignals,
) -> dict[str, str]:
    dataset = signal_or_unknown(signals.dataset, "未识别 benchmark/dataset")
    metric = signal_or_unknown(signals.metric, "未识别 metric")
    claim = signal_or_unknown(signals.claim, "未识别核心 claim")
    return {
        "motivation_sharpness": (
            f"`{title}` 的动机锋利度取决于它是否把 `{signals.task}` 中的失败模式转成可构造、可标注、可复查的 benchmark 问题。"
            f"当前 dataset 信号是 `{dataset}`。"
        ),
        "solution_elegance": (
            f"解法优雅性不在模型结构，而在 `{dataset}` 的数据构造、负样本设计和标注协议是否用更少假设暴露失败。"
            "如果只是扩大题库而不改变错误暴露机制，优雅性有限。"
        ),
        "evaluation_integrity": (
            f"评估真实性要看 `{metric}` 是否真的能测到 `{claim}`，尤其是负样本是否足够强、指标是否能区分答案正确与证据错误。"
            f"额外风险：{benchmark_risk}"
        ),
        "paradigm_inspiration": (
            "范式启发性来自把研究入口从“刷平均分”转成“定义失败模式”。"
            f"{alternative_paradigm_sentence(baseline_map)}"
        ),
        "why_good": (
            f"好的地方：它可能用 `{dataset}` 重新定义 `{signals.task}` 应该怎么被测量，"
            f"并用 `{metric}` 逼迫后续方法解释失败模式，而不是只报告总体性能。"
        ),
        "why_not_good": (
            f"脆弱点：如果 `{dataset}` 的负样本、标注或指标 `{metric}` 只覆盖少数有利场景，"
            "这篇 benchmark 会把数据偏差包装成能力评估。"
        ),
        "better_angle": (
            "更好的角度是做 counterexample-first evaluation：先定义能击穿 claim 的反例族，"
            f"再反推 `{metric}` 和采样规则，而不是先固定 benchmark 后报告平均分。"
        ),
        "baseline_comparison": build_type_aware_baseline_comparison(title, baseline_reference, "benchmark/evaluation"),
        "next_step_proposal": (
            f"下一步可以抽取 `{dataset}` 的 50-100 个样本，按 `{metric}` 与一个反例指标同时评价强 baseline，"
            "检查该 benchmark 是否真的暴露稳定失败模式。"
        ),
    }


def build_method_sight(title: str, baseline_reference: str, method_family: str, signals: PaperSignals) -> dict[str, str]:
    method = signal_or_unknown(signals.method, "未识别方法机制")
    dataset = signal_or_unknown(signals.dataset, "未识别 dataset")
    metric = signal_or_unknown(signals.metric, "未识别 metric")
    claim = signal_or_unknown(signals.claim, "未识别 claim")
    trick_risk = infer_method_trick_risk(signals.method)
    return {
        "motivation_sharpness": (
            f"`{title}` 的动机需要落到 `{signals.task}` 的具体瓶颈上。"
            f"当前 claim 是 `{claim}`，需要确认它不是只在 `{dataset}` 上成立。"
        ),
        "solution_elegance": (
            f"解法优雅性要看 `{method}` 是否改变了核心机制。"
            f"当前方法族判断为 `{method_family}`；{trick_risk}"
        ),
        "evaluation_integrity": (
            f"评估真实性取决于 `{dataset}` 与 `{metric}` 是否能支撑 `{claim}`。"
            "如果缺少 ablation、强 baseline 或失败样本分析，方法有效性只能算弱证据。"
        ),
        "paradigm_inspiration": (
            f"范式启发性取决于 `{method_family}` 路线是否改变问题建模。"
            "如果只是 prompt/decoding/scale trick，它更可能是工程增量而非新范式。"
        ),
        "why_good": (
            f"好的地方：如果 `{method}` 真能在 `{dataset}` 上用 `{metric}` 支撑 `{claim}`，"
            "它的价值在于把任务瓶颈转成一个可验证机制，而不是只给出经验调参。"
        ),
        "why_not_good": (
            f"脆弱点：{trick_risk} 还需要排除数据规模、prompt、decoding 或 benchmark-specific tuning 带来的假提升。"
        ),
        "better_angle": build_method_better_angle(method_family, signals),
        "baseline_comparison": build_type_aware_baseline_comparison(title, baseline_reference, method_family),
        "next_step_proposal": (
            f"下一步做最小 ablation：固定 `{dataset}`、`{metric}` 和 baseline，只移除 `{method_family}` 核心组件，"
            "观察 claim 是否仍然成立。"
        ),
    }


def build_survey_sight(title: str, direction: str, baseline_map: BaselineMap, signals: PaperSignals) -> dict[str, str]:
    return {
        "motivation_sharpness": (
            f"`{title}` 的动机不是复现实验，而是为 `{direction}` 建立文献图谱。"
            "它是否有价值，取决于分类轴能否帮助研究者定位真实 gap。"
        ),
        "solution_elegance": (
            "survey 的优雅性来自问题分解和文献组织，而不是模型机制。"
            "需要看它是否用少数清晰维度覆盖 task、method、dataset、metric 和 failure mode。"
        ),
        "evaluation_integrity": (
            "survey 不应按单篇方法论文评价实验真实性；应检查覆盖范围、遗漏论文、分类一致性和是否区分强证据与观点。"
        ),
        "paradigm_inspiration": (
            "范式启发性来自文献图谱是否揭示了未被连接的路线。"
            f"{alternative_paradigm_sentence(baseline_map)}"
        ),
        "why_good": (
            f"好的地方：它可能把 `{signals.task}` 的零散工作整理成可导航地图，帮助用户发现 baseline、benchmark 和开放问题。"
        ),
        "why_not_good": (
            "脆弱点：survey 很容易把已有工作重新分类后误当成新贡献；如果没有明确纳入/排除规则，结论会有选择性偏差。"
        ),
        "better_angle": (
            "更好的角度是把 survey 变成可执行的 gap map：每个类别都绑定代表论文、反例、未验证假设和最小实验入口。"
        ),
        "baseline_comparison": build_type_aware_baseline_comparison(title, pick_first_baseline_title(baseline_map), "survey-map"),
        "next_step_proposal": (
            "下一步不是复现它，而是用它的分类轴回查近三年 10 篇论文，验证是否遗漏关键 baseline 或混淆 benchmark 与方法贡献。"
        ),
    }


def build_system_sight(title: str, baseline_reference: str, signals: PaperSignals) -> dict[str, str]:
    method = signal_or_unknown(signals.method, "未识别系统流程")
    return {
        "motivation_sharpness": f"`{title}` 的动机在于把 `{signals.task}` 做成可执行流程，关键是是否减少人工切换和不可追踪判断。",
        "solution_elegance": f"系统优雅性要看 `{method}` 是否形成清晰状态转移，而不是把多个 API 串成不可解释 pipeline。",
        "evaluation_integrity": "评估真实性应看任务完成率、失败恢复、artifact 可追踪性和人工复核成本，不能只看最终回答质量。",
        "paradigm_inspiration": "系统类工作的范式价值来自改变科研/工程工作流，而不是单个模型指标提升。",
        "why_good": "好的地方：如果流程状态、工具调用和 artifact 都可追踪，它能把长任务从一次性回答变成可审计过程。",
        "why_not_good": "脆弱点：系统可能只在 demo 任务上顺畅，一旦目标变化或工具失败，就暴露出规划和恢复能力不足。",
        "better_angle": "更好的角度是加入失败恢复和证据边界，让每一步都能被用户中断、复核和重跑。",
        "baseline_comparison": build_type_aware_baseline_comparison(title, baseline_reference, "system/workflow"),
        "next_step_proposal": "下一步用 5 个真实科研任务测试流程稳定性，记录每次工具失败、人工介入和 artifact 质量。",
    }


def build_unknown_sight(
    title: str,
    text: str,
    direction: str,
    baseline_map: BaselineMap,
    baseline_reference: str,
    method_family: str,
    signals: PaperSignals,
) -> dict[str, str]:
    return {
        "motivation_sharpness": f"`{title}` 与 `{direction}` 相关，但当前 signals 不完整，不能断言它抓住了核心痛点。",
        "solution_elegance": f"方法信号为 `{signal_or_unknown(signals.method, '未识别方法机制')}`，需要回到 method 部分判断是否存在真正机制创新。",
        "evaluation_integrity": f"评估信号为 `{signal_or_unknown(signals.metric, '未识别 metric')}`；缺少 dataset/metric/claim 时，应按低置信判断。",
        "paradigm_inspiration": f"暂时只能与 `{pick_first_baseline_title(baseline_map) or '候选 baseline'}` 做弱对比，不能轻易说它有范式启发性。",
        "why_good": f"如果 `{title}` 的贡献成立，价值在于把 `{signals.task}` 的某个瓶颈转成可验证对象。",
        "why_not_good": "主要风险是证据链不足：method、dataset、metric 或 claim 缺失会让批判和复现都变成模板化推断。",
        "better_angle": "更好的角度是先补齐 claim/dataset/metric，再设计能反驳该 claim 的一组小反例。",
        "baseline_comparison": build_type_aware_baseline_comparison(title, baseline_reference, method_family),
        "next_step_proposal": "下一步先补充 PDF 方法和实验段，不急于生成一周计划；否则实验 anchor 不可靠。",
    }


def normalize_signals(signals: PaperSignals | dict[str, Any] | None) -> PaperSignals:
    if isinstance(signals, PaperSignals):
        return signals
    if isinstance(signals, dict):
        return PaperSignals(
            task=normalize_space(signals.get("task", "")) or "未识别任务",
            method=normalize_space(signals.get("method", "")),
            dataset=normalize_space(signals.get("dataset", "")),
            metric=normalize_space(signals.get("metric", "")),
            baseline=normalize_space(signals.get("baseline", "")),
            claim=normalize_space(signals.get("claim", "")),
            limitation=normalize_space(signals.get("limitation", "")),
            prior_work_limitation=normalize_space(signals.get("prior_work_limitation", "")),
            contribution_type=normalize_space(signals.get("contribution_type", "")),
            contribution_evidence=normalize_space(signals.get("contribution_evidence", "")),
            missing_signals=list(signals.get("missing_signals", [])) if isinstance(signals.get("missing_signals"), list) else [],
            signal_evidence=normalize_signal_evidence_map(signals.get("signal_evidence")),
        )
    return PaperSignals(
        task="未识别任务",
        method="",
        dataset="",
        metric="",
        baseline="",
        claim="",
        limitation="",
        prior_work_limitation="",
        contribution_type="",
        contribution_evidence="",
        missing_signals=["method", "dataset", "metric", "baseline", "claim", "limitation"],
        signal_evidence={},
    )


def normalize_signal_evidence_map(value: object) -> dict[str, SignalEvidence]:
    if not isinstance(value, dict):
        return {}
    output: dict[str, SignalEvidence] = {}
    for key, item in value.items():
        if isinstance(item, SignalEvidence):
            output[str(key)] = item
            continue
        if not isinstance(item, dict):
            continue
        output[str(key)] = SignalEvidence(
            field=normalize_space(item.get("field", "")) or str(key),
            canonical_value=normalize_space(item.get("canonical_value", "")),
            raw_value=normalize_space(item.get("raw_value", "")),
            source=normalize_space(item.get("source", "")),
            section=normalize_space(item.get("section", "")),
            page=int(item["page"]) if isinstance(item.get("page"), int) else None,
            quote=normalize_space(item.get("quote", "")),
            confidence=normalize_space(item.get("confidence", "")) or "low",
            validation_errors=[
                normalize_space(error)
                for error in item.get("validation_errors", [])
                if normalize_space(error)
            ]
            if isinstance(item.get("validation_errors"), list)
            else [],
            evidence_refs=[
                SignalEvidenceRef(
                    canonical_value=normalize_space(ref.get("canonical_value", "")),
                    raw_value=normalize_space(ref.get("raw_value", "")),
                    source=normalize_space(ref.get("source", "")),
                    section=normalize_space(ref.get("section", "")),
                    page=int(ref["page"]) if isinstance(ref.get("page"), int) else None,
                    quote=normalize_space(ref.get("quote", "")),
                    confidence=normalize_space(ref.get("confidence", "")) or "low",
                    validation_errors=[
                        normalize_space(error)
                        for error in ref.get("validation_errors", [])
                        if normalize_space(error)
                    ]
                    if isinstance(ref.get("validation_errors"), list)
                    else [],
                )
                for ref in item.get("evidence_refs", [])
                if isinstance(ref, dict)
            ]
            if isinstance(item.get("evidence_refs"), list)
            else [],
            availability=(
                normalize_space(item.get("availability", ""))
                or (
                    "verified"
                    if normalize_space(item.get("source", "")) == "pdf.full_text"
                    and not item.get("validation_errors")
                    else "partial"
                )
            ),
        )
    return output


def infer_contribution_type(text: str) -> str:
    if any(term in text for term in ["survey", "review", "overview", "taxonomy"]):
        return "survey"
    if any(term in text for term in ["benchmark", "dataset", "evaluation", "metric"]):
        return "benchmark"
    if any(term in text for term in ["agent", "workflow", "system"]):
        return "system"
    if any(term in text for term in ["method", "model", "architecture", "framework", "training", "decoding"]):
        return "method"
    return "unknown"


def build_evidence_profile(evidence_pack: EvidencePack) -> dict[str, dict[str, str]]:
    profile: dict[str, dict[str, str]] = {}
    for snippet in evidence_pack.snippets:
        if snippet.source not in {"metadata.abstract", "pdf.full_text"}:
            continue
        profile.setdefault(
            snippet.kind,
            {
                "id": snippet.id,
                "confidence": snippet.confidence or evidence_pack.confidence,
                "source": snippet.source,
            },
        )
        signal_match = re.match(r"signal_([a-z_]+)_(?:pdf|abstract)$", snippet.id)
        if signal_match:
            profile[f"signal:{signal_match.group(1)}"] = {
                "id": snippet.id,
                "confidence": snippet.confidence or evidence_pack.confidence,
                "source": snippet.source,
            }
    fallback = next(
        (snippet for snippet in evidence_pack.snippets if snippet.source in {"metadata.abstract", "pdf.full_text"}),
        None,
    )
    profile["default"] = {
        "id": fallback.id if fallback else "none",
        "confidence": fallback.confidence if fallback else evidence_pack.confidence or "low",
        "source": fallback.source if fallback else "missing",
    }
    return profile


def build_critique_evidence(
    values: dict[str, str],
    evidence_profile: dict[str, dict[str, str]],
    contribution_type: str,
) -> list[ResearchSightJudgment]:
    preferred_kinds = {
        "motivation_sharpness": ["signal:claim", "problem", "context", "metadata"],
        "solution_elegance": ["signal:method", "method", "context", "metadata"],
        "evaluation_integrity": ["signal:metric", "signal:dataset", "evaluation", "risk", "context"],
        "paradigm_inspiration": ["signal:method", "context", "method", "metadata"],
        "why_good": ["signal:claim", "signal:method", "method", "evaluation", "context"],
        "why_not_good": ["signal:limitation", "signal:metric", "risk", "evaluation", "context"],
        "better_angle": ["signal:limitation", "signal:claim", "risk", "evaluation", "method"],
        "baseline_comparison": ["signal:baseline", "metadata", "context"],
        "next_step_proposal": ["signal:claim", "signal:dataset", "evaluation", "risk", "method"],
    }
    judgments: list[ResearchSightJudgment] = []
    for field, value in values.items():
        if normalize_space(value).startswith("无法判断"):
            judgments.append(
                ResearchSightJudgment(
                    field=field,
                    evidence_snippet_id="none",
                    confidence="low",
                    rationale="该字段缺少自身所需的可定位原文证据；其他字段的证据不能替代它。",
                ),
            )
            continue
        evidence = select_evidence_for_field(evidence_profile, preferred_kinds.get(field, ["default"]))
        judgments.append(
            ResearchSightJudgment(
                field=field,
                evidence_snippet_id=evidence["id"],
                confidence=adjust_judgment_confidence(evidence["confidence"], contribution_type, field),
                rationale=(
                    f"该判断主要锚定 `{evidence['source']}` 证据；其中事实与推断需要区分，"
                    "如果缺少全文 PDF，应按证据边界复核。"
                    if evidence["id"] != "none"
                    else "无法定位 metadata.abstract 或 pdf.full_text 原文片段；该字段只能标为无法判断。"
                ),
            ),
        )
    return judgments


def select_evidence_for_field(evidence_profile: dict[str, dict[str, str]], kinds: list[str]) -> dict[str, str]:
    for kind in kinds:
        if kind in evidence_profile:
            return evidence_profile[kind]
    return evidence_profile["default"]


def adjust_judgment_confidence(confidence: str, contribution_type: str, field: str) -> str:
    if contribution_type == "survey" and field in {"evaluation_integrity", "next_step_proposal"}:
        return "medium" if confidence == "high" else confidence or "low"
    return confidence or "low"


def signal_or_unknown(value: str, fallback: str) -> str:
    normalized = normalize_space(value)
    if not normalized or normalized.startswith("当前证据不足"):
        return fallback
    return normalized


def alternative_paradigm_sentence(baseline_map: BaselineMap) -> str:
    if baseline_map.alternative_paradigms:
        return f" 应与 `{baseline_map.alternative_paradigms[0].title}` 这类异质范式比较，判断是否真的改变问题入口。"
    return " 当前缺少异质范式参照，不能轻易判断它有 paradigm shift。"


def infer_method_trick_risk(method: str) -> str:
    lower = method.lower()
    if any(term in lower for term in ["prompt", "decoding", "rerank", "chain-of-thought"]):
        return "当前更像 prompt/decoding 层改动，风险是机制贡献被工程技巧放大。"
    if any(term in lower for term in ["large", "scale", "billion", "data"]):
        return "当前存在 scale/data confound，风险是提升来自规模而不是机制。"
    if any(term in lower for term in ["architecture", "state space", "mamba", "attention", "transformer"]):
        return "当前至少有架构或机制信号，但仍需 ablation 证明不是堆模块。"
    if not signal_or_unknown(method, ""):
        return "当前方法机制不足，无法判断是否真的改变了核心机制。"
    return "当前方法机制需要通过 ablation 与强 baseline 排除工程增量。"


def build_method_better_angle(method_family: str, signals: PaperSignals) -> str:
    if method_family == "transformer":
        return (
            "更好的角度是先问是否必须继续修补注意力结构：可以用 state-space、检索约束或更强反例评估，"
            f"重新验证 `{signal_or_unknown(signals.claim, '核心 claim')}`。"
        )
    if method_family == "state-space":
        return "更好的角度是把线性复杂度优势和真实失败模式绑定，而不是只报告速度或平均分。"
    if method_family == "retrieval":
        return "更好的角度是评估检索证据是否改变模型决策，而不只是增加上下文长度。"
    return "更好的角度是从最脆弱假设倒推实验，而不是继续沿着同类方法做局部模块替换。"


def build_type_aware_baseline_comparison(title: str, reference: str, route: str) -> str:
    if reference:
        return (
            f"与 `{reference}` 相比，`{title}` 需要证明自己不是 `{route}` 路线内的弱增量。"
            "关键要看它是否改变了任务定义、机制约束或评价方式。"
        )
    return f"当前候选池缺少明确 baseline，`{title}` 的 `{route}` 优劣判断需要补充经典论文或最新强 baseline。"


def pick_first_baseline_title(baseline_map: BaselineMap) -> str:
    for group in [
        baseline_map.recent_strong_baselines,
        baseline_map.classic_baselines,
        baseline_map.alternative_paradigms,
    ]:
        if group:
            return group[0].title
    return ""


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
    lower = text.lower()
    if any(term in lower for term in ["mamba", "state space", "ssm", "selective scan"]):
        return "state-space"
    if any(term in lower for term in ["transformer", "attention", "vit", "swin"]):
        return "transformer"
    if any(term in lower for term in ["benchmark", "evaluation", "metric"]):
        return "evaluation"
    if any(term in lower for term in ["retrieval", "rag", "memory"]):
        return "retrieval"
    if any(term in lower for term in ["diffusion", "score-based"]):
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


def first_source_evidence(evidence_pack: EvidencePack):
    return next(
        (
            snippet
            for snippet in evidence_pack.snippets
            if snippet.source in {"metadata.abstract", "pdf.full_text"} and normalize_space(snippet.text)
        ),
        None,
    )


def truncate_evidence(value: str, limit: int = 180) -> str:
    normalized = normalize_space(value)
    return normalized if len(normalized) <= limit else f"{normalized[:limit - 3]}..."


def has_research_signal(value: str) -> bool:
    normalized = normalize_space(value)
    return bool(normalized) and not normalized.startswith("当前证据不足") and not normalized.startswith("未识别")
