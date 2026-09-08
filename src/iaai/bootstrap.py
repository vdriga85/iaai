"""Composition root: concrete adapter selection and packaged defaults."""

import os
from importlib.resources import files
from pathlib import Path

from iaai.application import ResearchService, parse_policy
from iaai.corpus_application import CorpusService
from iaai.corpus_domain import CorpusPolicy
from iaai.environment import capture_runtime, system_diagnostics
from iaai.fts_retrieval import FTS5Retriever
from iaai.http_acquisition import PublicHTTPAcquisition
from iaai.local_proposal_model import LocalProposalModel
from iaai.proposal_application import ProposalService
from iaai.proposal_domain import ProposalPolicy
from iaai.sqlite_corpus import SQLiteCorpusStore
from iaai.sqlite_proposals import SQLiteProposalStore
from iaai.sqlite_store import SQLiteResearchStore
from iaai.text_extraction import chunk_text, extract_html, normalize_text


def build_service(database: Path | None = None, repository: Path | None = None) -> ResearchService:
    repository = repository or Path.cwd()
    database = database or repository / "runtime" / "iaai.db"
    policy = parse_policy(files("iaai").joinpath("default-policy-v0.1.json").read_text("utf-8"))
    store = SQLiteResearchStore(database, policy.runtime.sqlite_busy_timeout_seconds)
    corpus_policy = CorpusPolicy.model_validate_json(
        files("iaai").joinpath("corpus-policy-v0.2.json").read_text("utf-8")
    )
    corpus = CorpusService(
        store,
        SQLiteCorpusStore(store),
        PublicHTTPAcquisition(),
        FTS5Retriever(),
        corpus_policy,
        extract_html,
        chunk_text,
        normalize_text,
    )
    service = ResearchService(
        store,
        policy,
        lambda: capture_runtime(repository),
        lambda: system_diagnostics(database, repository),
        corpus,
    )
    service.proposals = ProposalService(
        store,
        corpus,
        SQLiteProposalStore(store),
        LocalProposalModel(
            os.environ.get("IAAI_MODEL_CONFIG", str(repository / "runtime/model-config.json"))
        ),
        ProposalPolicy(),
    )
    return service
