"""Append-only migration 2; never rewrites Step 1 snapshots."""

MIGRATION_2 = (
    "CREATE TABLE sources (id TEXT PRIMARY KEY, content TEXT NOT NULL)",
    "CREATE TABLE observations (id TEXT PRIMARY KEY, "
    "research_id TEXT NOT NULL REFERENCES researches(id), "
    "source_id TEXT NOT NULL REFERENCES sources(id), content TEXT NOT NULL)",
    "CREATE TABLE artifacts (id TEXT PRIMARY KEY, "
    "observation_id TEXT NOT NULL UNIQUE REFERENCES observations(id), "
    "content TEXT NOT NULL)",
    "CREATE TABLE chunks (id TEXT PRIMARY KEY, "
    "artifact_id TEXT NOT NULL REFERENCES artifacts(id), content TEXT NOT NULL)",
    "CREATE TABLE corpus_members (research_id TEXT NOT NULL REFERENCES researches(id), "
    "artifact_id TEXT NOT NULL REFERENCES artifacts(id), PRIMARY KEY(research_id,artifact_id))",
    "CREATE TABLE corpus_snapshots (id TEXT PRIMARY KEY, "
    "research_id TEXT NOT NULL REFERENCES researches(id), "
    "version INTEGER NOT NULL, content TEXT NOT NULL, UNIQUE(research_id,version))",
    "CREATE TABLE raw_cache (observation_id TEXT PRIMARY KEY, "
    "body BLOB NOT NULL, created REAL NOT NULL)",
    "CREATE TABLE cache_events (observation_id TEXT PRIMARY KEY REFERENCES observations(id), "
    "removed_at REAL NOT NULL, removed_bytes INTEGER NOT NULL)",
    *(
        f"CREATE TRIGGER {table}_no_{action.lower()} BEFORE {action} ON {table} "
        "BEGIN SELECT RAISE(ABORT, 'immutable snapshot'); END"
        for table in (
            "sources",
            "observations",
            "artifacts",
            "chunks",
            "corpus_snapshots",
            "cache_events",
        )
        for action in ("UPDATE", "DELETE")
    ),
)
