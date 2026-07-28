from scholarflow_api.routers._partition import partition_router


def owns(path: str) -> bool:
    return path.endswith("/papers") or "/literature/" in path


router = partition_router(owns, tags=["literature"])
