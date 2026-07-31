from __future__ import annotations

from contextlib import contextmanager
import os
from typing import Iterator, NamedTuple
from unittest.mock import Mock, patch

from scholarflow_api.agent_core import LocalHeuristicProvider


OFFLINE_MODEL_ENVIRONMENT = {
    "SCHOLARFLOW_MODEL_PROVIDER": "local",
    "OPENROUTER_API_KEY": "",
    "DEEPSEEK_API_KEY": "",
}


class OfflineModelHarness(NamedTuple):
    provider: LocalHeuristicProvider
    provider_factory: Mock
    external_request: Mock


@contextmanager
def offline_model_environment() -> Iterator[OfflineModelHarness]:
    """Force ordinary workflow tests through the deterministic local provider."""

    provider = LocalHeuristicProvider()
    with patch.dict(
        os.environ,
        OFFLINE_MODEL_ENVIRONMENT,
        clear=False,
    ), patch(
        "scholarflow_api.services.agent_plan_service.get_model_provider",
        return_value=provider,
    ) as provider_factory, patch(
        "scholarflow_api.agent_core.open_url",
        side_effect=AssertionError(
            "ordinary workflow tests must not call an external model endpoint"
        ),
    ) as external_request:
        yield OfflineModelHarness(
            provider=provider,
            provider_factory=provider_factory,
            external_request=external_request,
        )
