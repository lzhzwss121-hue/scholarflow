from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from scholarflow_api import __version__
from scholarflow_api.database import init_db
from scholarflow_api.jobs.repository import recover_orphaned_runs
from scholarflow_api.routers.agents import (
    cancel_agent_run,
    create_agent_plan,
    execute_agent_run,
    get_agent_run_status,
    router as agents_router,
)
from scholarflow_api.routers.artifacts import (
    get_artifact,
    list_project_artifact_summaries,
    router as artifacts_router,
    save_artifact,
)
from scholarflow_api.routers.direction_reviews import router as direction_reviews_router
from scholarflow_api.routers.health import router as health_router
from scholarflow_api.routers.literature import router as literature_router
from scholarflow_api.routers.paper_cards import router as paper_cards_router
from scholarflow_api.routers.projects import router as projects_router
from scholarflow_api.routers.rag import router as rag_router
from scholarflow_api.routers.research_decisions import router as research_decisions_router
from scholarflow_api.schemas import PaperChunkIndexRequest
from scholarflow_api.services.agent_tool_service import build_agent_tool_registry
from scholarflow_api.services.workflow_runtime import (
    cancel_project_direction_review_run,
    create_project,
    create_project_direction_review,
    create_project_paper_card,
    create_project_rag_answer,
    create_project_research_decisions,
    delete_project_paper_rag_index,
    embed_project_paper_rag_index,
    embed_project_rag_index,
    extract_project_paper_full_text,
    get_latest_project_direction_review_run,
    get_paper_rag_index_status,
    get_project_direction_review_run,
    get_project_rag_evaluations,
    get_project_rag_index_status,
    get_project_timeline,
    health,
    list_project_paper_cards,
    list_project_paper_chunks,
    list_project_papers,
    list_projects,
    query_project_research_memory,
    rebuild_project_paper_rag_index,
    search_project_literature,
    search_project_rag,
    start_project_direction_review_run,
)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    init_db()
    recover_orphaned_runs()
    yield


app = FastAPI(
    title="ScholarFlow API",
    version=__version__,
    description="Backend API and persistence layer for ScholarFlow Bounded Research Agent runs.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_origin_regex=r"http://(127\.0\.0\.1|localhost):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for api_router in (
    health_router,
    projects_router,
    literature_router,
    paper_cards_router,
    rag_router,
    direction_reviews_router,
    research_decisions_router,
    agents_router,
    artifacts_router,
):
    app.include_router(api_router)
