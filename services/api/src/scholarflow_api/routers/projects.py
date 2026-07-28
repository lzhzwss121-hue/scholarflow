from scholarflow_api.routers._partition import partition_router


def owns(path: str) -> bool:
    return (
        path in {"/projects", "/projects/{project_id}"}
        or path.endswith("/sessions")
        or path.endswith("/timeline")
        or path.startswith("/sessions/")
    )


router = partition_router(owns, tags=["projects"])
