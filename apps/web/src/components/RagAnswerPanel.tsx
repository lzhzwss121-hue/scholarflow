import {
  AlertTriangle,
  BookOpenText,
  CheckCircle2,
  ExternalLink,
  FileSearch,
  Gauge,
  ShieldCheck,
} from "lucide-react";
import type {
  ApiRagAnswerResponse,
  ApiRagQualityAssessment,
  ApiRagSearchHit,
} from "@scholarflow/schemas";

export function RagAnswerPanel({ result }: { result: ApiRagAnswerResponse | null }) {
  if (!result) {
    return (
      <section className="rag-intro-panel" aria-label="rag answer introduction">
        <FileSearch size={21} />
        <div>
          <p className="section-kicker">Full-text RAG</p>
          <h2>直接查询论文摘要与 PDF 原文索引</h2>
          <p>
            系统先检索 chunk，再校验每条主张的 citation ID。没有过阈值证据时会拒答；
            摘要命中不会显示成全文结论。
          </p>
        </div>
      </section>
    );
  }

  if (result.status === "no_reliable_hit" || result.answer_kind === "no_answer") {
    return (
      <section className="rag-empty-panel" aria-label="rag no reliable hit">
        <AlertTriangle size={22} />
        <div>
          <p className="section-kicker">No reliable chunk</p>
          <h2>当前原文索引无法可靠回答</h2>
          <p>{result.unanswered_parts[0] || "没有 chunk 达到相关性门槛，系统未生成答案。"}</p>
          <ul>
            <li>先在 Paper Table 检索更直接相关的论文。</li>
            <li>上传关键论文 PDF，把 abstract_only 升级为 full_text。</li>
            <li>在问题中写明任务对象、数据集、指标或失败模式。</li>
          </ul>
          <RetrievalExplanation result={result} compact />
          <RagQualityPanel assessment={result.quality_assessment ?? null} compact />
          <WarningList title="检索状态" items={result.warnings} />
        </div>
      </section>
    );
  }

  const usedCitations = new Set(result.citation_validation.used_citation_ids);
  return (
    <section className="rag-answer-workspace" aria-label="evidence grounded rag answer">
      <header className="rag-answer-heading">
        <div>
          <p className="section-kicker">Evidence-grounded RAG</p>
          <h2>{result.question}</h2>
          <p>
            {result.answer_kind === "grounded_synthesis"
              ? "已生成通过 citation 校验的综合回答。"
              : "当前显示逐字证据摘录，没有把摘录扩写成未经支持的结论。"}
          </p>
        </div>
        <div className="rag-status-cluster" aria-label="rag answer status">
          <span data-status={result.status}>{result.status}</span>
          <span>{result.retrieval.retrieval_mode}</span>
          <span>{result.citations.length} citations</span>
          <span>{result.claims.length} claims</span>
        </div>
      </header>

      <div className="rag-provenance-strip">
        <ShieldCheck size={16} />
        <span>
          生成：{result.generation_provider || "未调用"}
          {result.generation_model ? ` / ${result.generation_model}` : ""}
        </span>
        <span>
          向量：{result.retrieval.provider || "未启用"} / {result.retrieval.embedding_model || "lexical only"}
        </span>
        <span>{result.external_data_transfer ? "本次存在外部数据传输" : "本次全部在本机处理"}</span>
      </div>

      <RetrievalExplanation result={result} />

      <RagQualityPanel assessment={result.quality_assessment ?? null} />

      <div className="rag-answer-body">
        <p>{result.answer}</p>
      </div>

      <div className="rag-claim-grid" aria-label="rag validated claims">
        {result.claims.map((claim, index) => (
          <article key={claim.id}>
            <div className="rag-claim-header">
              <span>{String(index + 1).padStart(2, "0")}</span>
              <strong>{formatEvidenceLevel(claim.evidence_level)}</strong>
              <small>{claim.confidence} confidence</small>
            </div>
            <p>{claim.statement}</p>
            <div className="rag-citation-buttons">
              {claim.citation_ids.map((citationId) => (
                <button
                  key={citationId}
                  type="button"
                  onClick={() => focusCitation(citationId)}
                >
                  [{shortCitation(citationId)}]
                </button>
              ))}
            </div>
          </article>
        ))}
      </div>

      {result.unanswered_parts.length || result.limitations.length ? (
        <div className="rag-boundary-grid">
          <BoundaryList title="当前仍不能回答" items={result.unanswered_parts} />
          <BoundaryList title="证据与生成边界" items={result.limitations} />
        </div>
      ) : null}

      <div className="rag-evidence-heading">
        <div>
          <BookOpenText size={18} />
          <div>
            <p className="section-kicker">Citation inspector</p>
            <h3>逐条核对引用原文</h3>
          </div>
        </div>
        <span>
          used {usedCitations.size} / available {result.citation_validation.available_citation_ids.length}
        </span>
      </div>

      <div className="rag-evidence-list" aria-label="rag citation evidence">
        {result.citations.map((citation) => (
          <CitationEvidenceCard
            citation={citation}
            isUsed={usedCitations.has(citation.citation_id)}
            key={citation.citation_id}
          />
        ))}
      </div>

      {result.citation_validation.rejected_claim_count > 0 ? (
        <div className="rag-validation-warning">
          <AlertTriangle size={17} />
          <span>
            已拒绝 {result.citation_validation.rejected_claim_count} 条未通过证据校验的模型主张；
            它们没有进入上方回答。
          </span>
        </div>
      ) : null}
      <WarningList title="RAG 状态" items={result.warnings} />
    </section>
  );
}

