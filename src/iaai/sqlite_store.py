"""SQLite implementation. Append-only snapshots plus an optimistic current pointer."""

import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from pydantic import ValidationError

from iaai.corpus_migration import MIGRATION_2
from iaai.domain import (
    Research,
    ResearchPolicy,
    ResearchProtocol,
    ResearchRevision,
    RevisionBundle,
    RunManifest,
)
from iaai.errors import IAAIError
from iaai.proposal_migration import MIGRATION_3

APPLICATION_ID = 0x49414149
MIGRATIONS = (
    (
        "CREATE TABLE protocols (hash TEXT PRIMARY KEY, content TEXT NOT NULL)",
        "CREATE TABLE policies (hash TEXT PRIMARY KEY, content TEXT NOT NULL)",
        "CREATE TABLE researches (id TEXT PRIMARY KEY, current_revision INTEGER NOT NULL, "
        "content TEXT NOT NULL)",
        "CREATE TABLE revisions (research_id TEXT NOT NULL REFERENCES researches(id), "
        "number INTEGER NOT NULL CHECK(number > 0), "
        "protocol_hash TEXT NOT NULL REFERENCES protocols(hash), "
        "policy_hash TEXT NOT NULL REFERENCES policies(hash), run_id TEXT NOT NULL UNIQUE, "
        "content TEXT NOT NULL, PRIMARY KEY(research_id, number))",
        "CREATE TABLE manifests (run_id TEXT PRIMARY KEY REFERENCES revisions(run_id), "
        "hash TEXT NOT NULL, content TEXT NOT NULL)",
        *(
            f"CREATE TRIGGER {table}_no_{action.lower()} BEFORE {action} ON {table} "
            "BEGIN SELECT RAISE(ABORT, 'immutable snapshot'); END"
            for table in ("protocols", "policies", "revisions", "manifests")
            for action in ("UPDATE", "DELETE")
        ),
    ),
    MIGRATION_2,
    MIGRATION_3,
)


