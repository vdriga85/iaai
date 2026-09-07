"""Composition root: concrete adapter selection and packaged defaults."""

from importlib.resources import files
from pathlib import Path

from iaai.application import ResearchService, parse_policy
from iaai.environment import capture_runtime, system_diagnostics
from iaai.sqlite_store import SQLiteResearchStore


def build_service(database: Path | None = None, repository: Path | None = None) -> ResearchService:
    repository = repository or Path.cwd()
    database = database or repository / "runtime" / "iaai.db"
    policy = parse_policy(files("iaai").joinpath("default-policy-v0.1.json").read_text("utf-8"))
    store = SQLiteResearchStore(database, policy.runtime.sqlite_busy_timeout_seconds)
    return ResearchService(
        store,
        policy,
        lambda: capture_runtime(repository),
        lambda: system_diagnostics(database, repository),
    )
