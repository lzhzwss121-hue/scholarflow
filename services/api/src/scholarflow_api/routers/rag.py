from scholarflow_api.routers._partition import partition_router


def owns(path: str) -> bool:
    return "/rag-" in path or path.endswith("/chunks")


router = partition_router(owns, tags=["rag"])
