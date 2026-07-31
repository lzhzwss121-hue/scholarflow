import { useEffect, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  BookOpen,
  BrainCircuit,
  Check,
  CheckCircle2,
  ChevronLeft,
  Download,
  FileText,
  Lightbulb,
  Rocket,
  ShieldCheck,
  Sparkles,
  Target,
} from "lucide-react";
import type {
  ApiArtifactSummary,
  ApiDirectionPaperReading,
  ApiDirectionReviewResponse,
  ApiFullTextProvenance,
  ApiPaperCard,
  ApiProject,
  ApiSignalEvidence,
} from "@scholarflow/schemas";
import type { PaperRow, ViewId } from "../mockData";
import {
  normalizeEvidencePack,
  normalizeResearchSight,
  resolvePaperCardForPaper,
} from "../lib/artifactHydration";
import type { PaperCardMatchSource } from "../lib/artifactHydration";
import type { ApiStatus } from "../types/workflow";
import {
  formatAcademicText,
  formatEvidenceLevel,
  formatResearchSignal,
  formatSignalEvidenceLocation,
} from "./shared/formatters";
import { formatContributionType } from "./shared/decisionFormatters";
import {
  OperationStatusNote,
  ProjectSidebar,
  formatArtifactDate,
} from "./shared/ProductViewRuntime";

