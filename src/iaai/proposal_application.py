"""Frozen-corpus proposal -> deterministic validation -> human review. No runtime imports."""

import json
from datetime import UTC, datetime
from uuid import uuid4

from pydantic import ValidationError

from iaai.corpus_application import validated_operation
from iaai.corpus_domain import TextChunk, digest
from iaai.errors import IAAIError
from iaai.proposal_context import PROMPT_VERSION, SYSTEM_CONTRACT, assemble
from iaai.proposal_domain import (
    ContextChunk,
    ModelResponse,
    ProposalCandidate,
    ProposalOutput,
    ProposalRequest,
    ProposalResult,
    ReviewDecision,
)
from iaai.proposal_ports import ProposalModel, ProposalStore


def parse_output(raw, request):
    # One explicit completion wire protocol: JSON plus optional runtime EOS marker.
    # Keep original stdout unchanged in provenance. No fences/repair/second model call.
    payload = raw.strip()
    if payload.endswith("[end of text]"):
        payload = payload[: -len("[end of text]")].rstrip()

    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON object key")
            result[key] = value
        return result

    json.loads(payload, object_pairs_hook=unique_keys)
    parsed = ProposalOutput.model_validate_json(payload)
    candidates = (*parsed.claims, *parsed.questions)
    if len(candidates) > request.policy.max_candidates:
        raise ValueError("candidate count exceeds policy")
    allowed = {item.chunk.chunk_id for item in request.context}
    seen = set()
    for candidate in candidates:
        if not set(candidate.chunk_ids) <= allowed:
            raise ValueError("reference outside supplied context")
        if len(candidate.chunk_ids) != len(set(candidate.chunk_ids)):
            raise ValueError("duplicate chunk references")
        key = " ".join(candidate.text.split()).casefold()
        if key in seen:
            raise ValueError("duplicate candidate text; entire batch rejected")
        seen.add(key)
    return parsed


def changed_characters(before, after):
    """Deterministic differing middle length sum after shared prefix/suffix removal, not quality."""
    left = 0
    while left < min(len(before), len(after)) and before[left] == after[left]:
        left += 1
    right = 0
    while right < min(len(before), len(after)) - left and before[-1 - right] == after[-1 - right]:
        right += 1
    return len(before) + len(after) - 2 * (left + right)


