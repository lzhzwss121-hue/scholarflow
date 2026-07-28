from scholarflow_api.routers._partition import partition_router


router = partition_router(lambda path: path.startswith("/agent/"), tags=["workflow-runs"])
