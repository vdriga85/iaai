"""Immutable preparation records, separate from Step 1 snapshots."""

import hashlib
from datetime import date, datetime
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from iaai.domain import Hash, Identifier, Positive, Snapshot, Text


def digest(value: str | bytes) -> str:
    return hashlib.sha256(value.encode("utf-8") if isinstance(value, str) else value).hexdigest()


class CorpusPolicy(Snapshot):
    schema_version: Literal["0.2"]
    policy_id: Literal["phase1-corpus"]
    version: Positive
    status: Literal["UNVALIDATED"]
    connect_timeout_seconds: Annotated[int, Field(gt=0, le=60)]
    read_timeout_seconds: Annotated[int, Field(gt=0, le=60)]
    fetch_deadline_seconds: Annotated[int, Field(gt=0, le=300)]
    max_fetch_bytes: Annotated[int, Field(gt=0, le=16 * 1024 * 1024)]
    max_redirects: Annotated[int, Field(ge=0, le=10)]
    raw_cache_bytes: Positive
    raw_cache_ttl_seconds: Annotated[int, Field(ge=0)]
    max_text_chars: Positive
    chunk_chars: Annotated[int, Field(ge=50, le=20000)]
    max_corpus_artifacts: Annotated[int, Field(gt=0, le=500)]
    max_corpus_chars: Positive
    search_limit: Annotated[int, Field(gt=0, le=100)]
    query_chars: Annotated[int, Field(gt=0, le=2000)]
    chunking_version: Literal["block-char-v1"]
    index_version: Literal["fts5-unicode61-bm25-v1"]
    supported_media_types: tuple[Literal["text/html", "application/xhtml+xml"], ...]

    @model_validator(mode="after")
    def ceilings(self) -> Self:
        if self.max_fetch_bytes > self.raw_cache_bytes:
            raise ValueError("fetch exceeds raw cache ceiling")
        if self.max_text_chars > self.max_corpus_chars or self.chunk_chars > self.max_text_chars:
            raise ValueError("incompatible text/chunk/corpus ceilings")
        if (
            max(self.connect_timeout_seconds, self.read_timeout_seconds)
            > self.fetch_deadline_seconds
        ):
            raise ValueError("timeout exceeds fetch deadline")
        if not self.supported_media_types:
            raise ValueError("supported media types cannot be empty")
        return self


class Source(Snapshot):
    source_id: Identifier
    canonical_url: Text | None
    identity_kind: Literal["URL", "MANUAL"]


class SourceObservation(Snapshot):
    observation_id: Identifier
    research_id: Identifier
    research_revision: Positive
    source_id: Identifier
    requested_url: Text | None
    final_url: Text | None
    redirect_chain: tuple[Text, ...]
    retrieved_at: datetime
    http_status: int | None
    media_type: Text | None
    raw_hash: Hash | None
    byte_count: Annotated[int, Field(ge=0)]
    status: Text
    adapter_version: Text
    provenance: Literal["DIRECT_HTTP", "HUMAN_IMPORTED"]
    initiated_by: Text
    note: str
    warnings: tuple[Text, ...]
    policy: CorpusPolicy


class ExtractionArtifact(Snapshot):
    artifact_id: Identifier
    observation_id: Identifier
    text: str
    text_hash: Hash
    extractor_version: Text
    encoding: Text | None
    language: Text | None
    title: Text | None
    author: Text | None
    source_date: date | None
    metadata_origin: Literal["HTML_DECLARED", "HUMAN_SUPPLIED", "UNKNOWN"]
    status: Literal["EXTRACTED", "HUMAN_IMPORTED", "INCOMPLETE", "UNSUPPORTED", "FAILED"]
    warnings: tuple[Text, ...]

    @model_validator(mode="after")
    def text_integrity(self) -> Self:
        if digest(self.text) != self.text_hash:
            raise ValueError("artifact text hash mismatch")
        if self.status in ("EXTRACTED", "HUMAN_IMPORTED") and not self.text.strip():
            raise ValueError("successful extraction requires nonempty text")
        return self


class TextChunk(Snapshot):
    chunk_id: Identifier
    artifact_id: Identifier
    text_hash: Hash
    start: Annotated[int, Field(ge=0)]
    end: Positive
    text: Text
    chunk_hash: Hash
    chunking_version: Text

    @model_validator(mode="after")
    def integrity(self) -> Self:
        if self.end <= self.start or len(self.text) != self.end - self.start:
            raise ValueError("invalid offsets")
        if self.chunk_hash != digest(self.text):
            raise ValueError("chunk hash mismatch")
        return self


class SourceRecord(Snapshot):
    source: Source
    observation: SourceObservation
    artifact: ExtractionArtifact
    chunks: tuple[TextChunk, ...]

    @model_validator(mode="after")
    def references(self) -> Self:
        if (
            self.source.source_id != self.observation.source_id
            or self.observation.observation_id != self.artifact.observation_id
        ):
            raise ValueError("source observation artifact mismatch")
        for chunk in self.chunks:
            if (
                chunk.artifact_id != self.artifact.artifact_id
                or chunk.text_hash != self.artifact.text_hash
                or self.artifact.text[chunk.start : chunk.end] != chunk.text
            ):
                raise ValueError("exact span invariant failed")
        return self


class Corpus(Snapshot):
    research_id: Identifier
    artifact_ids: tuple[Identifier, ...]


class ArtifactReference(Snapshot):
    artifact_id: Identifier
    artifact_hash: Hash
    text_hash: Hash
    source_id: Identifier
    chunk_hashes: tuple[Hash, ...]


class CorpusContent(Snapshot):
    research_id: Identifier
    research_revision: Positive
    protocol_hash: Hash
    artifacts: tuple[ArtifactReference, ...]
    policy: CorpusPolicy
    index_runtime: Text


class CorpusSnapshot(Snapshot):
    snapshot_id: Identifier
    version: Positive
    created_at: datetime
    initiated_by: Text
    content: CorpusContent
    corpus_hash: Hash

    @model_validator(mode="after")
    def integrity(self) -> Self:
        if self.corpus_hash != self.content.content_hash or not self.content.artifacts:
            raise ValueError("invalid frozen corpus content")
        ids = [ref.artifact_id for ref in self.content.artifacts]
        if ids != sorted(set(ids)):
            raise ValueError("artifact references must be unique and canonical")
        return self