class ProposalService:
    def __init__(self, researches, corpus, store: ProposalStore, model: ProposalModel, policy):
        self.researches, self.corpus, self.store = researches, corpus, store
        self.model, self.policy = model, policy

    @validated_operation
    def run(self, snapshot_id, question):
        snapshot = self.corpus.snapshot(snapshot_id)
        bundle = self.researches.load(
            snapshot.content.research_id, snapshot.content.research_revision
        )
        if bundle.protocol.content_hash != snapshot.content.protocol_hash:
            raise IAAIError("PROPOSAL_INPUT_MISMATCH", "Протокол не совпадает со снимком корпуса.")
        if not question.strip() or len(question) > 2000:
            raise IAAIError("VALIDATION_ERROR", "Введите вопрос длиной от 1 до 2000 символов.")
        started = datetime.now(UTC)
        retrieved, index, failure = (), "", ""
        try:
            retrieval = self.corpus.search(snapshot_id, question)
            index = retrieval["index_version"]
            retrieved = tuple(
                ContextChunk(
                    rank=r["rank"],
                    score=r["score"],
                    source_id=r["source_id"],
                    chunk=TextChunk.model_validate_json(json.dumps(r["chunk"])),
                )
                for r in retrieval["results"]
            )
        except IAAIError as exc:
            failure = exc.code
        context, omitted, prompt, schema = assemble(
            bundle.protocol, question, retrieved, self.policy
        )
        request = ProposalRequest(
            operation_id=str(uuid4()),
            research_id=snapshot.content.research_id,
            research_revision=snapshot.content.research_revision,
            protocol=bundle.protocol,
            protocol_hash=bundle.protocol.content_hash,
            snapshot_id=snapshot_id,
            corpus_hash=snapshot.corpus_hash,
            question=question,
            retrieval_query=question,
            retrieval_index_version=index,
            retrieved=retrieved,
            context=context,
            omitted_chunk_ids=omitted,
            model=self.model.identity(),
            policy=self.policy,
            policy_hash=self.policy.content_hash,
            prompt=prompt,
            prompt_version=PROMPT_VERSION,
            prompt_hash=digest(prompt),
            output_schema=schema,
            template_content=SYSTEM_CONTRACT + "\n" + schema,
            template_hash=digest(SYSTEM_CONTRACT + "\n" + schema),
            started_at=started,
        )
        self.store.begin(request)  # Durable before invocation. Missing result means INTERRUPTED.
        try:
            response = ModelResponse(status=failure) if failure else self.model.generate(request)
        except Exception:
            # Unexpected runtime failure still gets a bounded terminal record; no second model.
            response = ModelResponse(status="MODEL_RUNTIME_ERROR")
        parsed, candidates, error = None, [], ""
        status = response.status
        if status == "OK":
            try:
                if (
                    response.stdout_truncated
                    or len(response.stdout.encode("utf-8")) > self.policy.stdout_bytes
                ):
                    raise ValueError("output limit")
                parsed = parse_output(response.stdout, request)
                status = "ABSTAINED" if parsed.abstention else "PENDING_REVIEW"
                for kind, items in (("CLAIM", parsed.claims), ("QUESTION", parsed.questions)):
                    for item in items:
                        candidates.append(
                            ProposalCandidate(
                                candidate_id=str(uuid4()),
                                operation_id=request.operation_id,
                                kind=kind,
                                text=item.text,
                                reason=getattr(item, "reason", ""),
                                question=question,
                                chunk_ids=item.chunk_ids,
                                created_at=datetime.now(UTC),
                            )
                        )
            except (ValueError, ValidationError):
                status, error = (
                    "MODEL_OUTPUT_INVALID",
                    "JSON/schema/count/reference validation failed",
                )
        result = ProposalResult(
            operation_id=request.operation_id,
            completed_at=datetime.now(UTC),
            status=status,
            response=response,
            parsed=parsed,
            error=error,
        )
        self.store.finish(result, tuple(candidates))
        return self.store.operation(request.operation_id)

    def show(self, operation_id):
        return self.store.operation(operation_id)

    def queue(self, research_id):
        self.researches.load(research_id)
        entries = self.store.queue(research_id)
        counts = {
            status: 0 for status in ("PENDING_REVIEW", "ACCEPTED", "REJECTED", "EDITED_ACCEPTED")
        }
        for entry in entries:
            counts[entry["review"].action if entry["review"] else "PENDING_REVIEW"] += 1
        return {
            "entries": entries,
            "measurements": {
                "generated": len(entries),
                **counts,
                "changed_characters": sum(
                    e["review"].changed_characters for e in entries if e["review"]
                ),
            },
        }

    @validated_operation
    def review(
        self, candidate_id, action, reviewer, edited_text=None, reason_code=None, comment=""
    ):
        candidate = self.store.candidate(candidate_id)
        decision = ReviewDecision(
            decision_id=str(uuid4()),
            candidate_id=candidate_id,
            action=action,
            reviewer=reviewer,
            reviewed_at=datetime.now(UTC),
            edited_text=edited_text,
            reason_code=reason_code,
            comment=comment,
            changed_characters=changed_characters(candidate.text, edited_text)
            if edited_text is not None
            else 0,
        )
        self.store.review(decision)
        return decision

    def diagnostics(self):
        return {
            **self.model.identity().model_dump(mode="json"),
            "last_error": self.store.last_error(),
            "policy": self.policy.model_dump(mode="json"),
            "policy_hash": self.policy.content_hash,
            "gpu_required": False,
            "os_sandbox": False,
        }
