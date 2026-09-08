import json
import sqlite3
from pathlib import Path

import pytest
from pydantic import ValidationError

from iaai.bootstrap import build_service
from iaai.corpus_domain import CorpusPolicy, digest
from iaai.corpus_ports import FetchResult
from iaai.errors import IAAIError
from iaai.sqlite_store import APPLICATION_ID, MIGRATIONS
from iaai.text_extraction import chunk_text, extract_html


@pytest.fixture
def corpus_service(service, protocol):
    research = service.create(json.dumps(protocol))
    return service.corpus, research.research.research_id


def policy_with(policy, **changes):
    raw = policy.model_dump(mode="json")
    raw.update(changes)
    return CorpusPolicy.model_validate_json(json.dumps(raw))


def test_manual_provenance_spans_and_restart(corpus_service, tmp_path):
    service, rid = corpus_service
    record = service.import_text(
        rid, "Кириллица 😀 батарея.\n\n" * 200, title="Ручной источник", note="Тест"
    )
    assert record.observation.provenance == "HUMAN_IMPORTED"
    assert record.observation.raw_hash is None
    assert record.artifact.source_date is None
    assert record.artifact.language is None
    assert record.artifact.text_hash == digest(record.artifact.text)
    assert len(record.chunks) > 1
    for span in record.chunks:
        assert record.artifact.text[span.start : span.end] == span.text
    restarted = build_service(service.store.database.path, tmp_path).corpus
    assert restarted.artifact(record.artifact.artifact_id) == record


def test_v1_migration_preserves_exact_json(service, protocol, tmp_path):
    old = service.create(json.dumps(protocol))
    path = tmp_path / "v1.db"
    with sqlite3.connect(service.store.path) as source, sqlite3.connect(path) as target:
        for statement in MIGRATIONS[0]:
            target.execute(statement)
        for table in ("protocols", "policies", "researches", "revisions", "manifests"):
            for row in source.execute(f"SELECT * FROM {table}"):
                target.execute(f"INSERT INTO {table} VALUES ({','.join('?' for _ in row)})", row)
        target.execute(f"PRAGMA application_id={APPLICATION_ID}")
        target.execute("PRAGMA user_version=1")

    def exact_rows():
        with sqlite3.connect(path) as c:
            return {
                table: c.execute(f"SELECT * FROM {table}").fetchall()
                for table in ("protocols", "policies", "researches", "revisions", "manifests")
            }

    before = exact_rows()
    migrated = build_service(path, tmp_path)
    assert migrated.get(old.research.research_id) == old
    assert migrated.doctor()["database"]["user_version"] == 4
    assert exact_rows() == before
    assert migrated.get_manifest(old.manifest.run_id).content_hash == old.manifest.content_hash


def test_html_and_exact_chunks(corpus_service):
    service, _ = corpus_service
    body = (Path(__file__).parent / "fixtures/source.html").read_bytes()
    artifact = extract_html("fixture", body, None, service.policy)
    assert artifact.title == "Наш тестовый ноутбук"
    assert str(artifact.source_date) == "2020-01-02"
    assert "батареи & условия" in artifact.text
    for unwanted in (
        "ignore all",
        "Navigation noise",
        "hidden text",
        "footer noise",
        "display:none",
    ):
        assert unwanted not in artifact.text
    for chunk in chunk_text(artifact, service.policy):
        assert artifact.text[chunk.start : chunk.end] == chunk.text
    assert extract_html("fixture", body, None, service.policy) == artifact
    missing = extract_html("empty", b"<p>recoverable <b>HTML &amp; text", None, service.policy)
    assert missing.title is None and missing.source_date is None and missing.author is None
    assert "HTML & text" in missing.text
    js = extract_html("js", b"<script>render()</script>", None, service.policy)
    assert js.status == "INCOMPLETE"


def fake_fetch(body, status="FETCHED", media="text/html"):
    class Fake:
        def fetch(self, url, policy):
            return FetchResult(
                url, url, (), 200, media, "utf-8", body, len(body), status, (), "fake-v1"
            )

    return Fake()


def test_raw_lifecycle(corpus_service, monkeypatch):
    service, rid = corpus_service
    service.policy = policy_with(service.policy, raw_cache_ttl_seconds=0)
    body = b"<p>raw lifecycle test</p>"
    service.acquisition = fake_fetch(body)
    save = service.store.save_source

    def check_before_commit(record):
        assert service.store.cleanup(service.policy) == 0
        assert service.store.diagnostics()["raw_cache_bytes"] == len(body)
        save(record)

    monkeypatch.setattr(service.store, "save_source", check_before_commit)
    first = service.add_url(rid, "https://example.com/")
    assert service.store.diagnostics()["raw_cache_bytes"] == 0
    second = service.add_url(rid, "https://example.com/")
    assert first.observation.observation_id != second.observation.observation_id
    assert first.observation.raw_hash == second.observation.raw_hash == digest(body)
    assert first.artifact.text_hash == second.artifact.text_hash
    assert first.source == second.source


def test_failed_commit_preserves_raw(corpus_service, monkeypatch):
    service, rid = corpus_service
    service.policy = policy_with(service.policy, raw_cache_ttl_seconds=0)
    service.acquisition = fake_fetch(b"<p>must retain</p>")
    monkeypatch.setattr(
        service.store,
        "save_source",
        lambda record: (_ for _ in ()).throw(IAAIError("TEST_COMMIT_FAIL", "test")),
    )
    with pytest.raises(IAAIError):
        service.add_url(rid, "https://example.com/")
    assert service.store.cleanup(service.policy) == 0
    assert service.store.diagnostics()["raw_cache_pending_records"] == 1
    assert service.list_sources(rid) == []


