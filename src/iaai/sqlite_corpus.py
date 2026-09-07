"""Corpus persistence using the existing SQLite connection/migration boundary."""

import tempfile
import time

from iaai.corpus_domain import (
    Corpus,
    CorpusSnapshot,
    ExtractionArtifact,
    Source,
    SourceObservation,
    SourceRecord,
    TextChunk,
)
from iaai.errors import IAAIError


class SQLiteCorpusStore:
    def __init__(self, database):
        self.database = database

    def stage_raw(self, observation_id, body, policy):
        with self.database.connection() as c, c:
            c.execute("BEGIN IMMEDIATE")
            size = c.execute("SELECT coalesce(sum(length(body)),0) FROM raw_cache").fetchone()[0]
            if size + len(body) > policy.raw_cache_bytes:
                raise IAAIError("RAW_CACHE_LIMIT", "Кэш заполнен; дождитесь очистки по TTL.")
            c.execute("INSERT INTO raw_cache VALUES (?,?,?)", (observation_id, body, time.time()))

    def save_source(self, record):
        record = SourceRecord.model_validate_json(record.canonical_json())
        with self.database.connection() as c, c:
            c.execute(
                "INSERT INTO sources VALUES (?,?) ON CONFLICT(id) DO NOTHING",
                (record.source.source_id, record.source.canonical_json()),
            )
            c.execute(
                "INSERT INTO observations VALUES (?,?,?,?)",
                (
                    record.observation.observation_id,
                    record.observation.research_id,
                    record.source.source_id,
                    record.observation.canonical_json(),
                ),
            )
            c.execute(
                "INSERT INTO artifacts VALUES (?,?,?)",
                (
                    record.artifact.artifact_id,
                    record.observation.observation_id,
                    record.artifact.canonical_json(),
                ),
            )
            c.executemany(
                "INSERT INTO chunks VALUES (?,?,?)",
                [
                    (chunk.chunk_id, record.artifact.artifact_id, chunk.canonical_json())
                    for chunk in record.chunks
                ],
            )

    @staticmethod
    def _artifact(c, artifact_id):
        row = c.execute(
            "SELECT a.content,o.content,s.content FROM artifacts a "
            "JOIN observations o ON o.id=a.observation_id JOIN sources s ON s.id=o.source_id "
            "WHERE a.id=?",
            (artifact_id,),
        ).fetchone()
        if row is None:
            raise IAAIError("NOT_FOUND", "Источник не найден.")
        chunks = tuple(
            TextChunk.model_validate_json(item[0])
            for item in c.execute(
                "SELECT content FROM chunks WHERE artifact_id=? ORDER BY rowid", (artifact_id,)
            )
        )
        return SourceRecord(
            source=Source.model_validate_json(row[2]),
            observation=SourceObservation.model_validate_json(row[1]),
            artifact=ExtractionArtifact.model_validate_json(row[0]),
            chunks=chunks,
        )

    def artifact(self, artifact_id):
        with self.database.connection() as c:
            c.execute("BEGIN")
            return self._artifact(c, artifact_id)

    def source_records(self, research_id):
        with self.database.connection() as c:
            c.execute("BEGIN")
            ids = c.execute(
                "SELECT a.id FROM artifacts a JOIN observations o ON o.id=a.observation_id "
                "WHERE o.research_id=? ORDER BY o.rowid",
                (research_id,),
            ).fetchall()
            return tuple(self._artifact(c, row[0]) for row in ids)

    @staticmethod
    def _ids(c, research_id):
        return tuple(
            row[0]
            for row in c.execute(
                "SELECT artifact_id FROM corpus_members WHERE research_id=? ORDER BY artifact_id",
                (research_id,),
            )
        )

    def draft(self, research_id):
        with self.database.connection() as c:
            return Corpus(research_id=research_id, artifact_ids=self._ids(c, research_id))

    def select(self, research_id, artifact_id, include):
        with self.database.connection() as c, c:
            c.execute("BEGIN IMMEDIATE")
            record = self._artifact(c, artifact_id)
            if record.observation.research_id != research_id:
                raise IAAIError("RESEARCH_MISMATCH", "Источник относится к другому исследованию.")
            if include:
                c.execute(
                    "INSERT INTO corpus_members VALUES (?,?) ON CONFLICT DO NOTHING",
                    (research_id, artifact_id),
                )
            else:
                c.execute(
                    "DELETE FROM corpus_members WHERE research_id=? AND artifact_id=?",
                    (research_id, artifact_id),
                )

    def freeze(self, snapshot, expected_ids):
        snapshot = CorpusSnapshot.model_validate_json(snapshot.canonical_json())
        with self.database.connection() as c, c:
            c.execute("BEGIN IMMEDIATE")
            rid = snapshot.content.research_id
            current = c.execute(
                "SELECT current_revision FROM researches WHERE id=?", (rid,)
            ).fetchone()
            if (
                self._ids(c, rid) != expected_ids
                or current is None
                or current[0] != snapshot.content.research_revision
            ):
                raise IAAIError(
                    "CORPUS_CONFLICT", "Корпус или исследование изменились. Повторите фиксацию."
                )
            for ref in snapshot.content.artifacts:
                record = self._artifact(c, ref.artifact_id)
                if (
                    record.artifact.content_hash != ref.artifact_hash
                    or record.artifact.text_hash != ref.text_hash
                    or tuple(chunk.content_hash for chunk in record.chunks) != ref.chunk_hashes
                ):
                    raise IAAIError("CORPUS_CORRUPT", "Не совпадают ссылки корпуса.")
            c.execute(
                "INSERT INTO corpus_snapshots VALUES (?,?,?,?)",
                (snapshot.snapshot_id, rid, snapshot.version, snapshot.canonical_json()),
            )

    def snapshots(self, research_id):
        with self.database.connection() as c:
            return tuple(
                CorpusSnapshot.model_validate_json(row[0])
                for row in c.execute(
                    "SELECT content FROM corpus_snapshots WHERE research_id=? ORDER BY version",
                    (research_id,),
                )
            )

    def snapshot(self, snapshot_id):
        with self.database.connection() as c:
            row = c.execute(
                "SELECT content FROM corpus_snapshots WHERE id=?", (snapshot_id,)
            ).fetchone()
            if row is None:
                raise IAAIError("NOT_FOUND", "Снимок корпуса не найден.")
            return CorpusSnapshot.model_validate_json(row[0])

    def cleanup(self, policy):
        with self.database.connection() as c, c:
            c.execute("BEGIN IMMEDIATE")
            # Uncommitted observations can never be purged, including after a crash.
            rows = c.execute(
                "SELECT r.observation_id,length(r.body) FROM raw_cache r "
                "JOIN artifacts a ON a.observation_id=r.observation_id WHERE r.created<=?",
                (time.time() - policy.raw_cache_ttl_seconds,),
            ).fetchall()
            for oid, size in rows:
                c.execute("INSERT INTO cache_events VALUES (?,?,?)", (oid, time.time(), size))
                c.execute("DELETE FROM raw_cache WHERE observation_id=?", (oid,))
            return len(rows)

    def diagnostics(self):
        with self.database.connection() as c:
            size = c.execute("SELECT coalesce(sum(length(body)),0) FROM raw_cache").fetchone()[0]
            pending = c.execute(
                "SELECT count(*) FROM raw_cache WHERE observation_id NOT IN "
                "(SELECT observation_id FROM artifacts)"
            ).fetchone()[0]
            writable = False
            try:
                with tempfile.TemporaryFile(dir=self.database.path.parent) as file:
                    file.write(b"probe")
                    file.flush()
                writable = True
            except OSError:
                pass
            return {
                "raw_cache_bytes": size,
                "raw_cache_pending_records": pending,
                "cache_directory": str(self.database.path.parent),
                "cache_directory_writable": writable,
                "cache_storage": "SQLite transient BLOBs",
                "corpus_schema_version": 2,
            }
