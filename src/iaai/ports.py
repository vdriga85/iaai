"""The single storage boundary used by the application."""

from typing import Protocol

from iaai.domain import Research, RevisionBundle, RunManifest


class ResearchStore(Protocol):
    def save(self, bundle: RevisionBundle, expected_revision: int) -> None: ...

    def list_researches(self) -> tuple[Research, ...]: ...

    def load(self, research_id: str, revision: int | None = None) -> RevisionBundle: ...

    def manifest(self, run_id: str) -> RunManifest: ...

    def diagnostics(self) -> dict: ...
