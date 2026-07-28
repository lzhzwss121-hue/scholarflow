from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from scholarflow_api import __version__
from scholarflow_api.database import init_db
from scholarflow_api.jobs.repository import recover_orphaned_runs
from scholarflow_api.routers.agents import router as agents_router
from scholarflow_api.routers.artifacts import router as artifacts_router
from scholarflow_api.routers.direction_reviews import router as direction_reviews_router
from scholarflow_api.routers.health import router as health_router
from scholarflow_api.routers.literature import router as literature_router
from scholarflow_api.routers.paper_cards import router as paper_cards_router
from scholarflow_api.routers.projects import router as projects_router
from scholarflow_api.routers.rag import router as rag_router
from scholarflow_api.routers.research_decisions import router as research_decisions_router
from scholarflow_api.services.workflow_runtime import *  # noqa: F403


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    init_db()
    recover_orphaned_runs()
    yield


app = FastAPI(
    title="ScholarFlow API",
    version=__version__,
    description="Backend API and persistence layer for ScholarFlow Research Workflow Runs.",
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
