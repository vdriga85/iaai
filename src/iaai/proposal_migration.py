"""Migration 3: immutable invocation input/result, candidates and human decisions."""

MIGRATION_3 = (
    "CREATE TABLE proposal_operations (id TEXT PRIMARY KEY, research_id TEXT NOT NULL, "
    "revision INTEGER NOT NULL, snapshot_id TEXT NOT NULL REFERENCES corpus_snapshots(id), "
    "content TEXT NOT NULL, FOREIGN KEY(research_id,revision) "
    "REFERENCES revisions(research_id,number))",
    "CREATE TABLE proposal_results (operation_id TEXT PRIMARY KEY "
    "REFERENCES proposal_operations(id), content TEXT NOT NULL)",
    "CREATE TABLE proposal_candidates (id TEXT PRIMARY KEY, operation_id TEXT NOT NULL "
    "REFERENCES proposal_results(operation_id), content TEXT NOT NULL)",
    "CREATE TABLE review_decisions (id TEXT PRIMARY KEY, candidate_id TEXT NOT NULL UNIQUE "
    "REFERENCES proposal_candidates(id), content TEXT NOT NULL)",
    *(
        f"CREATE TRIGGER {table}_no_{action.lower()} BEFORE {action} ON {table} "
        "BEGIN SELECT RAISE(ABORT, 'immutable proposal history'); END"
        for table in (
            "proposal_operations",
            "proposal_results",
            "proposal_candidates",
            "review_decisions",
        )
        for action in ("UPDATE", "DELETE")
    ),
)
