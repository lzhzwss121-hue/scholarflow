import { useEffect, useMemo, useState } from "react";
import { navItems, type ViewId } from "./mockData";
import { ViewErrorBoundary } from "./components/ViewErrorBoundary";
import { useWorkflowController } from "./lib/workflowService";
import { ActiveView, WorkflowShell } from "./views/ProductViews";
import "./styles.css";

const productViewIds: ViewId[] = [
  "dashboard",
  "new-project",
  "paper-table",
  "direction-review",
  "paper-memory",
  "paper-reader",
  "gap-board",
  "experiment-planner",
];

const viewAliases: Record<string, ViewId> = {
  "experiment-plan": "experiment-planner",
  "deep-paper-card": "paper-reader",
};

function readViewFromHash(): ViewId {
  if (typeof window === "undefined") {
    return "dashboard";
  }
  const hashView = window.location.hash.replace("#", "");
  if (hashView in viewAliases) {
    return viewAliases[hashView];
  }
  return productViewIds.includes(hashView as ViewId) ? (hashView as ViewId) : "dashboard";
}

export function App() {
  const [activeView, setActiveView] = useState<ViewId>(() => readViewFromHash());
  const { actions, viewModel } = useWorkflowController(activeView, setActiveViewAndHash);
  const activeNavItem = useMemo(
    () => navItems.find((item) => item.id === activeView),
    [activeView],
  );

  useEffect(() => {
    function handleHashChange() {
      setActiveView(readViewFromHash());
    }

    window.addEventListener("hashchange", handleHashChange);
    return () => window.removeEventListener("hashchange", handleHashChange);
  }, []);

  function setActiveViewAndHash(view: ViewId) {
    setActiveView(view);
    if (typeof window !== "undefined") {
      window.history.replaceState(null, "", `#${view}`);
    }
  }

  return (
    <div className={`scholarflow-product-shell view-${activeView}`}>
      <WorkflowShell
        activeView={activeView}
        actions={actions}
        ariaLabel={activeNavItem?.label ?? "ScholarFlow workflow"}
        onSelectView={setActiveViewAndHash}
        viewModel={viewModel}
      >
        <ViewErrorBoundary view={activeView}>
          <ActiveView
            activeProject={viewModel.activeProject}
            agentBusy={viewModel.busy.agent}
            agentPlan={viewModel.agentPlan}
            agentTask={viewModel.agentTask}
            apiMessage={viewModel.apiMessage}
            apiStatus={viewModel.apiStatus}
            artifactCount={viewModel.artifactCount}
            artifactSummaries={viewModel.artifactSummaries}
            decisionBusy={viewModel.busy.decision}
            decisionGoal={viewModel.decisionGoal}
            directionBusy={viewModel.busy.direction}
            directionInput={viewModel.directionInput}
            directionReview={viewModel.directionReview}
            directionRound={viewModel.directionRound}
            literatureCoverage={viewModel.literatureCoverage}
            literatureBusy={viewModel.busy.literature}
            literatureErrors={viewModel.literatureErrors}
            literatureQuery={viewModel.literatureQuery}
            memoryBusy={viewModel.busy.memory}
            memoryQuestion={viewModel.memoryQuestion}
            memoryResult={viewModel.memoryResult}
            memoryTopK={viewModel.memoryTopK}
            projectDraft={viewModel.projectDraft}
            onAgentTaskChange={actions.onAgentTaskChange}
            onCreateProject={actions.onCreateProject}
            onCreateAgentPlan={actions.onCreateAgentPlan}
            onCreateDirectionReview={actions.onCreateDirectionReview}
            onExecuteAgentRun={actions.onExecuteAgentRun}
            onGeneratePaperCard={actions.onGeneratePaperCard}
            onCreateResearchDecision={actions.onCreateResearchDecision}
            onDecisionGoalChange={actions.onDecisionGoalChange}
            onDirectionInputChange={actions.onDirectionInputChange}
            onDirectionRoundChange={actions.onDirectionRoundChange}
            onLiteratureQueryChange={actions.onLiteratureQueryChange}
            onLoadArtifact={actions.onLoadArtifact}
            onMemoryQuestionChange={actions.onMemoryQuestionChange}
            onMemoryTopKChange={actions.onMemoryTopKChange}
            onPaperCardInputChange={actions.onPaperCardInputChange}
            onQueryResearchMemory={actions.onQueryResearchMemory}
            onProjectDraftChange={actions.onProjectDraftChange}
            onSearchLiterature={actions.onSearchLiterature}
            onSelectedDirectionPaperChange={actions.onSelectedDirectionPaperChange}
            onSelectedPaperChange={actions.onSelectedPaperChange}
            onSelectView={setActiveViewAndHash}
            paperRows={viewModel.paperRows}
            paperCardBusy={viewModel.busy.paperCard}
            paperCardInput={viewModel.paperCardInput}
            projectCount={viewModel.projectCount}
            researchDecision={viewModel.researchDecision}
            selectedDirectionPaperId={viewModel.selectedDirectionPaperId}
            selectedPaperId={viewModel.selectedPaperId}
            latestPaperCard={viewModel.latestPaperCard}
            view={activeView}
          />
        </ViewErrorBoundary>
      </WorkflowShell>
    </div>
  );
}
