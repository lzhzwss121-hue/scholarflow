from scholarflow_api.routers._partition import partition_router


def owns(path: str) -> bool:
    return "/research-decisions" in path or "/research-memory/" in path


router = partition_router(owns, tags=["research-decisions"])
