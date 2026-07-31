import { useEffect, useMemo, useRef, useState } from "react";
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

type AppRoute = {
  view: ViewId;
  paperId: string;
  from: "direction-review" | null;
};

function readRouteFromHash(): AppRoute {
  if (typeof window === "undefined") {
    return { view: "dashboard", paperId: "", from: null };
  }
  const rawHash = window.location.hash.replace(/^#/, "");
  const [rawPath, rawQuery = ""] = rawHash.split("?");
  const [rawView = "", rawPaperId = ""] = rawPath.split("/");
  const view = rawView in viewAliases ? viewAliases[rawView] : rawView;
  const normalizedView = productViewIds.includes(view as ViewId) ? (view as ViewId) : "dashboard";
  let paperId = "";
  if (normalizedView === "paper-reader" && rawPaperId) {
    try {
      paperId = decodeURIComponent(rawPaperId);
    } catch {
      paperId = rawPaperId;
    }
  }
  const from = new URLSearchParams(rawQuery).get("from") === "direction-review" ? "direction-review" : null;
  return { view: normalizedView, paperId, from };
}

export function App() {
  const [route, setRoute] = useState<AppRoute>(() => readRouteFromHash());
  const workflowMainRef = useRef<HTMLElement | null>(null);
  const previousRouteIdentityRef = useRef<string | null>(null);
  const activeView = route.view;
  const routeIdentity = `${activeView}:${route.paperId}`;
  const { actions, viewModel } = useWorkflowController(activeView, setActiveViewAndHash);
  const activeNavItem = useMemo(
    () => navItems.find((item) => item.id === activeView),
    [activeView],
  );

  useEffect(() => {
    function handleRouteChange() {
      setRoute(readRouteFromHash());
    }

    window.addEventListener("hashchange", handleRouteChange);
    window.addEventListener("popstate", handleRouteChange);
    return () => {
      window.removeEventListener("hashchange", handleRouteChange);
      window.removeEventListener("popstate", handleRouteChange);
    };
  }, []);

  useEffect(() => {
    const previousRouteIdentity = previousRouteIdentityRef.current;
    previousRouteIdentityRef.current = routeIdentity;
    if (previousRouteIdentity === routeIdentity) {
      return;
    }
    workflowMainRef.current?.scrollTo({ top: 0, behavior: "auto" });
  }, [routeIdentity]);

  const hasHydratedDirectionReview = Boolean(viewModel.directionReview);
  useEffect(() => {
    if (!route.paperId || !hasHydratedDirectionReview) {
      return;
    }
    const frame = window.requestAnimationFrame(() => {
      document.querySelector<HTMLElement>("#direction-paper-title")?.focus({ preventScroll: true });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [route.paperId, hasHydratedDirectionReview]);

  function setActiveViewAndHash(view: ViewId) {
    setRoute({ view, paperId: "", from: null });
    if (typeof window !== "undefined") {
      window.history.replaceState(null, "", `#${view}`);
    }
  }

  function openDirectionPaper(paperId: string) {
    actions.onSelectedDirectionPaperChange(paperId);
    actions.onSelectedPaperChange(paperId);
    const nextRoute: AppRoute = { view: "paper-reader", paperId, from: "direction-review" };
    setRoute(nextRoute);
    if (typeof window !== "undefined") {
      const encodedPaperId = encodeURIComponent(paperId);
      const nextUrl = `#paper-reader/${encodedPaperId}?from=direction-review`;
      const isPagingInsideDirectionReader =
        route.view === "paper-reader" && route.from === "direction-review" && Boolean(route.paperId);
      if (isPagingInsideDirectionReader) {
        window.history.replaceState(
          { ...window.history.state, from: "direction-review", paperId },
          "",
          nextUrl,
        );
      } else {
        window.history.pushState(
          { scholarflowDetail: true, from: "direction-review", paperId },
          "",
          nextUrl,
        );
      }
    }
  }

  function closeDirectionPaper() {
    if (typeof window !== "undefined" && window.history.state?.scholarflowDetail) {
      window.history.back();
      return;
    }
    setActiveViewAndHash("direction-review");
  }

  return (
    <div className={`scholarflow-product-shell view-${activeView}`}>
      <WorkflowShell
        activeView={activeView}
        actions={actions}
        ariaLabel={activeNavItem?.label ?? "ScholarFlow workflow"}
        mainRef={workflowMainRef}
        onSelectView={setActiveViewAndHash}
        viewModel={viewModel}
      >
        <ViewErrorBoundary key={`${activeView}:${route.paperId}`} view={activeView}>
          <ActiveView
            activeProject={viewModel.activeProject}
            agentBusy={viewModel.busy.agent}
            agentPlan={viewModel.agentPlan}
            agentRunStatus={viewModel.agentRunStatus}
            agentTask={viewModel.agentTask}
            apiMessage={viewModel.apiMessage}
            apiStatus={viewModel.apiStatus}
            artifactCount={viewModel.artifactCount}
            artifactSummaries={viewModel.artifactSummaries}
            decisionBusy={viewModel.busy.decision}
            decisionGoal={viewModel.decisionGoal}
            directionBusy={viewModel.busy.direction}
            directionInput={viewModel.directionInput}
            directionMessage={viewModel.directionMessage}
            directionPaperRouteId={route.paperId}
            directionReview={viewModel.directionReview}
            directionRun={viewModel.directionRun}
            directionRound={viewModel.directionRound}
            literatureCoverage={viewModel.literatureCoverage}
            literatureBusy={viewModel.busy.literature}
            literatureErrors={viewModel.literatureErrors}
            literatureQuery={viewModel.literatureQuery}
            memoryBusy={viewModel.busy.memory}
            memoryMessage={viewModel.memoryMessage}
            memoryQuestion={viewModel.memoryQuestion}
            memoryResult={viewModel.memoryResult}
            memoryTopK={viewModel.memoryTopK}
            ragAnswer={viewModel.ragAnswer}
            ragBusy={viewModel.busy.rag}
            ragMessage={viewModel.ragMessage}
            ragQuestion={viewModel.ragQuestion}
            ragTopK={viewModel.ragTopK}
            projectDraft={viewModel.projectDraft}
            onAgentTaskChange={actions.onAgentTaskChange}
            onCancelAgentRun={actions.onCancelAgentRun}
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
            onRagQuestionChange={actions.onRagQuestionChange}
            onRagTopKChange={actions.onRagTopKChange}
            onPaperCardInputChange={actions.onPaperCardInputChange}
            onPaperPdfUpload={actions.onPaperPdfUpload}
            onQueryResearchMemory={actions.onQueryResearchMemory}
            onQueryRag={actions.onQueryRag}
            onProjectDraftChange={actions.onProjectDraftChange}
            onSearchLiterature={actions.onSearchLiterature}
            onExitDirectionPaper={closeDirectionPaper}
            onSelectedDirectionPaperChange={openDirectionPaper}
            onSelectedPaperChange={actions.onSelectedPaperChange}
            onSelectView={setActiveViewAndHash}
            paperRows={viewModel.paperRows}
            paperCardBusy={viewModel.busy.paperCard}
            paperCardInput={viewModel.paperCardInput}
            projectCount={viewModel.projectCount}
            researchDecision={viewModel.researchDecision}
            selectedPaperId={viewModel.selectedPaperId}
            latestPaperCard={viewModel.latestPaperCard}
            view={activeView}
          />
        </ViewErrorBoundary>
      </WorkflowShell>
    </div>
  );
}
