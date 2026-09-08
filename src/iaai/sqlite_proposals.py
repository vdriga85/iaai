"""Append-only proposal history; no model invocation while holding DB locks."""

from iaai.corpus_domain import CorpusSnapshot
from iaai.errors import IAAIError
from iaai.proposal_domain import ProposalCandidate, ProposalRequest, ProposalResult, ReviewDecision


class SQLiteProposalStore:
    def __init__(self, database):
        self.database = database

    def begin(self, request):
        request = ProposalRequest.model_validate_json(request.canonical_json())
        with self.database.connection() as c, c:
            row = c.execute(
                "SELECT content FROM corpus_snapshots WHERE id=?", (request.snapshot_id,)
            ).fetchone()
            snap = CorpusSnapshot.model_validate_json(row[0]) if row else None
            if snap is None or (
                snap.corpus_hash,
                snap.content.research_id,
                snap.content.research_revision,
                snap.content.protocol_hash,
            ) != (
                request.corpus_hash,
                request.research_id,
                request.research_revision,
                request.protocol_hash,
            ):
                raise IAAIError("PROPOSAL_INPUT_MISMATCH", "Не совпадают ссылки операции.")
            c.execute(
                "INSERT INTO proposal_operations VALUES (?,?,?,?,?)",
                (
                    request.operation_id,
                    request.research_id,
                    request.research_revision,
                    request.snapshot_id,
                    request.canonical_json(),
                ),
            )

    def finish(self, result, candidates):
        result = ProposalResult.model_validate_json(result.canonical_json())
        with self.database.connection() as c, c:
            c.execute(
                "INSERT INTO proposal_results VALUES (?,?)",
                (result.operation_id, result.canonical_json()),
            )
            for candidate in candidates:
                candidate = ProposalCandidate.model_validate_json(candidate.canonical_json())
                if (
                    candidate.operation_id != result.operation_id
                    or result.status != "PENDING_REVIEW"
                ):
                    raise IAAIError(
                        "PROPOSAL_INPUT_MISMATCH", "Кандидат не относится к результату."
                    )
                c.execute(
                    "INSERT INTO proposal_candidates VALUES (?,?,?)",
                    (candidate.candidate_id, candidate.operation_id, candidate.canonical_json()),
                )

    def operation(self, operation_id):
        with self.database.connection() as c:
            c.execute("BEGIN")
            row = c.execute(
                "SELECT content FROM proposal_operations WHERE id=?", (operation_id,)
            ).fetchone()
            if not row:
                raise IAAIError("NOT_FOUND", "Операция не найдена.")
            result = c.execute(
                "SELECT content FROM proposal_results WHERE operation_id=?", (operation_id,)
            ).fetchone()
            return {
                "request": ProposalRequest.model_validate_json(row[0]),
                "result": ProposalResult.model_validate_json(result[0]) if result else None,
                "status": "RECORDED_WITHOUT_RESULT"
                if not result
                else ProposalResult.model_validate_json(result[0]).status,
                "candidates": self._entries(c, "p.operation_id=?", operation_id),
            }

    @staticmethod
    def _entries(c, condition, value):
        return [
            {
                "candidate": ProposalCandidate.model_validate_json(row[0]),
                "review": ReviewDecision.model_validate_json(row[1]) if row[1] else None,
            }
            for row in c.execute(
                "SELECT p.content,d.content FROM proposal_candidates p "
                "LEFT JOIN review_decisions d ON d.candidate_id=p.id "
                "JOIN proposal_operations o ON o.id=p.operation_id WHERE "
                + condition
                + " ORDER BY p.rowid",
                (value,),
            )
        ]

    def queue(self, research_id):
        with self.database.connection() as c:
            return self._entries(c, "o.research_id=?", research_id)

    def candidate(self, candidate_id):
        with self.database.connection() as c:
            row = c.execute(
                "SELECT content FROM proposal_candidates WHERE id=?", (candidate_id,)
            ).fetchone()
            if not row:
                raise IAAIError("NOT_FOUND", "Кандидат не найден.")
            return ProposalCandidate.model_validate_json(row[0])

    def terminal_without_candidates(self, research_id):
        with self.database.connection() as c:
            rows = c.execute(
                "SELECT r.content FROM proposal_results r "
                "JOIN proposal_operations o ON o.id=r.operation_id "
                "WHERE o.research_id=? AND NOT EXISTS "
                "(SELECT 1 FROM proposal_candidates p WHERE p.operation_id=o.id) "
                "ORDER BY r.rowid DESC",
                (research_id,),
            )
            return [
                {"operation_id": result.operation_id, "status": result.status}
                for row in rows
                for result in (ProposalResult.model_validate_json(row[0]),)
            ]

    def review(self, decision):
        decision = ReviewDecision.model_validate_json(decision.canonical_json())
        with self.database.connection() as c, c:
            c.execute("BEGIN IMMEDIATE")
            if c.execute(
                "SELECT 1 FROM review_decisions WHERE candidate_id=?", (decision.candidate_id,)
            ).fetchone():
                raise IAAIError(
                    "REVIEW_CONFLICT", "Кандидат уже проверен. Исходное решение сохранено."
                )
            c.execute(
                "INSERT INTO review_decisions VALUES (?,?,?)",
                (decision.decision_id, decision.candidate_id, decision.canonical_json()),
            )

    def last_error(self):
        with self.database.connection() as c:
            for row in c.execute(
                "SELECT content FROM proposal_results ORDER BY rowid DESC LIMIT 1"
            ):
                result = ProposalResult.model_validate_json(row[0])
                return (
                    result.status if result.status not in ("PENDING_REVIEW", "ABSTAINED") else None
                )
            return None
