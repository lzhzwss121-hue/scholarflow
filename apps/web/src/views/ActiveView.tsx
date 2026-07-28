import type {
  ApiAgentPlanResponse, ApiAgentRunStatusResponse, ApiArtifactSummary,
  ApiDirectionReviewResponse, ApiDirectionReviewRunStatusResponse, ApiPaperCard,
  ApiProject, ApiRagAnswerResponse, ApiResearchDecisionResponse,
  ApiResearchMemoryQueryResponse,
} from "@scholarflow/schemas";
import { ApiOfflineNotice } from "../components/ApiOfflineNotice";
import type { PaperRow, ViewId } from "../mockData";
import type { ApiStatus, ProjectDraft } from "../types/workflow";
import { DirectionReviewView } from "./DirectionReviewView";
import { ExperimentPlannerView } from "./ExperimentPlannerView";
import { GapBoardView } from "./GapBoardView";
import { ProductHomeView } from "./HomeView";
import { ProductNewProjectView } from "./NewProjectView";
import { ProductPaperReaderView } from "./PaperReaderView";
import { ProductPaperTableView } from "./PaperTableView";
import { ResearchMemoryView } from "./ResearchMemoryView";

const coreViews = new Set<ViewId>([
  "paper-table", "direction-review", "paper-memory", "paper-reader",
  "gap-board", "experiment-planner",
]);

