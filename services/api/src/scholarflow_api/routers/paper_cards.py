from scholarflow_api.routers._partition import partition_router


def owns(path: str) -> bool:
    return "/paper-cards" in path or path.endswith("/full-text")


router = partition_router(owns, tags=["paper-cards"])