export function ProductPaperReaderPanel({
  activeProject,
  apiMessage,
  artifactCount,
  artifactSummaries,
  apiStatus,
  card,
  directionPaperId,
  directionReview,
  isGenerating,
  onGenerate,
  onInputChange,
  onPdfUpload,
  onLoadArtifact,
  onExitDirectionPaper,
  onOpenDirectionPaper,
  onSelectedPaperChange,
  onSelectView,
  papers,
  projectCount,
  selectedPaperId,
  supplementalInput,
}: {
  activeProject: ApiProject | null;
  apiMessage: string;
  artifactCount: number;
  artifactSummaries: ApiArtifactSummary[];
  apiStatus: ApiStatus;
  card: ApiPaperCard | null;
  directionPaperId: string;
  directionReview: ApiDirectionReviewResponse | null;
  isGenerating: boolean;
  onGenerate: () => void;
  onInputChange: (value: string) => void;
  onPdfUpload: (paperId: string, file: File) => void;
  onLoadArtifact: (artifactId: string) => void;
  onExitDirectionPaper: () => void;
  onOpenDirectionPaper: (paperId: string) => void;
  onSelectedPaperChange: (paperId: string) => void;
  onSelectView: (view: ViewId) => void;
  papers: PaperRow[];
  projectCount: number;
  selectedPaperId: string;
  supplementalInput: string;
}) {
  const [activeQuestion, setActiveQuestion] = useState(1);

  useEffect(() => {
    setActiveQuestion(1);
  }, [card, selectedPaperId]);

  const directionReadings = directionReview?.papers ?? [];
  const directionReading = directionReadings.find((reading) => reading.paper.id === directionPaperId) ?? null;
  const effectiveDirectionReading = mergeDirectionReadingWithPaperCard(directionReading, card);

  if (directionPaperId) {
    return (
      <DirectionPaperPage
        canUpload={apiStatus === "online"}
        hasHydratedReview={Boolean(directionReview)}
        isGenerating={isGenerating}
        onBack={onExitDirectionPaper}
        onOpenEvidenceInput={() => onSelectView("paper-reader")}
        onOpenPaper={onOpenDirectionPaper}
        onPdfUpload={onPdfUpload}
        reading={effectiveDirectionReading}
        readings={directionReadings}
        requestedPaperId={directionPaperId}
      />
    );
  }

  const selectedPaper = papers.find((paper) => paper.id === selectedPaperId) ?? papers[0];
  const cardMatch = resolvePaperCardForPaper(card, directionReview, selectedPaper);
  const displayCard = cardMatch?.card ?? null;
  const cardSections = displayCard?.sections ?? [];
  const signals = displayCard?.signals;
  const evidenceLevel = displayCard?.evidence_level ?? "metadata_only";
  const evidenceQualification = displayCard?.evidence_qualification;
  const readerTitle = formatReaderTitle(evidenceLevel, Boolean(displayCard));
  const evidenceBoundary = buildEvidenceBoundary(evidenceLevel);
  const missingEvidence = buildMissingEvidenceChecklist(displayCard);
  const decisionBrief = buildPaperDecisionBrief(displayCard);
  const activeQuestionIndex = cardSections.length
    ? Math.min(Math.max(activeQuestion - 1, 0), cardSections.length - 1)
    : -1;
  const activeSection = activeQuestionIndex >= 0 ? cardSections[activeQuestionIndex] : null;
  const activeSectionContent = activeSection ? parsePaperCardSectionContent(activeSection.content) : null;
  const activeSectionParagraphs = activeSectionContent
    ? splitPaperCardSectionParagraphs(activeSectionContent.primary)
    : [];
  const openSupplementalEvidenceInput = () => {
    if (typeof document === "undefined") {
      return;
    }
    const panel = document.querySelector<HTMLDetailsElement>(".reader-supplemental-input");
    if (!panel) {
      return;
    }
    panel.open = true;
    window.requestAnimationFrame(() => {
      panel.querySelector<HTMLTextAreaElement>("textarea")?.focus();
    });
  };
  const expectedSections = [
    "研究问题与背景",
    "已有研究与不足",
    "作者思考路径重建",
    "核心 intuition",
    "方法 pipeline",
    "数学与理论解释",
    "实验如何验证 claim",
    "Take-aways",
    "最脆弱的假设",
    "一周最小复现实验",
    "反例设计",
    "非增量 follow-up idea",
  ];
  const conciseSignal = (label: string, value: string | undefined) => {
    const normalized = formatResearchSignal(value, "");
    if (!normalized) {
      return "";
    }
    const preview = normalized.length > 72 ? `${normalized.slice(0, 69)}…` : normalized;
    return `${label} · ${preview}`;
  };
  const signalTags = [
    signals?.contribution_type ? `类型 · ${signals.contribution_type}` : "",
    selectedPaper?.year ? `年份 · ${selectedPaper.year}` : "",
    selectedPaper?.venue ? `来源 · ${selectedPaper.venue}` : "",
    conciseSignal("Dataset", signals?.dataset),
    conciseSignal("Metric", signals?.metric),
    conciseSignal("Baseline", signals?.baseline),
  ].filter(Boolean);
  const selectedSummary = selectedPaper?.abstract || selectedPaper?.relation || "";
  const selectedSummaryPreview = selectedSummary.length > 560 ? `${selectedSummary.slice(0, 557)}…` : selectedSummary;

  return (
    <div className="reader-canvas">
      <ProjectSidebar
        activeProject={activeProject}
        activeView="paper-reader"
        artifacts={artifactSummaries}
        artifactCount={artifactCount}
        compact
        onLoadArtifact={onLoadArtifact}
        onSelectView={onSelectView}
        paperCount={papers.length}
        projectCount={projectCount}
      />

      <section className="reader-main-panel">
        <div className="reader-content">
          <button className="back-link" type="button" onClick={() => onSelectView("paper-table")}>
            <ChevronLeft size={16} />
            返回列表
          </button>
          <div className="reader-title-row">
            <div>
              <h1>{readerTitle}</h1>
              <p>
                {selectedPaper?.title ?? "尚未选择论文"}
                {selectedPaper?.venue || selectedPaper?.year ? <span>{selectedPaper.venue || selectedPaper.year}</span> : null}
              </p>
              <small>只展示当前项目真实论文和已生成的 Paper Card；摘要级/元数据级卡片不会被标成完整正文阅读。</small>
            </div>
            <div className="reader-actions">
              <button
                className="gradient-button"
                disabled={apiStatus !== "online" || isGenerating}
                type="button"
                onClick={onGenerate}
              >
                <Rocket size={17} />
                {isGenerating ? "生成中" : "生成 12 条分析"}
              </button>
            </div>
          </div>

          {isGenerating ? <OperationStatusNote apiStatus={apiStatus} message={apiMessage} /> : null}

          <div className="reader-tags">
            {signalTags.length ? (
              signalTags.map((tag) => <span key={tag}>{tag}</span>)
            ) : selectedPaper ? (
              <>
                <span>{selectedPaper.type || "type unknown"}</span>
                <span>{selectedPaper.source || "source unknown"}</span>
                <span>{selectedPaper.year || "year unknown"}</span>
              </>
            ) : (
              <span>等待论文或手动输入</span>
            )}
          </div>

          <article className="summary-card">
            <Sparkles size={23} />
            <div>
              <strong>{displayCard ? `${formatEvidenceLevel(evidenceLevel)}卡片` : "待生成 Paper Card"}</strong>
              <p>{selectedSummaryPreview || "请先在 Paper Table 选择论文，或粘贴摘要/正文片段后生成 Paper Card。"}</p>
              {selectedSummary.length > selectedSummaryPreview.length ? (
                <details className="summary-card-details">
                  <summary>查看完整摘要</summary>
                  <p>{selectedSummary}</p>
                </details>
              ) : null}
              {displayCard?.evidence_level ? (
                <small>
                  Evidence level: {formatEvidenceLevel(displayCard.evidence_level)} · 来源：
                  {formatPaperCardSource(cardMatch?.source ?? displayCard.card_source ?? "manual_unbound")} · 匹配：
                  {cardMatch?.matchedBy ?? "manual_unbound"}
                </small>
              ) : null}
            </div>
          </article>

          <section className="reader-evidence-summary" aria-label="paper card evidence summary">
            <div className={`reader-evidence-level ${evidenceLevel}`}>
              <ShieldCheck size={16} />
              <strong>{formatEvidenceLevel(evidenceLevel)}</strong>
              <span>来源：{formatPaperCardSource(cardMatch?.source ?? displayCard?.card_source ?? "manual_unbound")}</span>
              {evidenceQualification?.level === "full_text" && evidenceQualification.verified ? (
                <span>
                  {evidenceQualification.page_count} 页 / {evidenceQualification.character_count.toLocaleString("zh-CN")} 字符
                </span>
              ) : null}
              {evidenceQualification?.reason ? <span>{evidenceQualification.reason}</span> : null}
              {displayCard?.updated_at || displayCard?.created_at ? (
                <span>更新：{formatArtifactDate(displayCard.updated_at || displayCard.created_at)}</span>
              ) : null}
            </div>
            {evidenceBoundary ? <LimitedEvidenceSummary boundary={evidenceBoundary} /> : null}
            <FullTextProvenanceStatus
              onOpenEvidenceInput={openSupplementalEvidenceInput}
              provenance={displayCard?.full_text}
              updatedAt={displayCard?.updated_at || displayCard?.created_at}
            />

            {displayCard && missingEvidence.length ? (
              <details className="reader-evidence-scope" aria-label="paper card evidence scope">
                <summary>
                  <span>
                    <ShieldCheck size={17} />
                    <strong>待补证据与核验清单</strong>
                  </span>
                  <span>{formatEvidenceLevel(evidenceLevel)}</span>
                </summary>
                <div className="reader-evidence-scope-content">
                  {missingEvidence.length ? (
                    <div>
                      <strong>待补证据</strong>
                      <ul>
                        {missingEvidence.map((item) => (
                          <li key={item}>{item}</li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                </div>
              </details>
            ) : null}
          </section>

          {displayCard ? (
            <section
              className="paper-decision-brief"
              aria-label="paper research decision brief"
              data-testid="paper-research-decision-brief"
            >
              <header>
                <div>
                  <p className="section-kicker">Research decision brief</p>
                  <h2>先判断这篇论文是否值得继续投入</h2>
                </div>
                <span data-readiness={decisionBrief.readiness}>{decisionBrief.label}</span>
              </header>
              <div className="paper-decision-grid">
                {decisionBrief.items.map((item) => (
                  <article key={item.label}>
                    <div className="paper-decision-field-head">
                      <span>{item.label}</span>
                      <small data-source={item.sourceStatus}>{item.sourceLabel}</small>
                    </div>
                    <strong>{item.value}</strong>
                  </article>
                ))}
              </div>
              <div className="paper-decision-next">
                <Target size={17} />
                <div>
                  <strong>建议下一步</strong>
                  <p>{decisionBrief.nextAction}</p>
                </div>
              </div>
              {decisionBrief.evidence.length ? (
                <details className="paper-decision-evidence">
                  <summary>查看任务、方法与主张的原文定位</summary>
                  <dl>
                    {decisionBrief.evidence.map((item) => (
                      <div key={item.label}>
                        <dt>{item.label}</dt>
                        <dd>{item.location}</dd>
                      </div>
                    ))}
                  </dl>
                </details>
              ) : null}
            </section>
          ) : null}

          <details className="reader-supplemental-input">
            <summary>
              <span>
                <FileText size={17} />
                <strong>补充正文证据</strong>
              </span>
              <span>{supplementalInput.trim() ? `${supplementalInput.trim().length} 字` : "可选"}</span>
            </summary>
            <div className="reader-supplemental-input-content">
              <PdfUploadControl
                busy={isGenerating}
                disabled={apiStatus !== "online" || !selectedPaper}
                onUpload={onPdfUpload}
                paperId={selectedPaper?.id ?? ""}
              />
              <div className="reader-input-divider"><span>或粘贴关键正文片段</span></div>
              <label htmlFor="paper-card-supplemental-input">
                粘贴 abstract、method、experiment、表格说明或正文片段
              </label>
              <textarea
                id="paper-card-supplemental-input"
                placeholder="建议优先粘贴方法、实验设置、baseline、ablation 与 failure case；随后点击上方按钮重新生成。"
                value={supplementalInput}
                onChange={(event) => onInputChange(event.target.value)}
              />
              <p>补充内容会作为本次 Paper Card 的证据输入，不会覆盖项目中的原始论文记录。</p>
            </div>
          </details>

          <section className="question-board" aria-label="paper card reading">
            <div className="question-board-head">
              <div>
                <p className="section-kicker">Deep Paper Card</p>
                <h2>12 段科研精读</h2>
              </div>
              <span>{cardSections.length}/12 已生成</span>
            </div>
            {cardSections.length ? (
              <div className="paper-reader-workspace">
                <nav className="paper-reader-toc" aria-label="12 段精读目录">
                  <ol>
                    {cardSections.map((section, index) => {
                      const isActive = activeQuestionIndex === index;
                      return (
                        <li key={`${section.id}-${index}`}>
                          <button
                            aria-controls={isActive ? `paper-reader-section-${index + 1}` : undefined}
                            aria-current={isActive ? true : undefined}
                            className="paper-reader-toc-item"
                            type="button"
                            onClick={() => setActiveQuestion(index + 1)}
                          >
                            <span aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>
                            <strong>{formatPaperCardSectionTitle(section.title)}</strong>
                            <Check size={14} aria-hidden="true" />
                          </button>
                        </li>
                      );
                    })}
                  </ol>
                </nav>

                {activeSection && activeSectionContent ? (
                  <article
                    className="paper-reader-section"
                    id={`paper-reader-section-${activeQuestionIndex + 1}`}
                    tabIndex={-1}
                  >
                    <header>
                      <span>
                        Section {String(activeQuestionIndex + 1).padStart(2, "0")} / {cardSections.length}
                      </span>
                      <h3 data-testid="paper-reader-active-section-heading">{formatPaperCardSectionTitle(activeSection.title)}</h3>
                    </header>

                    <div className="paper-reader-section-body">
                      {activeSectionParagraphs.length ? (
                        activeSectionParagraphs.map((paragraph, index) => (
                          <p key={`${activeSection.id}-paragraph-${index}`}>{paragraph}</p>
                        ))
                      ) : (
                        <div className="paper-reader-section-empty" role="status">
                          <strong>本段暂无可定位内容</strong>
                          <span>所需字段已汇总在上方“待补证据与核验清单”。</span>
                        </div>
                      )}
                    </div>

                    {activeSectionContent.outline ||
                    activeSectionContent.evidenceGap ||
                    activeSectionContent.verification ? (
                      <details className="paper-reader-section-notes">
                        <summary>本段核验备注</summary>
                        <dl>
                          {activeSectionContent.outline ? (
                            <div>
                              <dt>阅读定位</dt>
                              <dd>{activeSectionContent.outline}</dd>
                            </div>
                          ) : null}
                          {activeSectionContent.evidenceGap ? (
                            <div>
                              <dt>证据缺口</dt>
                              <dd>{activeSectionContent.evidenceGap}</dd>
                            </div>
                          ) : null}
                          {activeSectionContent.verification ? (
                            <div>
                              <dt>核验问题</dt>
                              <dd>{activeSectionContent.verification}</dd>
                            </div>
                          ) : null}
                        </dl>
                      </details>
                    ) : null}

                    <footer className="paper-reader-section-nav" aria-label="精读章节切换">
                      <button
                        disabled={activeQuestionIndex <= 0}
                        type="button"
                        onClick={() => setActiveQuestion(activeQuestionIndex)}
                      >
                        <ChevronLeft size={15} />
                        上一节
                      </button>
                      <span aria-live="polite">
                        {activeQuestionIndex + 1} / {cardSections.length}
                      </span>
                      <button
                        disabled={activeQuestionIndex >= cardSections.length - 1}
                        type="button"
                        onClick={() => setActiveQuestion(activeQuestionIndex + 2)}
                      >
                        下一节
                        <ArrowRight size={15} />
                      </button>
                    </footer>
                  </article>
                ) : null}
              </div>
            ) : (
              <div className="reader-empty-state">
                <BookOpen size={22} />
                <div>
                  <h2>尚未生成 12 条精读</h2>
                  <p>点击“生成 12 条分析”后，系统会基于选中论文或补充文本生成真实 Paper Card。</p>
                </div>
              </div>
            )}
            {!cardSections.length ? (
              <div className="protocol-list compact" aria-label="paper card protocol">
                {expectedSections.map((section, index) => (
                  <div className="protocol-row" key={section}>
                    <span>{String(index + 1).padStart(2, "0")}</span>
                    <p>{section}</p>
                  </div>
                ))}
              </div>
            ) : null}
          </section>
        </div>

        <aside className="reader-aside">
          <section className="key-info-card">
            <h2>关键信息</h2>
            <div className="key-info-grid">
              <div>
                <strong>{selectedPaper?.year || "N/A"}</strong>
                <span>Year</span>
              </div>
              <div>
                <strong>{selectedPaper?.type || "N/A"}</strong>
                <span>Type</span>
              </div>
              <div>
                <strong>{selectedPaper?.priority || "N/A"}</strong>
                <span>Priority</span>
              </div>
              <div>
                <strong>{displayCard?.evidence_level ? formatEvidenceLevel(displayCard.evidence_level) : "N/A"}</strong>
                <span>Evidence</span>
              </div>
            </div>
          </section>

          <section className="evidence-chain-card">
            <div className="aside-heading compact">
              <h2>生成状态</h2>
              <span>{displayCard ? "已生成" : "待生成"}</span>
            </div>
            <div className="chain-step">
              <span>1</span>
              <div>
                <strong>最脆弱假设</strong>
                <p>{displayCard?.weakest_assumption || "尚未生成，系统不会编造论文局限。"}</p>
              </div>
            </div>
            <div className="chain-step">
              <span>2</span>
              <div>
                <strong>一周最小复现</strong>
                <p>{displayCard?.minimal_reproduction || "需要生成 Paper Card 后才能给出具体实验切口。"}</p>
              </div>
            </div>
            <div className="chain-step">
              <span>3</span>
              <div>
                <strong>证据来源</strong>
                <p>
                  {displayCard?.evidence_level
                    ? `${formatPaperCardSource(cardMatch?.source ?? displayCard.card_source ?? "manual_unbound")} · ${formatEvidenceLevel(displayCard.evidence_level)}`
                    : selectedPaper
                      ? "来自当前项目 Paper Table。"
                      : supplementalInput.trim()
                        ? "来自用户粘贴内容。"
                        : "暂无输入。"}
                </p>
              </div>
            </div>
          </section>

          <section className="paper-signals-card">
            <div className="aside-heading compact">
              <h2>科研字段（自动抽取）</h2>
              <span>{signals ? "已生成" : "暂无"}</span>
            </div>
            {signals ? (
              <div className="signal-chip-grid">
                {[
                  ["task", "研究任务", signals.task],
                  ["method", "核心方法", signals.method],
                  ["dataset", "数据集", signals.dataset],
                  ["metric", "评估指标", signals.metric],
                  ["baseline", "对比基线", signals.baseline],
                  ["claim", "主要主张", signals.claim],
                  ["limitation", "论文局限", signals.limitation],
                ].map(([field, label, value], index) => {
                  const source = classifySignalEvidence(signals.signal_evidence?.[field]);
                  return (
                    <article className={`signal-chip tone-${index}`} key={field}>
                      <div>
                        <strong>{label}</strong>
                        <small data-source={source.status}>{source.label}</small>
                      </div>
                      <span>{formatResearchSignal(value, "未定位")}</span>
                    </article>
                  );
                })}
              </div>
            ) : (
              <div className="reader-empty-state compact">
                <FileText size={19} />
                <div>
                  <h3>暂无科研字段</h3>
                  <p>生成 Paper Card 后才会显示研究任务、方法、数据集、指标、基线和主要主张。</p>
                </div>
              </div>
            )}
          </section>
        </aside>
      </section>
    </div>
  );
}

function classifySignalEvidence(
  evidence: ApiSignalEvidence | undefined,
): { label: string; status: "full_text" | "supplemental_text" | "abstract_only" | "missing" | "invalid" } {
  if (!evidence || evidence.availability === "missing") {
    return { label: "缺失", status: "missing" };
  }
  if (evidence.availability === "invalid" || evidence.validation_errors.length > 0) {
    return { label: "异常", status: "invalid" };
  }
  const refs = evidence.evidence_refs?.length ? evidence.evidence_refs : [evidence];
  const allFullText = refs.every(
    (ref) => ref.source === "pdf.full_text" && ref.validation_errors.length === 0,
  );
  if (allFullText && evidence.availability !== "partial") {
    return { label: "全文", status: "full_text" };
  }
  if (refs.some((ref) => ref.source === "user.supplemental_text")) {
    return { label: "补充文本", status: "supplemental_text" };
  }
  return { label: "摘要", status: "abstract_only" };
}

function PaperSignalDetail({
  evidence,
  label,
  value,
}: {
  evidence: ApiSignalEvidence | undefined;
  label: string;
  value: string | undefined;
}) {
  const source = classifySignalEvidence(evidence);
  return (
    <div className="paper-signal-detail">
      <div className="paper-signal-field-head">
        <strong>{label}</strong>
        <small data-source={source.status}>{source.label}</small>
      </div>
      <span>{formatResearchSignal(value, "未定位")}</span>
      <small className="critique-evidence-note">{formatSignalEvidenceLocation(evidence)}</small>
    </div>
  );
}

function buildPaperDecisionBrief(card: ApiPaperCard | null): {
  readiness: "ready" | "partial" | "blocked";
  label: string;
  items: Array<{
    label: string;
    value: string;
    sourceLabel: string;
    sourceStatus: "full_text" | "supplemental_text" | "abstract_only" | "missing" | "invalid";
  }>;
  nextAction: string;
  evidence: Array<{ label: string; location: string }>;
} {
  const signals = card?.signals;
  const useful = (value: string | undefined, fallback: string) => {
    return formatResearchSignal(value, fallback);
  };
  const coreEvidence = [
    signals?.signal_evidence?.task,
    signals?.signal_evidence?.method,
    signals?.signal_evidence?.claim,
  ];
  const coreSignalsPresent = Boolean(
    signals && useful(signals.task, "") && useful(signals.method, "") && useful(signals.claim, ""),
  );
  const coreEvidenceStatuses = coreEvidence.map((evidence) => classifySignalEvidence(evidence).status);
  const coreSignalsVerified = coreEvidenceStatuses.every((status) => status === "full_text");
  const cardHasVerifiedFullText =
    card?.evidence_qualification?.level === "full_text" &&
    card.evidence_qualification.verified;
  const readiness =
    cardHasVerifiedFullText && coreSignalsPresent && coreSignalsVerified
      ? "ready"
      : coreSignalsPresent || card?.evidence_level === "abstract_only"
        ? "partial"
        : "blocked";
  const label =
    readiness === "ready"
      ? "可进入人工核验"
      : readiness === "partial"
        ? "仅作选读线索"
        : "证据不足";
  const nextAction =
    readiness === "ready"
      ? useful(
          card?.minimal_reproduction,
          "先回到 PDF 核对方法、实验设置和失败案例，再决定是否进入复现。",
        )
      : cardHasVerifiedFullText
        ? "卡片已绑定全文，但任务、方法或主要主张仍有字段缺少全文定位；请先核对对应 PDF 段落，再决定是否进入复现。"
      : "上传或绑定论文 PDF，重点补齐方法、实验设置、baseline、ablation 与失败案例后重新生成。";
  const evidenceFields: Array<[string, ApiSignalEvidence | undefined]> = [
    ["研究任务", signals?.signal_evidence?.task],
    ["核心方法", signals?.signal_evidence?.method],
    ["主要主张", signals?.signal_evidence?.claim],
  ];
  return {
    readiness,
    label,
    items: [
      {
        label: "研究任务",
        value: useful(signals?.task, "尚未定位到明确、可检验的研究任务。"),
        sourceLabel: classifySignalEvidence(signals?.signal_evidence?.task).label,
        sourceStatus: classifySignalEvidence(signals?.signal_evidence?.task).status,
      },
      {
        label: "核心方法",
        value: useful(signals?.method, "尚未定位到具体方法机制。"),
        sourceLabel: classifySignalEvidence(signals?.signal_evidence?.method).label,
        sourceStatus: classifySignalEvidence(signals?.signal_evidence?.method).status,
      },
      {
        label: "主要主张",
        value: useful(signals?.claim, "尚未定位到论文的主要经验主张。"),
        sourceLabel: classifySignalEvidence(signals?.signal_evidence?.claim).label,
        sourceStatus: classifySignalEvidence(signals?.signal_evidence?.claim).status,
      },
    ],
    nextAction,
    evidence: evidenceFields.flatMap(([field, evidence]) =>
      evidence
        ? [{ label: field, location: formatSignalEvidenceLocation(evidence) }]
        : [],
    ),
  };
}

function DirectionPaperPage({
  canUpload,
  hasHydratedReview,
  isGenerating,
  onBack,
  onOpenEvidenceInput,
  onOpenPaper,
  onPdfUpload,
  reading,
  readings,
  requestedPaperId,
}: {
  canUpload: boolean;
  hasHydratedReview: boolean;
  isGenerating: boolean;
  onBack: () => void;
  onOpenEvidenceInput: () => void;
  onOpenPaper: (paperId: string) => void;
  onPdfUpload: (paperId: string, file: File) => void;
  reading: ApiDirectionPaperReading | null;
  readings: ApiDirectionPaperReading[];
  requestedPaperId: string;
}) {
  const readingIndex = reading ? readings.findIndex((item) => item.paper.id === reading.paper.id) : -1;
  const previousReading = readingIndex > 0 ? readings[readingIndex - 1] : null;
  const nextReading = readingIndex >= 0 && readingIndex < readings.length - 1 ? readings[readingIndex + 1] : null;

  return (
    <div className="direction-paper-page">
      <header className="direction-paper-toolbar">
        <button className="back-link" type="button" onClick={onBack}>
          <ChevronLeft size={16} />
          返回 Direction Review
        </button>
        <div className="direction-paper-position" aria-live="polite">
          {reading ? `${readingIndex + 1} / ${readings.length}` : "Paper Card"}
        </div>
        <div className="direction-paper-paging">
          <button
            aria-label="上一篇论文"
            disabled={!previousReading}
            type="button"
            onClick={() => previousReading && onOpenPaper(previousReading.paper.id)}
          >
            <ChevronLeft size={15} />
            上一篇
          </button>
          <button
            aria-label="下一篇论文"
            disabled={!nextReading}
            type="button"
            onClick={() => nextReading && onOpenPaper(nextReading.paper.id)}
          >
            下一篇
            <ArrowRight size={15} />
          </button>
        </div>
      </header>

      {reading ? (
        <DirectionPaperDetail
          canUpload={canUpload}
          isGenerating={isGenerating}
          onOpenEvidenceInput={onOpenEvidenceInput}
          onPdfUpload={onPdfUpload}
          reading={reading}
        />
      ) : (
        <section className="direction-paper-route-state" role="status">
          <BookOpen size={22} />
          <div>
            <h1>{hasHydratedReview ? "未找到这篇 Paper Card" : "正在恢复 Paper Card"}</h1>
            <p>
              {hasHydratedReview
                ? `当前 Direction Review 中没有 paper id=${requestedPaperId}。系统不会回退到第一篇论文。`
                : "正在从当前项目的 Direction Review artifact 恢复论文详情，请稍候。"}
            </p>
            {hasHydratedReview ? (
              <button className="secondary-command" type="button" onClick={onBack}>
                返回论文列表
              </button>
            ) : null}
          </div>
        </section>
      )}
    </div>
  );
}

function formatReaderTitle(evidenceLevel: string, hasCard: boolean): string {
  if (!hasCard) {
    return "论文阅读 · Paper Card";
  }
  if (evidenceLevel === "full_text") {
    return "全文级深读 · Paper Card";
  }
  if (evidenceLevel === "supplemental_text") {
    return "补充文本辅助阅读 · Paper Card";
  }
  if (evidenceLevel === "abstract_only") {
    return "摘要级阅读 · Paper Card";
  }
  return "阅读提纲 · Paper Card";
}

function formatPaperCardSource(source: PaperCardMatchSource): string {
  if (source === "direction_review_artifact") {
    return "Direction Review artifact";
  }
  if (source === "paper_table") {
    return "Paper Table";
  }
  return "Manual input / unbound";
}

function formatFullTextSource(source: string): string {
  if (source === "arxiv_pdf") {
    return "arXiv PDF";
  }
  if (source === "openalex_open_access_pdf") {
    return "OpenAlex 开放全文";
  }
  if (source === "open_access_pdf") {
    return "开放获取 PDF";
  }
  if (source === "user_provided") {
    return "用户补充文本，未通过 PDF 验证";
  }
  if (source === "user_uploaded_pdf") {
    return "用户上传 PDF";
  }
  return source || "未记录来源";
}

function mergeDirectionReadingWithPaperCard(
  reading: ApiDirectionPaperReading | null,
  card: ApiPaperCard | null,
): ApiDirectionPaperReading | null {
  if (!reading || !card || !doesPaperCardMatchDirectionReading(card, reading)) {
    return reading;
  }
  if (evidenceRank(card.evidence_level, card.full_text) < evidenceRank(reading.evidence_level, reading.full_text)) {
    return reading;
  }
  return {
    ...reading,
    artifact_id: card.artifact_id ?? reading.artifact_id,
    artifact_title: card.source_artifact_title ?? reading.artifact_title,
    evidence_level: card.evidence_level ?? reading.evidence_level,
    evidence_qualification: card.evidence_qualification ?? reading.evidence_qualification,
    full_text: card.full_text ?? reading.full_text,
    updated_at: card.updated_at || card.created_at || reading.updated_at,
    signals: card.signals ?? reading.signals,
    sections: card.sections.length ? card.sections : reading.sections,
    weakest_assumption: card.weakest_assumption || reading.weakest_assumption,
    minimal_reproduction: card.minimal_reproduction || reading.minimal_reproduction,
  };
}

function doesPaperCardMatchDirectionReading(card: ApiPaperCard, reading: ApiDirectionPaperReading): boolean {
  const readingId = reading.paper_id || reading.paper.id;
  if (card.paper_id && readingId) {
    return card.paper_id === readingId;
  }
  if (card.card_source !== "direction_review_artifact") {
    return false;
  }
  const cardTitle = normalizePaperTitle(card.paper_title);
  const readingTitle = normalizePaperTitle(reading.paper_title || reading.paper.title);
  return Boolean(cardTitle && readingTitle && cardTitle === readingTitle);
}

function evidenceRank(
  level: string | undefined,
  provenance?: ApiFullTextProvenance,
): number {
  const qualification = provenance?.evidence_qualification;
  if (qualification?.level === "full_text" && qualification.verified) {
    return 4;
  }
  if (qualification?.level === "supplemental_text" || level === "supplemental_text") {
    return 2;
  }
  if (level === "abstract_only") {
    return 1;
  }
  return 0;
}

function normalizePaperTitle(value: string | undefined): string {
  return (value ?? "")
    .toLowerCase()
    .replace(/[^a-z0-9\u4e00-\u9fff]+/g, " ")
    .trim();
}

function fullTextFailureReason(provenance: ApiFullTextProvenance): string {
  if (provenance.status === "supplemental_text") {
    return "用户补充文本，未通过 PDF 验证";
  }
  if (provenance.error.trim()) {
    return provenance.error.trim();
  }
  if (provenance.status === "download_failed") {
    return "PDF 下载失败，来源可能需要登录或拒绝自动访问。";
  }
  if (provenance.status === "parse_failed") {
    return "已获取 PDF，但没有解析出可用于科研分析的正文。";
  }
  if (provenance.status === "disabled") {
    return "当前服务未启用全文获取。";
  }
  return "没有发现可公开访问的 PDF 地址。";
}

function FullTextProvenanceStatus({
  onOpenEvidenceInput,
  provenance,
  updatedAt,
}: {
  onOpenEvidenceInput?: () => void;
  provenance: ApiFullTextProvenance | undefined;
  updatedAt?: string;
}) {
  if (!provenance) {
    return null;
  }

  const qualification = provenance.evidence_qualification;
  const extracted = Boolean(
    qualification?.level === "full_text" && qualification.verified,
  );
  return (
    <section
      className={extracted ? "full-text-provenance-status extracted" : "full-text-provenance-status limited"}
      aria-label="full text acquisition status"
      data-testid="paper-card-provenance"
    >
      {extracted ? <CheckCircle2 size={18} /> : <AlertTriangle size={18} />}
      <div>
        <strong>
          {extracted
            ? `已验证 PDF 全文 · ${provenance.page_count.toLocaleString("zh-CN")} 页 / ${provenance.character_count.toLocaleString("zh-CN")} 字符`
            : fullTextFailureReason(provenance)}
        </strong>
        <p>
          来源：{formatFullTextSource(provenance.source)}
          {provenance.pdf_url ? (
            <>
              {" · "}
              <a href={provenance.pdf_url} rel="noreferrer" target="_blank">
                查看 PDF 来源
              </a>
            </>
          ) : null}
        </p>
        {updatedAt ? <small className="full-text-updated-at">更新时间：{formatArtifactDate(updatedAt)}</small> : null}
        {!extracted && provenance.recovery_hint ? <small>建议：{provenance.recovery_hint}</small> : null}
      </div>
      {!extracted && onOpenEvidenceInput ? (
        <button type="button" onClick={onOpenEvidenceInput}>
          补充正文证据
          <ArrowRight size={14} />
        </button>
      ) : null}
    </section>
  );
}

function PdfUploadControl({
  busy,
  disabled,
  onUpload,
  paperId,
}: {
  busy: boolean;
  disabled: boolean;
  onUpload: (paperId: string, file: File) => void;
  paperId: string;
}) {
  const inputId = `paper-pdf-upload-${paperId.replace(/[^a-zA-Z0-9_-]/g, "-") || "unbound"}`;
  const unavailable = disabled || busy || !paperId;
  return (
    <div className="pdf-upload-control" aria-label="upload paper PDF">
      <div>
        <Download size={18} aria-hidden="true" />
        <span>
          <strong>直接上传论文 PDF</strong>
          <small>解析文本层并重新生成全文级 Paper Card；文件仅发送到本地 ScholarFlow API。</small>
        </span>
      </div>
      <label className={unavailable ? "disabled" : ""} htmlFor={inputId} aria-disabled={unavailable}>
        {busy ? "正在解析…" : "选择 PDF"}
      </label>
      <input
        accept="application/pdf,.pdf"
        disabled={unavailable}
        id={inputId}
        type="file"
        onChange={(event) => {
          const file = event.currentTarget.files?.[0];
          event.currentTarget.value = "";
          if (file) {
            onUpload(paperId, file);
          }
        }}
      />
    </div>
  );
}

type EvidenceBoundary = {
  title: string;
  message: string;
  confirmed: string;
  cannotConfirm: string;
  nextAction: string;
};

export function buildEvidenceBoundary(evidenceLevel: string | undefined): EvidenceBoundary | null {
  if (evidenceLevel === "metadata_only") {
    return {
      title: "元数据级证据，不是全文结论",
      message: "当前只基于标题、年份、来源等元数据生成阅读提纲。方法、实验、claim 和反例都需要补充 abstract 或 PDF 后才能确认。",
      confirmed: "论文标题、年份、来源与检索方向的表面关联。",
      cannotConfirm: "研究方法、实验设置、claim、局限和复现条件。",
      nextAction: "先补充摘要；需要做科研判断时上传可复制文本的 PDF。",
    };
  }
  if (evidenceLevel === "abstract_only") {
    return {
      title: "摘要级证据，不是全文结论",
      message: "当前只基于摘要和候选元数据生成结构化阅读。它适合决定是否精读，但不能替代完整 PDF 的方法和实验核验。",
      confirmed: "摘要明确陈述的研究对象、核心任务和作者公开 claim。",
      cannotConfirm: "方法细节、完整 baseline、消融、失败样本与统计可靠性。",
      nextAction: "上传本地 PDF，系统会重新绑定当前论文并升级为已验证 PDF 全文。",
    };
  }
  if (evidenceLevel === "supplemental_text") {
    return {
      title: "用户补充文本，未通过 PDF 验证",
      message: "当前卡片可使用用户粘贴内容辅助阅读，但该内容没有经过 PDF 来源、页码、文本层和解析状态验证。",
      confirmed: "用户明确提供的文本内容，以及其中可直接看到的关键词和陈述。",
      cannotConfirm: "PDF 原文位置、完整上下文、全文级 claim、true gap 和实验 anchor。",
      nextAction: "上传带可复制文本层的 PDF；只有通过统一资格检查后才会升级为已验证 PDF 全文。",
    };
  }
  return null;
}

function LimitedEvidenceSummary({ boundary }: { boundary: EvidenceBoundary }) {
  return (
    <section className="limited-evidence-summary" aria-label="limited evidence summary">
      <div>
        <strong>能确认什么</strong>
        <p>{boundary.confirmed}</p>
      </div>
      <div>
        <strong>不能确认什么</strong>
        <p>{boundary.cannotConfirm}</p>
      </div>
      <div>
        <strong>如何获得全文</strong>
        <p>{boundary.nextAction}</p>
      </div>
    </section>
  );
}

function buildMissingEvidenceChecklist(card: ApiPaperCard | null): string[] {
  if (!card) {
    return [];
  }
  const checklist: string[] = [];
  if (card.evidence_level === "metadata_only") {
    checklist.push("缺 abstract/PDF/正文");
  }
  if (card.evidence_level === "abstract_only") {
    checklist.push("缺 PDF/完整正文、method/experiment 表格和 failure case");
  }
  if (card.evidence_level === "supplemental_text") {
    checklist.push("用户补充文本未通过 PDF 来源、页码和解析验证");
  }
  const missingSignals = card.signals?.missing_signals ?? [];
  missingSignals.forEach((signal) => checklist.push(`缺 ${signal}`));
  if (card.minimal_reproduction.toLowerCase().includes("status: blocked")) {
    checklist.push("最小复现实验未解锁：需要补齐 claim + dataset + metric + baseline");
  }
  return [...new Set(checklist)];
}

type ParsedPaperCardSectionContent = {
  evidenceGap: string;
  outline: string;
  primary: string;
  verification: string;
};

function parsePaperCardSectionContent(content: string): ParsedPaperCardSectionContent {
  let normalized = content.replace(/\r\n?/g, "\n").trim();
  const boundaryMatch = normalized.match(
    /^证据边界[（(](?:metadata_only|abstract_only|supplemental_text)[）)][:：][\s\S]*?(?=\n阅读提纲[:：])/,
  );

  if (boundaryMatch) {
    normalized = normalized.slice(boundaryMatch[0].length).replace(/^\n+/, "");
  }

  const outlinePrefix = "阅读提纲：";
  const visibleMarker = "\n当前可见线索：";
  const gapMarker = "\n证据缺口：";
  const verificationMarker = "\n需要验证的问题：";
  const visibleIndex = normalized.indexOf(visibleMarker);
  const verificationIndex = normalized.lastIndexOf(verificationMarker);
  const gapIndex = verificationIndex >= 0
    ? normalized.lastIndexOf(gapMarker, verificationIndex - 1)
    : normalized.lastIndexOf(gapMarker);

  if (
    normalized.startsWith(outlinePrefix) &&
    visibleIndex >= 0 &&
    gapIndex > visibleIndex &&
    verificationIndex > gapIndex
  ) {
    return {
      outline: normalized.slice(outlinePrefix.length, visibleIndex).trim(),
      primary: normalized.slice(visibleIndex + visibleMarker.length, gapIndex).trim(),
      evidenceGap: normalized.slice(gapIndex + gapMarker.length, verificationIndex).trim(),
      verification: normalized.slice(verificationIndex + verificationMarker.length).trim(),
    };
  }

  return {
    evidenceGap: "",
    outline: "",
    primary: normalized,
    verification: "",
  };
}

function formatPaperCardSectionTitle(title: string): string {
  return title.replace(/^\s*\d{1,2}\s*[.、:：)）]\s*/, "").trim();
}

function splitPaperCardSectionParagraphs(content: string): string[] {
  if (!content.trim()) {
    return [];
  }
  const withSignalBreaks = content.replace(
    /;\s*(?=(?:method|dataset|metric|baseline|claim|limitation|type)=)/gi,
    ";\n",
  );
  const sourceLines = withSignalBreaks.split(/\n+/).map((line) => line.trim()).filter(Boolean);
  const paragraphs: string[] = [];
  for (const line of sourceLines) {
    const sentences = line.split(/(?<=[。！？])\s+/).map((sentence) => sentence.trim()).filter(Boolean);
    let current = "";
    for (const sentence of sentences) {
      if (current && current.length + sentence.length > 380) {
        paragraphs.push(current);
        current = sentence;
      } else {
        current = current ? `${current} ${sentence}` : sentence;
      }
    }
    if (current) {
      paragraphs.push(current);
    }
  }
  return paragraphs.length ? paragraphs : [];
}

function DirectionPaperDetail({
  canUpload,
  isGenerating,
  onOpenEvidenceInput,
  onPdfUpload,
  reading,
}: {
  canUpload: boolean;
  isGenerating: boolean;
  onOpenEvidenceInput: () => void;
  onPdfUpload: (paperId: string, file: File) => void;
  reading: ApiDirectionPaperReading;
}) {
  const [activeSectionNumber, setActiveSectionNumber] = useState(1);
  const signals = reading.signals;
  const missingSignals = signals?.missing_signals ?? [];
  const evidenceBoundary = buildEvidenceBoundary(reading.evidence_level);
  const missingEvidence = [
    ...(evidenceBoundary ? [evidenceBoundary.title] : []),
    ...missingSignals.map((signal) => `缺 ${signal}`),
  ];
  const sections = reading.sections ?? [];
  const activeSectionIndex = sections.length
    ? Math.min(Math.max(activeSectionNumber - 1, 0), sections.length - 1)
    : -1;
  const activeSection = activeSectionIndex >= 0 ? sections[activeSectionIndex] : null;
  const researchSight = normalizeResearchSight(reading.research_sight);
  const evidencePack = normalizeEvidencePack(researchSight.evidence_pack);
  const critiqueEvidence = new Map(
    (researchSight.critique_evidence ?? []).map((item) => [item.field, item]),
  );

  useEffect(() => {
    setActiveSectionNumber(1);
  }, [reading.paper?.id]);

  const renderCritiqueEvidence = (field: string) => {
    const evidence = critiqueEvidence.get(field);
    if (!evidence) {
      return null;
    }
    return (
      <small className="critique-evidence-note">
        evidence: {evidence.evidence_snippet_id || "none"} · confidence: {evidence.confidence || "low"}
        {evidence.rationale ? ` · ${evidence.rationale}` : ""}
      </small>
    );
  };

  return (
    <section className="direction-detail" aria-label="selected paper detail">
      <div className="direction-detail-header">
        <div>
          <p className="section-kicker">Selected Paper Detail</p>
          <h2 id="direction-paper-title" tabIndex={-1}>
            {formatAcademicText(reading.paper?.title ?? "Untitled paper")}
          </h2>
        </div>
        {reading.paper?.url ? (
          <a href={reading.paper.url} rel="noreferrer" target="_blank">
            open paper
          </a>
        ) : null}
      </div>

      <section className="reader-evidence-summary direction-reader-evidence" aria-label="direction paper evidence summary">
        <div className={`reader-evidence-level ${reading.evidence_level}`}>
          <ShieldCheck size={16} />
          <strong>{formatEvidenceLevel(reading.evidence_level ?? "metadata_only")}</strong>
          <span>来源：{formatFullTextSource(reading.full_text?.source ?? "")}</span>
          {reading.full_text?.status === "extracted" ? (
            <span>
              {reading.full_text.page_count} 页 / {reading.full_text.character_count.toLocaleString("zh-CN")} 字符
            </span>
          ) : null}
          {reading.updated_at ? <span>更新：{formatArtifactDate(reading.updated_at)}</span> : null}
        </div>
        {evidenceBoundary ? <LimitedEvidenceSummary boundary={evidenceBoundary} /> : null}
        {missingEvidence.length ? <small>待补证据：{missingEvidence.join("；")}</small> : null}
      </section>

      <article className="direction-abstract">
        <h3>摘要中文内容</h3>
        <small>Evidence level: {formatEvidenceLevel(reading.evidence_level ?? "metadata_only")}</small>
        <p>{reading.abstract_translation}</p>
      </article>

      <FullTextProvenanceStatus
        onOpenEvidenceInput={onOpenEvidenceInput}
        provenance={reading.full_text}
        updatedAt={reading.updated_at}
      />

      {reading.full_text?.status !== "extracted" ? (
        <PdfUploadControl
          busy={isGenerating}
          disabled={!canUpload}
          onUpload={onPdfUpload}
          paperId={reading.paper.id}
        />
      ) : null}

      {signals ? (
        <details className="paper-signals-panel direction-detail-disclosure" aria-label="paper evidence signals">
          <summary className="paper-signals-header">
            <div>
              <p className="section-kicker">Paper Signals</p>
              <h3>论文证据信号</h3>
            </div>
            <FileText size={18} />
          </summary>
          <div className="paper-signals-grid">
            <div>
              <strong>类型</strong>
              <span>{formatContributionType(signals.contribution_type || "")}</span>
            </div>
            <PaperSignalDetail evidence={signals.signal_evidence?.task} label="研究任务" value={signals.task} />
            <PaperSignalDetail evidence={signals.signal_evidence?.method} label="核心方法" value={signals.method} />
            <PaperSignalDetail evidence={signals.signal_evidence?.dataset} label="数据集" value={signals.dataset} />
            <PaperSignalDetail evidence={signals.signal_evidence?.metric} label="评估指标" value={signals.metric} />
            <PaperSignalDetail evidence={signals.signal_evidence?.baseline} label="对比基线" value={signals.baseline} />
            <PaperSignalDetail evidence={signals.signal_evidence?.claim} label="主要主张" value={signals.claim} />
            <PaperSignalDetail evidence={signals.signal_evidence?.limitation} label="论文局限" value={signals.limitation} />
            <PaperSignalDetail
              evidence={signals.signal_evidence?.prior_work_limitation}
              label="已有研究不足"
              value={signals.prior_work_limitation}
            />
            <div>
              <strong>未定位字段</strong>
              <span>{missingSignals.length ? missingSignals.join(", ") : "无"}</span>
            </div>
          </div>
        </details>
      ) : null}

      <details className="research-sight-panel direction-detail-disclosure">
        <summary className="research-sight-header">
          <div>
            <p className="section-kicker">Research Sight</p>
            <h3>科研审美评价</h3>
          </div>
          <BrainCircuit size={18} />
        </summary>
        <div className="research-sight-score-grid">
          <div>
            <strong>证据等级</strong>
            <span>
              {formatEvidenceLevel(reading.evidence_level ?? evidencePack.evidence_level)}；
              来源置信度 {evidencePack.source_confidence || "unknown"} / 抽取置信度 {evidencePack.extraction_confidence || "unknown"} /
              最终 {evidencePack.confidence || "low"}。{evidencePack.grounding_summary}
            </span>
          </div>
          <div>
            <strong>动机锋利度</strong>
            <span>{researchSight.motivation_sharpness || "暂无"}</span>
          </div>
          <div>
            <strong>解法优雅性</strong>
            <span>{researchSight.solution_elegance || "暂无"}</span>
          </div>
          <div>
            <strong>评估真实性</strong>
            <span>{researchSight.evaluation_integrity || "暂无"}</span>
          </div>
          <div>
            <strong>范式启发性</strong>
            <span>{researchSight.paradigm_inspiration || "暂无"}</span>
          </div>
        </div>
        <div className="research-sight-critique">
          <div>
            <strong>为什么好</strong>
            <p>{researchSight.why_good || "尚未形成可引用的正面评价。"}</p>
            {renderCritiqueEvidence("why_good")}
          </div>
          <div>
            <strong>为什么不好</strong>
            <p>{researchSight.why_not_good || "尚未形成可引用的局限评价。"}</p>
            {renderCritiqueEvidence("why_not_good")}
          </div>
          <div>
            <strong>更好角度</strong>
            <p>{researchSight.better_angle || "尚未形成论文专属的研究角度。"}</p>
            {renderCritiqueEvidence("better_angle")}
          </div>
          <div>
            <strong>Baseline 对比</strong>
            <p>{researchSight.baseline_comparison || "尚未定位到可复核的对照结论。"}</p>
            {renderCritiqueEvidence("baseline_comparison")}
          </div>
          <div>
            <strong>下一步 proposal</strong>
            <p>{researchSight.next_step_proposal || "尚未形成论文专属的下一步建议。"}</p>
            {renderCritiqueEvidence("next_step_proposal")}
          </div>
        </div>
        <div className="sight-evidence-grid" aria-label="research sight evidence">
          <div>
            <strong>证据片段</strong>
            {evidencePack.snippets.length ? (
              evidencePack.snippets.slice(0, 4).map((snippet) => (
                <article key={`${snippet.source}-${snippet.id}`}>
                  <span>
                    {snippet.source} · {snippet.kind} · {snippet.confidence}
                    {snippet.section ? ` · ${snippet.section}` : ""}
                    {typeof snippet.page === "number" ? ` · p.${snippet.page}` : ""}
                  </span>
                  <p>{snippet.text}</p>
                  <small>{snippet.note}</small>
                </article>
              ))
            ) : (
              <p>当前没有可用证据片段。</p>
            )}
          </div>
          <div>
            <strong>缺失证据</strong>
            {evidencePack.missing_evidence.length ? (
              <ul>
                {evidencePack.missing_evidence.slice(0, 5).map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            ) : (
              <p>当前没有显式缺失项。</p>
            )}
          </div>
        </div>
      </details>

      <div className="direction-key-findings">
        <div>
          <strong>最脆弱假设</strong>
          <span>{reading.weakest_assumption}</span>
        </div>
        <div>
          <strong>一周最小复现</strong>
          <span>{reading.minimal_reproduction}</span>
        </div>
        <div>
          <strong>反例设计</strong>
          <span>{reading.counterexample}</span>
        </div>
        <div>
          <strong>Follow-up Idea</strong>
          <span>{reading.follow_up_idea}</span>
        </div>
      </div>

      <section className="direction-section-reader" aria-label="12 段精读">
        <div className="question-board-head">
          <div>
            <p className="section-kicker">Deep Paper Card</p>
            <h2>12 段科研精读</h2>
          </div>
          <span>{sections.length}/12 已生成</span>
        </div>
        {sections.length ? (
          <div className="paper-reader-workspace direction-paper-section-workspace">
            <nav className="paper-reader-toc" aria-label="独立 Paper Card 精读目录">
              <ol>
                {sections.map((section, index) => {
                  const isActive = activeSectionIndex === index;
                  return (
                    <li key={`${section.id}-${index}`}>
                      <button
                        aria-controls={isActive ? `direction-paper-section-${index + 1}` : undefined}
                        aria-current={isActive ? true : undefined}
                        aria-label={`第 ${index + 1} 节：${section.title}`}
                        className="paper-reader-toc-item"
                        type="button"
                        onClick={() => setActiveSectionNumber(index + 1)}
                      >
                        <span aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>
                        <strong>{formatPaperCardSectionTitle(section.title)}</strong>
                        <Check size={14} aria-hidden="true" />
                      </button>
                    </li>
                  );
                })}
              </ol>
            </nav>

            {activeSection ? (
              <article
                className="paper-reader-section direction-active-section"
                id={`direction-paper-section-${activeSectionIndex + 1}`}
                tabIndex={-1}
              >
                <header>
                  <span>
                    Section {String(activeSectionIndex + 1).padStart(2, "0")} / {sections.length}
                    {" · "}
                    {reading.full_text?.status === "extracted"
                      ? `PDF 全文 ${reading.full_text.page_count} 页`
                      : formatEvidenceLevel(reading.evidence_level ?? "metadata_only")}
                  </span>
                  <h3 data-testid={`direction-paper-section-heading-${activeSectionIndex + 1}`}>
                    {formatPaperCardSectionTitle(activeSection.title)}
                  </h3>
                </header>
                <div className="paper-reader-section-body direction-active-section-body">
                  {splitPaperCardSectionParagraphs(activeSection.content).map((paragraph, index) => (
                    <p key={`${activeSection.id}-paragraph-${index}`}>{paragraph}</p>
                  ))}
                </div>
                <footer className="paper-reader-section-nav" aria-label="独立 Paper Card 章节切换">
                  <button
                    disabled={activeSectionIndex <= 0}
                    type="button"
                    onClick={() => setActiveSectionNumber(activeSectionIndex)}
                  >
                    <ChevronLeft size={15} />
                    上一节
                  </button>
                  <span aria-live="polite">
                    {activeSectionIndex + 1} / {sections.length}
                  </span>
                  <button
                    disabled={activeSectionIndex >= sections.length - 1}
                    type="button"
                    onClick={() => setActiveSectionNumber(activeSectionIndex + 2)}
                  >
                    下一节
                    <ArrowRight size={15} />
                  </button>
                </footer>
              </article>
            ) : null}
          </div>
        ) : (
          <article className="direction-detail-section empty">
            <span>00</span>
            <div>
              <h3>暂无 12 sections</h3>
              <p>当前 artifact 没有提供 card.sections 或 sections 字段，但 Paper Signals 与 Research Sight 仍可查看。</p>
            </div>
          </article>
        )}
      </section>
    </section>
  );
}