function RagQualityPanel({
  assessment,
  compact = false,
}: {
  assessment: ApiRagQualityAssessment | null;
  compact?: boolean;
}) {
  if (!assessment) {
    return null;
  }
  const scoreLabel =
    assessment.score === null
      ? assessment.quality_status === "safe_refusal"
        ? "拒答通过"
        : "未评分"
      : `${assessment.score.toFixed(1)}/100`;
  const primaryMetrics = [
    ["主张可追溯", formatQualityMetric(assessment.metrics.claim_traceability, "ratio")],
    ["引用完整", formatQualityMetric(assessment.metrics.citation_integrity, "ratio")],
    ["全文覆盖", formatQualityMetric(assessment.metrics.full_text_coverage, "ratio")],
    ["问题覆盖", formatQualityMetric(assessment.metrics.mean_anchor_coverage, "ratio")],
    ["检索均值", formatQualityMetric(assessment.metrics.mean_retrieval_score, "score")],
  ];
  const problemChecks = assessment.checks.filter(
    (check) => check.status === "warn" || check.status === "fail",
  );
  return (
    <section
      className={compact ? "rag-quality-panel compact" : "rag-quality-panel"}
      aria-label="rag automated evidence quality"
    >
      <header>
        <div className="rag-quality-title">
          <Gauge size={19} />
          <div>
            <p className="section-kicker">Automated evidence audit</p>
            <h3>证据链质量（不是答案正确率）</h3>
          </div>
        </div>
        <div className="rag-quality-score" data-status={assessment.quality_status}>
          <strong>{scoreLabel}</strong>
          <span>证据链分 · {formatQualityStatus(assessment.quality_status)}</span>
        </div>
      </header>

      {!compact ? (
        <div className="rag-quality-metrics">
          {primaryMetrics.map(([label, value]) => (
            <div key={label}>
              <span>{label}</span>
              <strong>{value}</strong>
            </div>
          ))}
        </div>
      ) : null}

      {assessment.score !== null && !compact ? (
        <div className="rag-quality-meter" aria-label={`evidence quality score ${assessment.score}`}>
          <span style={{ width: `${Math.max(0, Math.min(100, assessment.score))}%` }} />
        </div>
      ) : null}

      {assessment.strengths.length ? (
        <ul className="rag-quality-strengths">
          {assessment.strengths.map((item) => (
            <li key={item}>
              <CheckCircle2 size={15} />
              <span>{item}</span>
            </li>
          ))}
        </ul>
      ) : null}

      {assessment.risk_flags.length ? (
        <div className="rag-quality-risks">
          <strong>仍需人工核验</strong>
          <ul>
            {assessment.risk_flags.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {problemChecks.length ? (
        <details className="rag-quality-checks">
          <summary>查看 {problemChecks.length} 个风险检查与修复建议</summary>
          <div>
            {problemChecks.map((check) => (
              <article data-status={check.status} key={check.id}>
                <span>{check.status === "fail" ? "失败" : "警告"}</span>
                <div>
                  <strong>{check.label}</strong>
                  <p>{check.detail}</p>
                  {check.remediation ? <small>{check.remediation}</small> : null}
                </div>
              </article>
            ))}
          </div>
        </details>
      ) : null}
      <p className="rag-quality-disclaimer">{assessment.disclaimer}</p>
    </section>
  );
}

function CitationEvidenceCard({
  citation,
  isUsed,
}: {
  citation: ApiRagSearchHit;
  isUsed: boolean;
}) {
  const pageLabel =
    citation.page_start === null
      ? "页码未知"
      : citation.page_start === citation.page_end
        ? `p.${citation.page_start}`
        : `pp.${citation.page_start}-${citation.page_end}`;
  const matchStrength = citation.match_strength || inferMatchStrength(citation);
  const matchedTerms = citation.matched_query_terms ?? [];
  return (
    <article
      className="rag-evidence-card"
      data-used={isUsed ? "true" : "false"}
      id={citationDomId(citation.citation_id)}
      tabIndex={-1}
    >
      <div className="rag-evidence-meta">
        <span>{isUsed ? "已引用" : "候选证据"}</span>
        <span data-match-strength={matchStrength}>{formatMatchStrength(matchStrength)}</span>
        <span>{formatEvidenceLevel(citation.evidence_level)}</span>
        <span>{citation.section || "section unknown"}</span>
        <span>{pageLabel}</span>
      </div>
      <h4>{citation.paper_title}</h4>
      <p>{citation.text}</p>
      <details className="rag-match-details">
        <summary>为什么命中这段证据</summary>
        <p>
          {citation.match_explanation ||
            `覆盖 ${Math.round((citation.anchor_coverage ?? 0) * 100)}% 的问题锚点；混合分 ${citation.hybrid_score.toFixed(2)}。`}
        </p>
        <div className="rag-match-term-list" aria-label="matched query anchors">
          {matchedTerms.length ? (
            matchedTerms.map((term) => <span key={term}>{term}</span>)
          ) : (
            <span>没有记录直接词面锚点</span>
          )}
        </div>
        <dl>
          <div>
            <dt>关键词</dt>
            <dd>{citation.lexical_score.toFixed(2)}</dd>
          </div>
          <div>
            <dt>向量</dt>
            <dd>{citation.vector_score.toFixed(2)}</dd>
          </div>
          <div>
            <dt>混合</dt>
            <dd>{citation.hybrid_score.toFixed(2)}</dd>
          </div>
          <div>
            <dt>问题覆盖</dt>
            <dd>{Math.round((citation.anchor_coverage ?? 0) * 100)}%</dd>
          </div>
        </dl>
      </details>
      <footer>
        <code>{citation.citation_id}</code>
        {citation.paper_url ? (
          <a href={citation.paper_url} rel="noreferrer" target="_blank">
            论文来源
            <ExternalLink size={13} />
          </a>
        ) : null}
      </footer>
    </article>
  );
}

function RetrievalExplanation({
  result,
  compact = false,
}: {
  result: ApiRagAnswerResponse;
  compact?: boolean;
}) {
  const retrieval = result.retrieval;
  return (
    <section
      className={compact ? "rag-retrieval-explanation compact" : "rag-retrieval-explanation"}
      aria-label="rag retrieval explanation"
    >
      <header>
        <strong>本次检索是怎样得到结果的</strong>
        <span>
          {retrieval.candidate_chunks} 候选 → {retrieval.rejected_by_relevance_gate ?? 0} 门槛拒绝 →{" "}
          {retrieval.returned_hits} 返回
        </span>
      </header>
      {retrieval.query_anchor_terms?.length ? (
        <div className="rag-query-anchor-list">
          <span>问题锚点</span>
          {retrieval.query_anchor_terms.map((term) => <code key={term}>{term}</code>)}
        </div>
      ) : null}
      <p>
        {retrieval.score_explanation ||
          "检索分只表示当前问题与索引片段的匹配强度，不是论文结论或答案的正确率。"}
      </p>
    </section>
  );
}

function BoundaryList({ title, items }: { title: string; items: string[] }) {
  if (!items.length) {
    return null;
  }
  return (
    <section>
      <strong>{title}</strong>
      <ul>
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </section>
  );
}

function WarningList({ title, items }: { title: string; items: string[] }) {
  if (!items.length) {
    return null;
  }
  return (
    <details className="rag-warning-list">
      <summary>{title}（{items.length}）</summary>
      <ul>
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </details>
  );
}

function focusCitation(citationId: string) {
  const target = document.getElementById(citationDomId(citationId));
  target?.scrollIntoView({ behavior: "smooth", block: "center" });
  target?.focus({ preventScroll: true });
}

function citationDomId(citationId: string) {
  return `rag-evidence-${citationId.replace(/[^a-zA-Z0-9_-]/g, "-")}`;
}

function shortCitation(citationId: string) {
  const parts = citationId.split(":");
  return parts.slice(1).join(":") || citationId;
}

function formatEvidenceLevel(level: string) {
  if (level === "full_text") {
    return "PDF 全文";
  }
  if (level === "abstract_only") {
    return "摘要";
  }
  return "元数据";
}

function formatQualityStatus(status: ApiRagQualityAssessment["quality_status"]) {
  if (status === "strong_evidence") {
    return "证据链较强";
  }
  if (status === "safe_refusal") {
    return "安全拒答";
  }
  if (status === "insufficient_evidence") {
    return "证据不足";
  }
  return "需要复核";
}

function inferMatchStrength(
  citation: ApiRagSearchHit,
): ApiRagSearchHit["match_strength"] {
  if (
    (citation.matched_query_terms?.length ?? 0) > 0 &&
    citation.anchor_coverage >= 0.6 &&
    citation.hybrid_score >= 0.35
  ) {
    return "strong";
  }
  if (citation.anchor_coverage >= 0.3 || citation.hybrid_score >= 0.55) {
    return "moderate";
  }
  return "borderline";
}

function formatMatchStrength(strength: ApiRagSearchHit["match_strength"]) {
  if (strength === "strong") {
    return "强命中";
  }
  if (strength === "moderate") {
    return "中等命中";
  }
  return "门槛命中";
}

function formatQualityMetric(value: number | undefined, kind: "ratio" | "score") {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "—";
  }
  return kind === "ratio" ? `${Math.round(value * 100)}%` : value.toFixed(2);
}
