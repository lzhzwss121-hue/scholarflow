import { type ReactNode, useEffect, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  Bell,
  BookOpen,
  BrainCircuit,
  Calendar,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  Circle,
  Clock3,
  Download,
  Filter,
  FileText,
  FlaskConical,
  GitBranch,
  LayoutDashboard,
  Lightbulb,
  Network,
  Play,
  Plus,
  Rocket,
  Save,
  Search,
  ShieldCheck,
  Sparkles,
  Table2,
  Target,
  Trophy,
  X,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import {
  SCHOLARFLOW_VERSION,
  type ApiAgentPlanResponse,
  type ApiAgentPlanStep,
  type ApiAgentRunStatusResponse,
  type ApiArtifact,
  type ApiArtifactRef,
  type ApiArtifactSummary,
  type ApiDirectionPaperReading,
  type ApiDirectionReviewResponse,
  type ApiDirectionReviewRunStatusResponse,
  type ApiEvidencePack,
  type ApiFullTextProvenance,
  type ApiPaperCard,
  type ApiProject,
  type ApiRagAnswerResponse,
  type ApiResearchDecisionResponse,
  type ApiResearchMemoryQueryResponse,
  type ApiSignalEvidence,
} from "@scholarflow/schemas";
import {
  navItems,
  type ArtifactContent,
  type PaperRow,
  type PlanStep,
  type PlanStatus,
  type TimelineEvent,
  type ViewId,
} from "../mockData";
import { RagAnswerPanel } from "../components/RagAnswerPanel";
import { isRetrievalWarning } from "../apiClient";
import {
  normalizeEvidencePack,
  normalizeResearchSight,
  resolvePaperCardForPaper,
  toPlanStatus,
} from "../lib/artifactHydration";
import type { PaperCardMatchSource } from "../lib/artifactHydration";
import type {
  ApiStatus,
  ArtifactTab,
  ProjectDraft,
  WorkflowActions,
  WorkflowNotice,
  WorkflowStepStatus,
  WorkflowViewModel,
} from "../types/workflow";
import {
  ConferenceLogoBelt,
  PROJECT_DRAFT_STORAGE_KEY,
  ProjectSidebar,
} from "./shared/ProductViewRuntime";

export function ProductNewProjectView({
  activeProject,
  apiMessage,
  apiStatus,
  artifactCount,
  artifactSummaries,
  draft,
  onCreateProject,
  onDraftChange,
  onLoadArtifact,
  onSelectView,
  paperCount,
  projectCount,
}: {
  activeProject: ApiProject | null;
  apiMessage: string;
  apiStatus: ApiStatus;
  artifactCount: number;
  artifactSummaries: ApiArtifactSummary[];
  draft: ProjectDraft;
  onCreateProject: () => void;
  onDraftChange: (draft: ProjectDraft) => void;
  onLoadArtifact: (artifactId: string) => void;
  onSelectView: (view: ViewId) => void;
  paperCount: number;
  projectCount: number;
}) {
  const [draftStatus, setDraftStatus] = useState("");
  const suggestions = [
    {
      title: "多模态大模型在视觉问答中的证据真实性评估",
      detail: "关注 hallucination、citation faithfulness 与 benchmark。",
      icon: Network,
    },
    {
      title: "医学影像分割中的 prompt learning",
      detail: "探索提示学习在分割任务中的跨域泛化能力。",
      icon: BookOpen,
    },
    {
      title: "RAG 系统中 citation faithfulness 的自动评估方法",
      detail: "构建无需人工标注的可信度评估框架。",
      icon: Search,
    },
    {
      title: "扩散模型用于盲图像修复时的可控性问题",
      detail: "研究条件控制与结构保持的平衡策略。",
      icon: FileText,
    },
  ];
  const createSteps = [
    ["创建 SQLite Project", "建立本地项目、语言、研究领域和 workflow。"],
    ["初始化 Research Workflow Task", "生成从文献检索到可验证 gap 的最小任务计划。"],
    ["进入 Paper Table", "用当前关键词直接发起 arXiv / OpenAlex 检索。"],
    ["保存 Artifact", "后续总结、Paper Card、Gap Board 都可回溯。"],
  ];

  function updateDraft(field: keyof ProjectDraft, value: string) {
    onDraftChange({
      ...draft,
      [field]: value,
    });
  }

  function applySuggestion(title: string) {
    onDraftChange({
      ...draft,
      title,
      keyword: title,
      description: `围绕「${title}」检索近三年相关论文，识别证据约束、benchmark 偏差与一周可验证实验。`,
    });
  }

  function saveDraftToLocalStorage() {
    if (!draft.title.trim() && !draft.keyword.trim() && !draft.description.trim()) {
      setDraftStatus("请先填写标题、关键词或目标，再保存草稿。");
      return;
    }
    try {
      window.localStorage.setItem(PROJECT_DRAFT_STORAGE_KEY, JSON.stringify({ ...draft, saved_at: new Date().toISOString() }));
      setDraftStatus("草稿已保存到本机浏览器 localStorage，不会写入后端或 GitHub。");
    } catch {
      setDraftStatus("草稿保存失败：浏览器阻止了 localStorage 写入。");
    }
  }

  return (
    <div className="project-canvas">
      <ProjectSidebar
        activeProject={activeProject}
        activeView="new-project"
        artifacts={artifactSummaries}
        artifactCount={artifactCount}
        onLoadArtifact={onLoadArtifact}
        onSelectView={onSelectView}
        paperCount={paperCount}
        projectCount={projectCount}
      />

      <section className="new-project-panel">
        <div className="panel-title-row">
          <Sparkles size={34} />
          <div>
            <h1>新建科研项目</h1>
            <p>输入项目信息，系统将为你初始化 “survey-to-experiment” 工作流。</p>
          </div>
        </div>

        <div className="field-stack">
          <label>
            <span>项目标题 <sup>*</sup></span>
            <div className="text-input-row">
              <input
                maxLength={100}
                placeholder="例如：多模态大模型在视觉问答证据真实性研究"
                value={draft.title}
                onChange={(event) => updateDraft("title", event.target.value)}
              />
              <span>{draft.title.length}/100</span>
            </div>
          </label>
          <label>
            <span>研究方向 / Keyword <sup>*</sup></span>
            <div className="text-input-row">
              <input
                maxLength={200}
                placeholder="输入关键词，多个关键词请用英文逗号分隔"
                value={draft.keyword}
                onChange={(event) => updateDraft("keyword", event.target.value)}
              />
              <span>{draft.keyword.length}/200</span>
            </div>
          </label>
          <label>
            <span>研究领域 <sup>*</sup></span>
            <div className="select-like readonly-field" aria-readonly="true">
              <span>{draft.field || "Artificial Intelligence / Multimodal Learning"}</span>
              <small>只读，可在标题和关键词中细化方向</small>
            </div>
          </label>
          <label>
            <span>工作流模板 <sup>*</sup></span>
            <div className="select-like readonly-field" aria-readonly="true">
              <span>Survey → Deep Reading → Memory → Gap → Experiment</span>
              <small>固定模板</small>
            </div>
          </label>
        </div>

        <div className="form-action-row">
          <button className="gradient-button form-primary" disabled={apiStatus === "checking"} type="button" onClick={onCreateProject}>
            创建项目
          </button>
          <button className="outline-button form-secondary" type="button" onClick={saveDraftToLocalStorage}>
            <Save size={17} />
            保存草稿
          </button>
        </div>
        {draftStatus ? <p className="draft-status-note">{draftStatus}</p> : null}

        <div className={`project-status-note ${apiStatus}`}>
          <Lightbulb size={18} />
          <span>{apiMessage}</span>
        </div>
      </section>

      <aside className="new-project-aside">
        <section className="suggestion-panel">
          <div className="aside-heading">
            <h2>推荐输入示例</h2>
            <span>Prompt Suggestions</span>
          </div>
          <div className="suggestion-list">
            {suggestions.map((item) => {
              const Icon = item.icon;
              return (
                <button className="suggestion-card" key={item.title} type="button" onClick={() => applySuggestion(item.title)}>
                  <span>
                    <Icon size={21} />
                  </span>
                  <div>
                    <strong>{item.title}</strong>
                    <p>{item.detail}</p>
                  </div>
                </button>
              );
            })}
          </div>
        </section>

        <section className="after-create-panel">
          <h2>创建后自动生成</h2>
          <ol>
            {createSteps.map(([title, detail], index) => (
              <li key={title}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                <div>
                  <strong>{title}</strong>
                  <p>{detail}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>
      </aside>

      <ConferenceLogoBelt />
    </div>
  );
}