class SQLiteResearchStore:
    def __init__(self, path: Path, busy_timeout_seconds: int):
        self.path = path.resolve()
        self.busy_timeout_seconds = busy_timeout_seconds

    @contextmanager
    def connection(self, busy_timeout_seconds: int | None = None):
        connection = None
        timeout = busy_timeout_seconds or self.busy_timeout_seconds
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.is_dir():
                raise IAAIError("DATABASE_PATH", "Database path points to a directory")
            connection = sqlite3.connect(self.path, timeout=timeout)
            connection.row_factory = sqlite3.Row
            connection.execute(f"PRAGMA busy_timeout={timeout * 1000}")
            # Check identity BEFORE altering journal mode or performing migrations.
            # These reads must share a snapshot if another process is initializing the DB.
            connection.execute("BEGIN")
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            identity = connection.execute("PRAGMA application_id").fetchone()[0]
            tables = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            if not (
                (version == 0 and identity == 0 and not tables)
                or (identity == APPLICATION_ID and 1 <= version <= len(MIGRATIONS))
            ):
                raise IAAIError("DATABASE_SCHEMA", "Unknown database identity or schema version")
            connection.commit()
            if self._enable_wal(connection, timeout) != "wal":
                raise IAAIError("DATABASE_SETTINGS", "SQLite WAL mode could not be enabled")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("BEGIN IMMEDIATE")
            # Recheck after acquiring lock: another process may have initialized it.
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version:
                self._check_schema(connection, version)
            for index in range(version, len(MIGRATIONS)):
                for statement in MIGRATIONS[index]:
                    connection.execute(statement)
                connection.execute(f"PRAGMA user_version={index + 1}")
            connection.execute(f"PRAGMA application_id={APPLICATION_ID}")
            connection.commit()
            self._check_schema(connection)
            yield connection
        except IAAIError:
            raise
        except OSError as exc:
            raise IAAIError("DATABASE_PATH", f"Cannot access database: {exc.strerror}") from exc
        except sqlite3.IntegrityError as exc:
            raise IAAIError("DATABASE_CONFLICT", "Snapshot conflict; no changes committed") from exc
        except sqlite3.OperationalError as exc:
            code = "DATABASE_BUSY" if "locked" in str(exc) else "DATABASE_ERROR"
            raise IAAIError(code, str(exc)) from exc
        except (sqlite3.DatabaseError, ValidationError, ValueError, KeyError) as exc:
            raise IAAIError("DATABASE_CORRUPT", "Invalid database or stored snapshot") from exc
        finally:
            if connection is not None:
                connection.close()  # Rolls back any unfinished transaction.

    @staticmethod
    def _enable_wal(connection, timeout):
        # journal_mode transitions can return SQLITE_BUSY without using busy_timeout.
        # Retry only this idempotent setup operation, bounded by the same policy budget.
        deadline = time.monotonic() + timeout
        while True:
            try:
                return connection.execute("PRAGMA journal_mode=WAL").fetchone()[0]
            except sqlite3.OperationalError as exc:
                remaining = deadline - time.monotonic()
                if getattr(exc, "sqlite_errorcode", None) != sqlite3.SQLITE_BUSY or remaining <= 0:
                    raise
                time.sleep(min(0.01, remaining))  # OS polling cadence, not research calibration.

    @staticmethod
    def _check_schema(connection, version=None):
        # Validate the old structure before upgrade, and current structure afterward.
        expected = sqlite3.connect(":memory:")
        try:
            for migration in MIGRATIONS[:version]:
                for statement in migration:
                    expected.execute(statement)
            query = (
                "SELECT type, name, sql FROM sqlite_master "
                "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
            )
            actual = [tuple(row) for row in connection.execute(query)]
            if actual != expected.execute(query).fetchall():
                raise IAAIError("DATABASE_SCHEMA", "Database structure does not match schema")
        finally:
            expected.close()

    def save(self, bundle: RevisionBundle, expected_revision: int) -> None:
        # Revalidate even if a caller used Pydantic's unsafe model_copy/model_construct APIs.
        bundle = RevisionBundle.model_validate_json(bundle.canonical_json())
        research, revision = bundle.research, bundle.revision
        if (
            research.current_revision != expected_revision + 1
            or revision.revision != expected_revision + 1
        ):
            raise IAAIError("REVISION_CONFLICT", "Revision sequence is not contiguous")
        with (
            self.connection(bundle.policy.runtime.sqlite_busy_timeout_seconds) as connection,
            connection,
        ):
            connection.execute("BEGIN IMMEDIATE")
            if expected_revision == 0:
                connection.execute(
                    "INSERT INTO researches VALUES (?, ?, ?)",
                    (research.research_id, 1, research.canonical_json()),
                )
            else:
                updated = connection.execute(
                    "UPDATE researches SET current_revision=?, content=? "
                    "WHERE id=? AND current_revision=?",
                    (
                        research.current_revision,
                        research.canonical_json(),
                        research.research_id,
                        expected_revision,
                    ),
                )
                if updated.rowcount != 1:
                    raise IAAIError("REVISION_CONFLICT", "Research changed; reload before revising")
            for table, snapshot in (("protocols", bundle.protocol), ("policies", bundle.policy)):
                connection.execute(
                    f"INSERT INTO {table} VALUES (?, ?) ON CONFLICT(hash) DO NOTHING",
                    (snapshot.content_hash, snapshot.canonical_json()),
                )
            connection.execute(
                "INSERT INTO revisions VALUES (?, ?, ?, ?, ?, ?)",
                (
                    research.research_id,
                    revision.revision,
                    revision.protocol_hash,
                    revision.policy_hash,
                    revision.run_id,
                    revision.canonical_json(),
                ),
            )
            connection.execute(
                "INSERT INTO manifests VALUES (?, ?, ?)",
                (
                    bundle.manifest.run_id,
                    bundle.manifest.content_hash,
                    bundle.manifest.canonical_json(),
                ),
            )

    def list_researches(self) -> tuple[Research, ...]:
        with self.connection() as connection:
            return tuple(
                Research.model_validate_json(row[0])
                for row in connection.execute("SELECT content FROM researches ORDER BY rowid DESC")
            )

    def load(self, research_id: str, revision: int | None = None) -> RevisionBundle:
        with self.connection() as connection:
            connection.execute("BEGIN")  # Consistent read snapshot across all SELECTs.
            row = connection.execute(
                "SELECT content FROM researches WHERE id=?", (research_id,)
            ).fetchone()
            if row is None:
                raise IAAIError("NOT_FOUND", "Research not found")
            research = Research.model_validate_json(row[0])
            row = connection.execute(
                "SELECT r.content, p.content, y.content, m.content, m.hash FROM revisions r "
                "JOIN protocols p ON p.hash=r.protocol_hash "
                "JOIN policies y ON y.hash=r.policy_hash "
                "JOIN manifests m ON m.run_id=r.run_id WHERE r.research_id=? AND r.number=?",
                (research_id, revision if revision is not None else research.current_revision),
            ).fetchone()
            if row is None:
                raise IAAIError("NOT_FOUND", "Revision not found")
            manifest = RunManifest.model_validate_json(row[3])
            if manifest.content_hash != row[4]:
                raise IAAIError("DATABASE_CORRUPT", "Manifest hash mismatch")
            return RevisionBundle(
                research=research,
                revision=ResearchRevision.model_validate_json(row[0]),
                protocol=ResearchProtocol.model_validate_json(row[1]),
                policy=ResearchPolicy.model_validate_json(row[2]),
                manifest=manifest,
            )

    def manifest(self, run_id: str) -> RunManifest:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT content, hash FROM manifests WHERE run_id=?", (run_id,)
            ).fetchone()
            if row is None:
                raise IAAIError("NOT_FOUND", "Manifest not found")
            manifest = RunManifest.model_validate_json(row[0])
            if manifest.content_hash != row[1] or manifest.run_id != run_id:
                raise IAAIError("DATABASE_CORRUPT", "Manifest hash or ID mismatch")
            return manifest

    def diagnostics(self) -> dict:
        with self.connection() as connection:
            integrity = connection.execute("PRAGMA quick_check").fetchone()[0]
            if integrity != "ok" or connection.execute("PRAGMA foreign_key_check").fetchone():
                raise IAAIError("DATABASE_CORRUPT", "SQLite integrity check failed")
            result = {
                name: connection.execute(f"PRAGMA {name}").fetchone()[0]
                for name in (
                    "journal_mode",
                    "synchronous",
                    "foreign_keys",
                    "busy_timeout",
                    "user_version",
                    "application_id",
                )
            }
            if (result["journal_mode"], result["synchronous"], result["foreign_keys"]) != (
                "wal",
                2,
                1,
            ):
                raise IAAIError("DATABASE_SETTINGS", "Required SQLite settings are not active")
            return {"status": "OK", "path": str(self.path), "integrity": integrity, **result}
