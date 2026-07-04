import type {
  ApiAgentPlanResponse,
  ApiArtifact,
  ApiArtifactSummary,
  ApiDirectionReviewResponse,
  ApiPaperCard,
  ApiProject,
  ApiResearchDecisionResponse,
  ApiResearchMemoryQueryResponse,
  ApiWorkflowStepState,
  ApiWorkflowStepStatus,
} from "@scholarflow/schemas";
import type { ArtifactContent, PaperRow, TimelineEvent, ViewId } from "../mockData";

export type ArtifactTab = "markdown" | "json" | "diff";
export type ApiStatus = "checking" | "online" | "offline";
export type ProjectDraft = {
  title: string;
  description: string;
  keyword: string;
  field: string;
};

export type ViewSelector = (view: ViewId) => void;

export type WorkflowStepStatus = ApiWorkflowStepStatus;

export type WorkflowStepView = ApiWorkflowStepState & {
  id: ViewId;
};

export type WorkflowNotice = {
  id: string;
  kind: "warning" | "error" | "info";
  message: string;
};

export type RelevanceCoverage = Record<string, number>;

export type WorkflowBusyStates = {
  agent: boolean;
  artifactSaving: boolean;
  decision: boolean;
  direction: boolean;
  literature: boolean;
  memory: boolean;
  paperCard: boolean;
};

export type WorkflowViewModel = {
  activeArtifact: ArtifactContent;
  activeProject: ApiProject | null;
  agentPlan: ApiAgentPlanResponse | null;
  agentTask: string;
  apiMessage: string;
  apiStatus: ApiStatus;
  artifactCount: number;
  artifactDraft: ArtifactContent | null;
  artifactSummaries: ApiArtifactSummary[];
  artifactTab: ArtifactTab;
  busy: WorkflowBusyStates;
  decisionGoal: string;
  directionInput: string;
  directionReview: ApiDirectionReviewResponse | null;
  directionRound: number;
  latestPaperCard: ApiPaperCard | null;
  lastSavedArtifact: ApiArtifact | null;
  literatureCoverage: RelevanceCoverage;
  literatureErrors: string[];
  literatureQuery: string;
  memoryQuestion: string;
  memoryResult: ApiResearchMemoryQueryResponse | null;
  memoryTopK: number;
  paperCardInput: string;
  paperRows: PaperRow[];
  projectCount: number;
  projectDraft: ProjectDraft;
  projects: ApiProject[];
  researchDecision: ApiResearchDecisionResponse | null;
  selectedDirectionPaperId: string;
  selectedPaperId: string;
  timelineRows: TimelineEvent[];
  warnings: WorkflowNotice[];
  workflowSteps: WorkflowStepView[];
};

export type WorkflowActions = {
  onAgentTaskChange: (task: string) => void;
  onArtifactChange: (artifact: ArtifactContent) => void;
  onArtifactTabChange: (tab: ArtifactTab) => void;
  onCreateAgentPlan: () => void;
  onCreateDirectionReview: () => void;
  onCreateProject: () => void;
  onCreateResearchDecision: () => void;
  onDecisionGoalChange: (goal: string) => void;
  onDirectionInputChange: (direction: string) => void;
  onDirectionRoundChange: (round: number) => void;
  onExecuteAgentRun: () => void;
  onGeneratePaperCard: () => void;
  onLiteratureQueryChange: (query: string) => void;
  onLoadArtifact: (artifactId: string) => void;
  onMemoryQuestionChange: (question: string) => void;
  onMemoryTopKChange: (topK: number) => void;
  onPaperCardInputChange: (value: string) => void;
  onProjectDraftChange: (draft: ProjectDraft) => void;
  onQueryResearchMemory: () => void;
  onSaveArtifact: () => void;
  onSearchLiterature: () => void;
  onSelectProject: (projectId: string) => void;
  onSelectedDirectionPaperChange: (paperId: string) => void;
  onSelectedPaperChange: (paperId: string) => void;
};

export type WorkflowController = {
  actions: WorkflowActions;
  viewModel: WorkflowViewModel;
};
