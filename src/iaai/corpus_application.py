"""Preparation use cases; no Flask, SQL or concrete HTTP implementation."""

from datetime import UTC, date, datetime
from functools import wraps
from uuid import uuid4

from pydantic import ValidationError

from iaai.application import validation_error
from iaai.corpus_domain import (
    ArtifactReference,
    CorpusContent,
    CorpusSnapshot,
    ExtractionArtifact,
    Source,
    SourceObservation,
    SourceRecord,
    digest,
)
from iaai.corpus_ports import Acquisition, CorpusStore, Retriever
from iaai.errors import IAAIError
from iaai.ports import ResearchStore
from iaai.source_urls import canonical_url


def validated_operation(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except ValidationError as exc:
            raise validation_error(exc) from exc

    return wrapped


class CorpusService:
    def __init__(
        self,
        researches: ResearchStore,
        store: CorpusStore,
        acquisition: Acquisition,
        retriever: Retriever,
        policy,
        extract,
        chunk,
        normalize,
    ):
        self.researches, self.store = researches, store
        self.acquisition, self.retriever, self.policy = acquisition, retriever, policy
        self.extract, self.chunk, self.normalize = extract, chunk, normalize

    @validated_operation
    def add_url(self, research_id, url, initiated_by="local-user"):
        research = self.researches.load(research_id)
        url = canonical_url(url)
        self.store.cleanup(self.policy)
        result = self.acquisition.fetch(url, self.policy)
        oid = str(uuid4())
        source = Source(source_id="src_" + digest(url), canonical_url=url, identity_kind="URL")
        observation = SourceObservation(
            observation_id=oid,
            research_id=research_id,
            research_revision=research.research.current_revision,
            source_id=source.source_id,
            requested_url=url,
            final_url=result.final_url,
            redirect_chain=result.redirect_chain,
            retrieved_at=datetime.now(UTC),
            http_status=result.http_status,
            media_type=result.media_type,
            raw_hash=digest(result.body) if result.body is not None else None,
            byte_count=result.byte_count,
            status=result.status,
            adapter_version=result.adapter_version,
            provenance="DIRECT_HTTP",
            initiated_by=initiated_by,
            note="",
            warnings=result.warnings,
            policy=self.policy,
        )
        if result.body is not None:
            self.store.stage_raw(oid, result.body, self.policy)
        artifact = None
        extraction_failure = result.status
        if result.status == "FETCHED" and result.body is not None:
            try:
                artifact = self.extract(oid, result.body, result.charset, self.policy)
            except (ValueError, UnicodeError, RecursionError):
                extraction_failure = "EXTRACTION_FAILED"
        if artifact is None:
            artifact = ExtractionArtifact(
                artifact_id="art_" + oid,
                observation_id=oid,
                text="",
                text_hash=digest(""),
                extractor_version="not-extracted-v1",
                encoding=None,
                language=None,
                title=None,
                author=None,
                source_date=None,
                metadata_origin="UNKNOWN",
                status="UNSUPPORTED" if result.status == "UNSUPPORTED_MEDIA_TYPE" else "FAILED",
                warnings=(extraction_failure,),
            )
        record = SourceRecord(
            source=source,
            observation=observation,
            artifact=artifact,
            chunks=self.chunk(artifact, self.policy),
        )
        self.store.save_source(record)
        self.store.cleanup(self.policy)
        return record

    @validated_operation
    def import_text(
        self,
        research_id,
        text,
        url=None,
        title=None,
        source_date=None,
        initiated_by="local-user",
        note="",
    ):
        research = self.researches.load(research_id)
        if not initiated_by.strip():
            raise IAAIError("IMPORT_PROVENANCE", "Укажите, кто инициировал импорт.")
        try:
            supplied_date = date.fromisoformat(source_date) if source_date else None
        except ValueError as exc:
            raise IAAIError(
                "IMPORT_DATE", "Дата источника должна иметь формат ГГГГ-ММ-ДД."
            ) from exc
        if len(text) > self.policy.max_text_chars:
            raise IAAIError("TEXT_LIMIT", "Текст превышает лимит импорта.")
        normalized = self.normalize(text)
        if not normalized:
            raise IAAIError("EMPTY_TEXT", "Введите текст источника.")
        url = canonical_url(url) if url else None
        oid = str(uuid4())
        source = Source(
            source_id="src_" + digest(url) if url else "src_" + oid,
            canonical_url=url,
            identity_kind="URL" if url else "MANUAL",
        )
        observation = SourceObservation(
            observation_id=oid,
            research_id=research_id,
            research_revision=research.research.current_revision,
            source_id=source.source_id,
            requested_url=url,
            final_url=None,
            redirect_chain=(),
            retrieved_at=datetime.now(UTC),
            http_status=None,
            media_type="text/plain",
            raw_hash=None,
            byte_count=len(normalized.encode("utf-8")),
            status="HUMAN_IMPORTED",
            adapter_version="manual-normalized-v1",
            provenance="HUMAN_IMPORTED",
            initiated_by=initiated_by,
            note=note,
            warnings=("RAW_EXTRACTION_REPLAY_UNAVAILABLE",),
            policy=self.policy,
        )
        artifact = ExtractionArtifact(
            artifact_id="art_" + oid,
            observation_id=oid,
            text=normalized,
            text_hash=digest(normalized),
            extractor_version="human-normalized-v1",
            encoding=None,
            language=None,
            title=title or None,
            author=None,
            source_date=supplied_date,
            metadata_origin="HUMAN_SUPPLIED",
            status="HUMAN_IMPORTED",
            warnings=("RAW_EXTRACTION_REPLAY_UNAVAILABLE", "HUMAN_SUPPLIED_METADATA"),
        )
        record = SourceRecord(
            source=source,
            observation=observation,
            artifact=artifact,
            chunks=self.chunk(artifact, self.policy),
        )
        self.store.save_source(record)
        return record

    def list_sources(self, research_id):
        self.researches.load(research_id)
        records = self.store.source_records(research_id)
        return [
            {
                "record": record.model_dump(mode="json"),
                "eligibility": self.eligibility(research_id, record),
                "duplicate_text_candidates": [
                    other.artifact.artifact_id
                    for other in records
                    if other.artifact.artifact_id != record.artifact.artifact_id
                    and other.artifact.text
                    and other.artifact.text_hash == record.artifact.text_hash
                ],
            }
            for record in records
        ]

    def eligibility(self, research_id, record):
        protocol = self.researches.load(research_id).protocol
        if (
            protocol.source_cutoff
            and record.artifact.source_date
            and record.artifact.source_date > protocol.source_cutoff
        ):
            return "OUTSIDE_SOURCE_CUTOFF"
        if record.artifact.status not in ("EXTRACTED", "HUMAN_IMPORTED"):
            return "ARTIFACT_NOT_ACCEPTABLE"
        return "SOURCE_DATE_UNKNOWN" if record.artifact.source_date is None else "ELIGIBLE"

    def artifact(self, artifact_id):
        return self.store.artifact(artifact_id)

    def corpus(self, research_id):
        self.researches.load(research_id)
        return {
            "draft": self.store.draft(research_id).model_dump(mode="json"),
            "snapshots": [s.model_dump(mode="json") for s in self.store.snapshots(research_id)],
        }

    def select(self, research_id, artifact_id, include=True):
        record = self.store.artifact(artifact_id)
        if include:
            status = self.eligibility(research_id, record)
            if status not in ("ELIGIBLE", "SOURCE_DATE_UNKNOWN"):
                raise IAAIError(
                    status, "Источник нельзя включить: проверьте дату и результат извлечения."
                )
        self.store.select(research_id, artifact_id, include)
        return self.corpus(research_id)

    @validated_operation
    def freeze(self, research_id, initiated_by="local-user"):
        research = self.researches.load(research_id)
        draft = self.store.draft(research_id)
        if not draft.artifact_ids:
            raise IAAIError("EMPTY_CORPUS", "Сначала включите хотя бы один источник в корпус.")
        if len(draft.artifact_ids) > self.policy.max_corpus_artifacts:
            raise IAAIError("CORPUS_LIMIT", "Слишком много источников в корпусе.")
        refs, total = [], 0
        for aid in draft.artifact_ids:
            record = self.store.artifact(aid)
            status = self.eligibility(research_id, record)
            if status not in ("ELIGIBLE", "SOURCE_DATE_UNKNOWN"):
                raise IAAIError(status, "Исключите недопустимый источник перед фиксацией.")
            total += len(record.artifact.text)
            if total > self.policy.max_corpus_chars:
                raise IAAIError("CORPUS_LIMIT", "Превышен лимит текста корпуса.")
            if (
                record.observation.policy.chunk_chars != self.policy.chunk_chars
                or record.observation.policy.chunking_version != self.policy.chunking_version
            ):
                raise IAAIError(
                    "CHUNK_VERSION_MISMATCH",
                    "Нужен новый импорт с текущими настройками фрагментов.",
                )
            refs.append(
                ArtifactReference(
                    artifact_id=aid,
                    artifact_hash=record.artifact.content_hash,
                    text_hash=record.artifact.text_hash,
                    source_id=record.source.source_id,
                    chunk_hashes=tuple(c.content_hash for c in record.chunks),
                )
            )
        content = CorpusContent(
            research_id=research_id,
            research_revision=research.research.current_revision,
            protocol_hash=research.protocol.content_hash,
            artifacts=tuple(refs),
            policy=self.policy,
            index_runtime=self.retriever.runtime_version(),
        )
        snapshots = self.store.snapshots(research_id)
        snapshot = CorpusSnapshot(
            snapshot_id=str(uuid4()),
            version=len(snapshots) + 1,
            created_at=datetime.now(UTC),
            initiated_by=initiated_by,
            content=content,
            corpus_hash=content.content_hash,
        )
        self.store.freeze(snapshot, draft.artifact_ids)
        return snapshot

    def snapshot(self, snapshot_id):
        return self.store.snapshot(snapshot_id)

    def search(self, snapshot_id, query):
        snapshot = self.store.snapshot(snapshot_id)
        if len(query) > snapshot.content.policy.query_chars:
            raise IAAIError("QUERY_LIMIT", "Слишком длинный поисковый запрос.")
        if snapshot.content.index_runtime != self.retriever.runtime_version():
            raise IAAIError(
                "INDEX_VERSION_MISMATCH", "Версия SQLite изменилась; создайте новый снимок."
            )
        chunks, sources = [], {}
        for ref in snapshot.content.artifacts:
            record = self.store.artifact(ref.artifact_id)
            if (
                record.artifact.content_hash != ref.artifact_hash
                or tuple(c.content_hash for c in record.chunks) != ref.chunk_hashes
            ):
                raise IAAIError("CORPUS_CORRUPT", "Хеши корпуса не совпадают.")
            chunks.extend(record.chunks)
            sources[ref.artifact_id] = record.source.source_id
        results = self.retriever.search(tuple(chunks), query, snapshot.content.policy.search_limit)
        for result in results:
            result["source_id"] = sources[result["chunk"]["artifact_id"]]
            result["preview"] = result["chunk"]["text"]
        return {
            "snapshot_id": snapshot_id,
            "corpus_hash": snapshot.corpus_hash,
            "query": query,
            "index_version": snapshot.content.index_runtime,
            "results": results,
        }

    def diagnostics(self):
        self.store.cleanup(self.policy)
        return {
            **self.store.diagnostics(),
            "fts5_available": self.retriever.available(),
            "index_version": self.retriever.runtime_version(),
            "policy_hash": self.policy.content_hash,
        }
