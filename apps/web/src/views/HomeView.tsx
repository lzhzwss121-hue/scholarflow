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
  AgentRunPanel,
  formatProjectStage,
  Metric,
  WorkflowGuide,
} from "./shared/ProductViewRuntime";

export function ProductHomeView({
  activeProject,
  agentBusy,
  agentPlan,
  agentRunStatus,
  agentTask,
  apiStatus,
  artifactCount,
  onAgentTaskChange,
  onCancelAgentRun,
  onCreateAgentPlan,
  onExecuteAgentRun,
  onSelectView,
  paperCount,
  projectCount,
}: {
  activeProject: ApiProject | null;
  agentBusy: boolean;
  agentPlan: ApiAgentPlanResponse | null;
  agentRunStatus: ApiAgentRunStatusResponse | null;
  agentTask: string;
  apiStatus: ApiStatus;
  artifactCount: number;
  onAgentTaskChange: (task: string) => void;
  onCancelAgentRun: () => void;
  onCreateAgentPlan: () => void;
  onExecuteAgentRun: () => void;
  onSelectView: (view: ViewId) => void;
  paperCount: number;
  projectCount: number;
}) {
  return (
    <div className="dashboard-workbench">
      <section className="workbench-summary-panel">
        <div className="workbench-summary-copy">
          <p className="section-kicker">Project snapshot</p>
          <h2>{activeProject?.title ?? "先创建一个科研项目"}</h2>
          <p>
            {activeProject
              ? activeProject.description || "当前项目已经连接到本地 SQLite 工作区。"
              : "ScholarFlow 只展示真实项目状态。创建项目后，Paper Table、Direction Review、Paper Memory、Gap Board 和 Experiment Plan 才会逐步进入可用状态。"}
          </p>
          <div className="workbench-context-row">
            <span>{activeProject?.field || "Evidence-first workflow"}</span>
            <span>{activeProject?.workflow || "Survey → experiment"}</span>
            <span>{activeProject ? formatProjectStage(activeProject.stage) : "Awaiting project"}</span>
          </div>
        </div>
        <div className="workbench-summary-actions">
          <div className={`workbench-live-state ${apiStatus}`}>
            <span aria-hidden="true" />
            <div>
              <small>Workspace state</small>
              <strong>{apiStatus === "online" ? "Ready for research" : "Backend required"}</strong>
            </div>
          </div>
          <div className="workbench-action-row">
            <button className="secondary-command" type="button" onClick={() => onSelectView("new-project")}>
              <Plus size={17} />
              新建项目
            </button>
            <button
              className="secondary-command workbench-primary-command"
              disabled={!activeProject || apiStatus !== "online"}
              type="button"
              onClick={() => onSelectView("paper-table")}
            >
              <Search size={17} />
              进入 Paper Table
            </button>
          </div>
        </div>
      </section>

      <section className="workbench-metric-grid" aria-label="current project metrics">
        <Metric label="API" value={apiStatus} detail={apiStatus === "online" ? "后端可用" : "等待后端连接"} />
        <Metric label="Projects" value={String(projectCount)} detail="本地 SQLite 项目数" />
        <Metric label="Papers" value={String(paperCount)} detail="当前项目真实论文" />
        <Metric label="Artifacts" value={String(artifactCount)} detail="后端持久化输出" />
      </section>

      <WorkflowGuide
        apiStatus={apiStatus}
        artifactCount={artifactCount}
        hasProject={Boolean(activeProject)}
        onSelectView={onSelectView}
        paperCount={paperCount}
      />

      <AgentRunPanel
        activeProject={activeProject}
        agentBusy={agentBusy}
        agentPlan={agentPlan}
        agentRunStatus={agentRunStatus}
        agentTask={agentTask}
        apiStatus={apiStatus}
        onAgentTaskChange={onAgentTaskChange}
        onCancelAgentRun={onCancelAgentRun}
        onCreateAgentPlan={onCreateAgentPlan}
        onExecuteAgentRun={onExecuteAgentRun}
      />
    </div>
  );
}
