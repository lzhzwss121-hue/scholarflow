"""ScholarFlow API package."""

from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dependency is optional for import-time resilience.
    load_dotenv = None


def load_project_environment() -> None:
    if load_dotenv is None:
        return
    candidates = [
        Path.cwd() / ".env",
        Path(__file__).resolve().parents[4] / ".env",
    ]
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen or not resolved.exists():
            continue
        load_dotenv(resolved, override=False)
        seen.add(resolved)


load_project_environment()

__version__ = "0.1.0"
