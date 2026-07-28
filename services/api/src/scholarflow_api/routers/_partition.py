from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter

from scholarflow_api.services.workflow_runtime import router as workflow_router


def partition_router(
    predicate: Callable[[str], bool],
    *,
    tags: list[str],
) -> APIRouter:
    router = APIRouter(tags=tags)
    router.routes.extend(
        route
        for route in workflow_router.routes
        if predicate(getattr(route, "path", ""))
    )
    return router