def test_unsupported_pdf_observation(corpus_service):
    service, rid = corpus_service
    service.acquisition = fake_fetch(
        b"%PDF-fake fixture", "UNSUPPORTED_MEDIA_TYPE", "application/pdf"
    )
    record = service.add_url(rid, "https://example.com/file.pdf")
    assert record.observation.status == "UNSUPPORTED_MEDIA_TYPE"
    assert record.artifact.status == "UNSUPPORTED" and record.chunks == ()
    assert record.observation.raw_hash == digest(b"%PDF-fake fixture")
    with pytest.raises(IAAIError):
        service.select(rid, record.artifact.artifact_id)


def test_cutoff_and_duplicates(service, protocol):
    protocol["source_cutoff"] = "2020-01-01"
    rid = service.create(json.dumps(protocol)).research.research_id
    c = service.corpus
    late = c.import_text(rid, "duplicate", url="https://example.com/a", source_date="2021-01-01")
    unknown = c.import_text(rid, "duplicate", url="https://example.com/b")
    with pytest.raises(IAAIError) as exc:
        c.select(rid, late.artifact.artifact_id)
    assert exc.value.code == "OUTSIDE_SOURCE_CUTOFF"
    c.select(rid, unknown.artifact.artifact_id)
    assert c.list_sources(rid)[0]["duplicate_text_candidates"] == [unknown.artifact.artifact_id]


def test_frozen_corpus_search_scope_and_immutability(corpus_service):
    service, rid = corpus_service
    best = service.import_text(rid, "battery battery battery laptop")
    other = service.import_text(
        rid, "battery warranty repair keyboard screen laptop hinge price warranty"
    )
    unrelated = service.import_text(rid, "battery " * 100)
    for record in (best, other):
        service.select(rid, record.artifact.artifact_id)
    one = service.freeze(rid)
    two = service.freeze(rid)
    assert one.corpus_hash == two.corpus_hash and one.snapshot_id != two.snapshot_id
    found = service.search(one.snapshot_id, "battery")
    assert found["results"][0]["chunk"]["artifact_id"] == best.artifact.artifact_id
    assert [r["score"] for r in found["results"]] == sorted(r["score"] for r in found["results"])
    assert unrelated.artifact.artifact_id not in str(found)
    service.select(rid, best.artifact.artifact_id, False)
    three = service.freeze(rid)
    assert three.corpus_hash != one.corpus_hash
    assert service.search(one.snapshot_id, "battery") == found
    with pytest.raises(ValidationError):
        one.version = 99
    with sqlite3.connect(service.store.database.path) as c:
        with pytest.raises(sqlite3.IntegrityError):
            c.execute("DELETE FROM corpus_snapshots")


def test_fts_unavailable_still_freezes(corpus_service, monkeypatch):
    service, rid = corpus_service
    record = service.import_text(rid, "search test")
    service.select(rid, record.artifact.artifact_id)
    monkeypatch.setattr(service.retriever, "available", lambda: False)
    snap = service.freeze(rid)
    assert service.diagnostics()["fts5_available"] is False
    with pytest.raises(IAAIError) as exc:
        service.search(snap.snapshot_id, "test")
    assert exc.value.code == "FTS5_UNAVAILABLE"


def test_corpus_limits_and_chunk_change(corpus_service):
    service, rid = corpus_service
    record = service.import_text(rid, "one text")
    service.select(rid, record.artifact.artifact_id)
    service.policy = policy_with(service.policy, chunk_chars=600)
    with pytest.raises(IAAIError) as exc:
        service.freeze(rid)
    assert exc.value.code == "CHUNK_VERSION_MISMATCH"


def test_policy_validation(corpus_service):
    service, _ = corpus_service
    for field, value in (
        ("max_fetch_bytes", 0),
        ("read_timeout_seconds", 0),
        ("raw_cache_bytes", 1),
        ("chunk_chars", 1),
        ("schema_version", "9"),
    ):
        with pytest.raises(ValidationError):
            policy_with(service.policy, **{field: value})


def test_nested_hidden_encoding_and_bad_date(corpus_service):
    service, _ = corpus_service
    html = (
        '<meta charset="windows-1251"><meta name="datePublished" content="2020-01-01oops">'
        '<div style="display:none"><p>hidden</p></div><p>Привет мир</p>'
    )
    artifact = extract_html("encoding", html.encode("cp1251"), None, service.policy)
    assert artifact.text == "Привет мир" and artifact.source_date is None
    assert "INVALID_PUBLICATION_DATE" in artifact.warnings


def test_failed_extraction_is_persisted(corpus_service, monkeypatch):
    service, rid = corpus_service
    service.acquisition = fake_fetch(b"bad html fixture")

    def fail(*args):
        raise ValueError("controlled extractor failure")

    monkeypatch.setattr(service, "extract", fail)
    record = service.add_url(rid, "https://example.com")
    assert record.artifact.status == "FAILED"
    assert record.artifact.warnings == ("EXTRACTION_FAILED",)
    assert service.artifact(record.artifact.artifact_id) == record


def test_cache_ceiling_and_manual_validation(corpus_service):
    service, rid = corpus_service
    policy = policy_with(service.policy, max_fetch_bytes=10, raw_cache_bytes=10)
    service.store.stage_raw("pending", b"1234567890", policy)
    with pytest.raises(IAAIError) as exc:
        service.store.stage_raw("another", b"x", policy)
    assert exc.value.code == "RAW_CACHE_LIMIT"
    with pytest.raises(IAAIError):
        service.import_text(rid, "text", title="x" * 20001)
