"""Additive provenance only; existing schemas and rows are untouched."""

MIGRATION_4 = (
    "CREATE TABLE input_builds (research_id TEXT NOT NULL, revision INTEGER NOT NULL, "
    "hash TEXT NOT NULL, content TEXT NOT NULL, PRIMARY KEY(research_id,revision), "
    "FOREIGN KEY(research_id,revision) REFERENCES revisions(research_id,number))",
    *(
        f"CREATE TRIGGER input_builds_no_{action.lower()} BEFORE {action} ON input_builds "
        "BEGIN SELECT RAISE(ABORT, 'immutable input build'); END"
        for action in ("UPDATE", "DELETE")
    ),
)
