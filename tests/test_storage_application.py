import json
import sqlite3
import subprocess
import sys

import pytest

from iaai.bootstrap import build_service
from iaai.errors import IAAIError
from iaai.sqlite_store import APPLICATION_ID


def test_atomic_create_restart_and_manifest(service, protocol, tmp_path):
    bundle = service.create(json.dumps(protocol))
    research_id = bundle.research.research_id
    assert service.list_researches() == (bundle.research,)
    assert service.get(research_id) == bundle
    assert service.get_manifest(bundle.manifest.run_id) == bundle.manifest
    assert bundle.policy.status == "UNVALIDATED"
    assert bundle.protocol.constraints == ()
    restarted = build_service(service.store.path, tmp_path)
    assert restarted.get(research_id) == bundle
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "iaai",
            "--db",
            str(service.store.path),
            "research",
            "show",
            research_id,
        ],
        capture_output=True,
        text=True,
    )
    assert process.returncode == 0, process.stderr
    assert json.loads(process.stdout)["manifest"]["run_id"] == bundle.manifest.run_id
    diagnostics = service.doctor()
    assert diagnostics["ok"]
    db = diagnostics["database"]
    assert (
        db["journal_mode"],
        db["synchronous"],
        db["foreign_keys"],
        db["busy_timeout"],
        db["user_version"],
    ) == ("wal", 2, 1, 5000, 4)
    assert bundle.manifest.runtime.python_version
    assert bundle.manifest.runtime.git_status == "UNAVAILABLE"


def test_revisions_preserve_snapshots(service, protocol, policy):
    first = service.create(json.dumps(protocol))
    protocol["geography"] = "Germany"
    protocol["version"] = 2
    policy["version"] = 2
    policy["parent_policy_hash"] = first.policy.content_hash
    policy["stop"]["novelty_ceiling"] = 0.1
    second = service.revise(first.research.research_id, json.dumps(protocol), json.dumps(policy))
    assert second.revision.revision == 2
    assert second.policy.content_hash != first.policy.content_hash
    old = service.get(first.research.research_id, 1)
    assert old.protocol == first.protocol
    assert old.policy == first.policy
    assert old.manifest == first.manifest
    assert old.research.current_revision == 2
    assert service.get(first.research.research_id).revision == second.revision
    with pytest.raises(IAAIError, match="not changed"):
        service.revise(first.research.research_id, json.dumps(protocol), json.dumps(policy))


def test_invalid_revision_and_unknown(service, protocol, policy):
    first = service.create(json.dumps(protocol))
    protocol["geography"] = "Germany"
    with pytest.raises(IAAIError) as failure:
        service.revise(first.research.research_id, json.dumps(protocol), json.dumps(policy))
    assert failure.value.code == "VERSION_CONFLICT"
    for operation in (
        lambda: service.get("missing"),
        lambda: service.get_manifest("missing"),
        lambda: service.get(first.research.research_id, 20),
    ):
        with pytest.raises(IAAIError) as failure:
            operation()
        assert failure.value.code == "NOT_FOUND"


def test_invalid_config_creates_nothing(service, protocol, policy):
    policy["resources"]["rss_bytes"] = 0
    with pytest.raises(IAAIError):
        service.create(json.dumps(protocol), json.dumps(policy))
    assert not service.store.path.exists()


def test_rollback_on_manifest_failure(service, protocol, monkeypatch):
    first = service.create(json.dumps(protocol))
    # A duplicate run ID fails at revision/manifest insertion AFTER the new research insert.
    import iaai.application as application

    ids = iter(["another-research", first.manifest.run_id])
    monkeypatch.setattr(application, "uuid4", lambda: next(ids))
    with pytest.raises(IAAIError):
        service.create(json.dumps(protocol))
    assert service.list_researches() == (first.research,)
    with sqlite3.connect(service.store.path) as connection:
        for table in ("researches", "protocols", "policies", "revisions", "manifests"):
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 1


def test_immutable_tables(service, protocol):
    service.create(json.dumps(protocol))
    with sqlite3.connect(service.store.path) as connection:
        for table in ("protocols", "policies", "revisions", "manifests"):
            with pytest.raises(sqlite3.IntegrityError, match="immutable"):
                connection.execute(f"DELETE FROM {table}")
            with pytest.raises(sqlite3.IntegrityError, match="immutable"):
                connection.execute(f"UPDATE {table} SET content='{{}}'")


@pytest.mark.parametrize("kind", ["directory", "corrupt", "future", "foreign", "missing_table"])
def test_database_failures(tmp_path, kind):
    path = tmp_path / "bad.db"
    if kind == "directory":
        path.mkdir()
    elif kind == "corrupt":
        path.write_bytes(b"this is not SQLite" * 100)
    elif kind == "missing_table":
        build_service(path, tmp_path).doctor()
        with sqlite3.connect(path) as connection:
            connection.execute("DROP TABLE manifests")
    else:
        with sqlite3.connect(path) as connection:
            if kind == "future":
                connection.execute(f"PRAGMA application_id={APPLICATION_ID}")
                connection.execute("PRAGMA user_version=99")
            else:
                connection.execute("CREATE TABLE unrelated (value TEXT)")
    service = build_service(path, tmp_path)
    result = service.doctor()
    assert not result["ok"]
    assert result["database"]["status"] == "ERROR"
    assert result["database"]["code"].startswith("DATABASE_")
    with pytest.raises(IAAIError):
        service.list_researches()


def test_git_clean_and_dirty(tmp_path):
    from iaai.environment import capture_runtime

    def git(*args):
        return subprocess.run(
            ["git", "-C", str(tmp_path), *args], check=True, capture_output=True, text=True
        ).stdout.strip()

    git("init")
    git(
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "--allow-empty",
        "-m",
        "fixture",
    )
    runtime = capture_runtime(tmp_path)
    assert runtime.git_commit == git("rev-parse", "HEAD")
    assert runtime.git_dirty is False
    (tmp_path / "untracked.txt").write_text("fixture")
    assert capture_runtime(tmp_path).git_dirty is True
