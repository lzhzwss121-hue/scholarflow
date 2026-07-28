from __future__ import annotations

import ssl
import urllib.request
from typing import Any


def open_url(
    request: urllib.request.Request,
    *,
    timeout: float,
    context: ssl.SSLContext | None = None,
) -> Any:
    kwargs: dict[str, Any] = {"timeout": timeout}
    if context is not None:
        kwargs["context"] = context
    return urllib.request.urlopen(request, **kwargs)