export interface ActiveViewProps {
  activeProject: ApiProject | null;
  agentBusy: boolean;
  agentPlan: ApiAgentPlanResponse | null;
  agentRunStatus: ApiAgentRunStatusResponse | null;
  agentTask: string;
  apiMessage: string;
  apiStatus: ApiStatus;
  artifactCount: number;
  artifactSummaries: ApiArtifactSummary[];
  decisionBusy: boolean;
  decisionGoal: string;
  directionBusy: boolean;
  directionInput: string;
  directionMessage: string;
  directionPaperRouteId: string;
  directionReview: ApiDirectionReviewResponse | null;
  directionRun: ApiDirectionReviewRunStatusResponse | null;
  directionRound: number;
  literatureCoverage: Record<string, number>;
  literatureBusy: boolean;
  literatureErrors: string[];
  literatureQuery: string;
  latestPaperCard: ApiPaperCard | null;
  memoryBusy: boolean;
  memoryMessage: string;
  memoryQuestion: string;
  memoryResult: ApiResearchMemoryQueryResponse | null;
  memoryTopK: number;
  ragAnswer: ApiRagAnswerResponse | null;
  ragBusy: boolean;
  ragMessage: string;
  ragQuestion: string;
  ragTopK: number;
  projectDraft: ProjectDraft;
  onAgentTaskChange: (task: string) => void;
  onCreateAgentPlan: () => void;
  onCancelAgentRun: () => void;
  onCreateDirectionReview: () => void;
  onCreateProject: () => void;
  onCreateResearchDecision: () => void;
  onDecisionGoalChange: (goal: string) => void;
  onDirectionInputChange: (direction: string) => void;
  onDirectionRoundChange: (round: number) => void;
  onExecuteAgentRun: () => void;
  onExitDirectionPaper: () => void;
  onGeneratePaperCard: () => void;
  onLiteratureQueryChange: (query: string) => void;
  onLoadArtifact: (artifactId: string) => void;
  onMemoryQuestionChange: (question: string) => void;
  onMemoryTopKChange: (topK: number) => void;
  onRagQuestionChange: (question: string) => void;
  onRagTopKChange: (topK: number) => void;
  onPaperCardInputChange: (value: string) => void;
  onPaperPdfUpload: (paperId: string, file: File) => void;
  onProjectDraftChange: (draft: ProjectDraft) => void;
  onQueryResearchMemory: () => void;
  onQueryRag: () => void;
  onSearchLiterature: () => void;
  onSelectedDirectionPaperChange: (paperId: string) => void;
  onSelectedPaperChange: (paperId: string) => void;
  onSelectView: (view: ViewId) => void;
  paperRows: PaperRow[];
  paperCardBusy: boolean;
  paperCardInput: string;
  projectCount: number;
  researchDecision: ApiResearchDecisionResponse | null;
  selectedPaperId: string;
  view: ViewId;
}
export function ActiveView({
  activeProject,
  agentBusy,
  agentPlan,
  agentRunStatus,
  agentTask,
  apiMessage,
  apiStatus,
  artifactCount,
  artifactSummaries,
  decisionBusy,
  decisionGoal,
  directionBusy,
  directionInput,
  directionMessage,
  directionPaperRouteId,
  directionReview,
  directionRun,
  directionRound,
  literatureCoverage,
  literatureBusy,
  literatureErrors,
  literatureQuery,
  latestPaperCard,
  memoryBusy,
  memoryMessage,
  memoryQuestion,
  memoryResult,
  memoryTopK,
  ragAnswer,
  ragBusy,
  ragMessage,
  ragQuestion,
  ragTopK,
  projectDraft,
  onAgentTaskChange,
  onCancelAgentRun,
  onCreateAgentPlan,
  onCreateDirectionReview,
  onCreateProject,
  onCreateResearchDecision,
  onDecisionGoalChange,
  onDirectionInputChange,
  onDirectionRoundChange,
  onExecuteAgentRun,
  onExitDirectionPaper,
  onGeneratePaperCard,
  onLiteratureQueryChange,
  onLoadArtifact,
  onMemoryQuestionChange,
  onMemoryTopKChange,
  onRagQuestionChange,
  onRagTopKChange,
  onPaperCardInputChange,
  onPaperPdfUpload,
  onProjectDraftChange,
  onQueryResearchMemory,
  onQueryRag,
  onSearchLiterature,
  onSelectedDirectionPaperChange,
  onSelectedPaperChange,
  onSelectView,
  paperRows,
  paperCardBusy,
  paperCardInput,
  projectCount,
  researchDecision,
  selectedPaperId,
  view,
}: ActiveViewProps) {
  const offlineNotice = apiStatus === "offline" && coreViews.has(view) ? <ApiOfflineNotice /> : null;

  switch (view) {
    case "new-project":
      return (
        <ProductNewProjectView
          activeProject={activeProject}
          apiMessage={apiMessage}
          apiStatus={apiStatus}
          artifactCount={artifactCount}
          artifactSummaries={artifactSummaries}
          draft={projectDraft}
          onCreateProject={onCreateProject}
          onDraftChange={onProjectDraftChange}
          onLoadArtifact={onLoadArtifact}
          onSelectView={onSelectView}
          paperCount={paperRows.length}
          projectCount={projectCount}
        />
      );
    case "paper-table":
      return (
        <>
          {offlineNotice}
          <ProductPaperTableView
            activeProject={activeProject}
            apiMessage={apiMessage}
            artifactCount={artifactCount}
            artifactSummaries={artifactSummaries}
            apiStatus={apiStatus}
            relevanceCoverage={literatureCoverage}
            errors={literatureErrors}
            isSearching={literatureBusy}
            onQueryChange={onLiteratureQueryChange}
            onLoadArtifact={onLoadArtifact}
            onSearch={onSearchLiterature}
            onSelectView={onSelectView}
            papers={paperRows}
            projectCount={projectCount}
            query={literatureQuery}
          />
        </>
      );
    case "paper-reader":
      return (
        <>
          {offlineNotice}
          <ProductPaperReaderView
            activeProject={activeProject}
            apiMessage={apiMessage}
            artifactCount={artifactCount}
            apiStatus={apiStatus}
            card={latestPaperCard}
            directionPaperId={directionPaperRouteId}
            directionReview={directionReview}
            artifactSummaries={artifactSummaries}
            isGenerating={paperCardBusy}
            onGenerate={onGeneratePaperCard}
            onInputChange={onPaperCardInputChange}
            onPdfUpload={onPaperPdfUpload}
            onLoadArtifact={onLoadArtifact}
            onExitDirectionPaper={onExitDirectionPaper}
            onOpenDirectionPaper={onSelectedDirectionPaperChange}
            onSelectedPaperChange={onSelectedPaperChange}
            onSelectView={onSelectView}
            papers={paperRows}
            projectCount={projectCount}
            selectedPaperId={selectedPaperId}
            supplementalInput={paperCardInput}
          />
        </>
      );
    case "direction-review":
      return (
        <>
          {offlineNotice}
          <DirectionReviewView
            apiMessage={directionMessage}
            apiStatus={apiStatus}
            direction={directionInput}
            isGenerating={directionBusy}
            onDirectionChange={onDirectionInputChange}
            onGenerate={onCreateDirectionReview}
            onLoadArtifact={onLoadArtifact}
            onOpenPaperCard={onSelectedDirectionPaperChange}
            onRoundChange={onDirectionRoundChange}
            review={directionReview}
            run={directionRun}
            round={directionRound}
          />
        </>
      );
    case "paper-memory":
      return (
        <>
          {offlineNotice}
          <ResearchMemoryView
            apiStatus={apiStatus}
            direction={directionInput}
            isQuerying={memoryBusy}
            isRagQuerying={ragBusy}
            memoryMessage={memoryMessage}
            onQuestionChange={onMemoryQuestionChange}
            onQuery={onQueryResearchMemory}
            onQueryRag={onQueryRag}
            onRagQuestionChange={onRagQuestionChange}
            onRagTopKChange={onRagTopKChange}
            onSelectView={onSelectView}
            onTopKChange={onMemoryTopKChange}
            question={memoryQuestion}
            result={memoryResult}
            ragResult={ragAnswer}
            ragMessage={ragMessage}
            ragQuestion={ragQuestion}
            ragTopK={ragTopK}
            topK={memoryTopK}
          />
        </>
      );
    case "gap-board":
      return (
        <>
          {offlineNotice}
          <GapBoardView
            apiMessage={apiMessage}
            apiStatus={apiStatus}
            decision={researchDecision}
            goal={decisionGoal}
            isGenerating={decisionBusy}
            onGenerate={onCreateResearchDecision}
            onGoalChange={onDecisionGoalChange}
          />
        </>
      );
    case "experiment-planner":
      return (
        <>
          {offlineNotice}
          <ExperimentPlannerView
            apiMessage={apiMessage}
            apiStatus={apiStatus}
            decision={researchDecision}
            goal={decisionGoal}
            isGenerating={decisionBusy}
            onGenerate={onCreateResearchDecision}
            onGoalChange={onDecisionGoalChange}
          />
        </>
      );
    case "dashboard":
    default:
      return (
        <ProductHomeView
          activeProject={activeProject}
          agentBusy={agentBusy}
          agentPlan={agentPlan}
          agentRunStatus={agentRunStatus}
          agentTask={agentTask}
          apiStatus={apiStatus}
          artifactCount={artifactCount}
          onAgentTaskChange={onAgentTaskChange}
          onCancelAgentRun={onCancelAgentRun}
          onCreateAgentPlan={onCreateAgentPlan}
          onExecuteAgentRun={onExecuteAgentRun}
          onSelectView={onSelectView}
          paperCount={paperRows.length}
          projectCount={projectCount}
        />
      );
  }
}
