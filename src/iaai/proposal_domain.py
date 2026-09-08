"""Candidate and human-review records, never assertions or evidence."""

from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from iaai.corpus_domain import TextChunk, digest
from iaai.domain import Hash, Identifier, ResearchProtocol, Snapshot, Text

ShortText = Annotated[str, Field(min_length=1, max_length=2000, pattern=r"\S")]


class ProposalPolicy(Snapshot):
    schema_version: Literal["0.3"] = "0.3"
    status: Literal["UNVALIDATED"] = "UNVALIDATED"
    version: Literal[1] = 1
    retrieval_top_k: Annotated[int, Field(ge=1, le=20)] = 3
    max_context_chars: Annotated[int, Field(ge=100, le=20000)] = 4000
    max_prompt_bytes: Annotated[int, Field(ge=2000, le=60000)] = 12000
    context_window: Annotated[int, Field(ge=2048, le=32768)] = 16384
    max_output_tokens: Annotated[int, Field(ge=64, le=4096)] = 768
    timeout_seconds: Annotated[int, Field(ge=1, le=1800)] = 300
    stdout_bytes: Annotated[int, Field(ge=1024, le=262144)] = 32768
    stderr_bytes: Annotated[int, Field(ge=1024, le=65536)] = 16384
    temperature: Annotated[float, Field(ge=0, le=2)] = 0.0
    seed: Annotated[int, Field(ge=0, le=2147483647)] = 42
    threads: Annotated[int, Field(ge=1, le=64)] = 6
    gpu_layers: Literal[0] = 0
    max_candidates: Annotated[int, Field(ge=1, le=12)] = 6

    @model_validator(mode="after")
    def token_bound(self) -> Self:
        # Conservative byte upper bound for the selected byte-fallback tokenizer.
        if self.max_prompt_bytes + self.max_output_tokens + 128 > self.context_window:
            raise ValueError("prompt byte bound + output + special-token reserve exceeds context")
        return self


class ModelIdentity(Snapshot):
    status: Text
    name: str = ""
    executable: str = ""
    runtime_version: str = ""
    executable_hash: Hash | None = None
    model_path: str = ""
    basename: str = ""
    model_hash: Hash | None = None
    model_size: int = 0
    model_file_exists: bool = False
    executable_exists: bool = False
    host_architecture: str = "UNKNOWN"
    logical_cpus: int | None = None
    quantization: str = "UNKNOWN"
    adapter_version: Literal["llama-completion-chatml-v1"] = "llama-completion-chatml-v1"


class ContextChunk(Snapshot):
    rank: int
    score: float
    source_id: Identifier
    chunk: TextChunk


class ClaimOutput(Snapshot):
    text: ShortText
    chunk_ids: Annotated[tuple[Identifier, ...], Field(min_length=1, max_length=20)]


class QuestionOutput(ClaimOutput):
    reason: ShortText


class ProposalOutput(Snapshot):
    claims: Annotated[tuple[ClaimOutput, ...], Field(max_length=12)]
    questions: Annotated[tuple[QuestionOutput, ...], Field(max_length=12)]
    abstention: str

    @model_validator(mode="after")
    def nonempty_or_abstain(self) -> Self:
        if len(self.abstention) > 2000:
            raise ValueError("abstention too long")
        if not self.claims and not self.questions and not self.abstention.strip():
            raise ValueError("empty batch requires explicit abstention")
        if (self.claims or self.questions) and self.abstention:
            raise ValueError("abstention and candidates are mutually exclusive")
        return self


class ProposalRequest(Snapshot):
    operation_id: Identifier
    research_id: Identifier
    research_revision: int
    protocol: ResearchProtocol
    protocol_hash: Hash
    snapshot_id: Identifier
    corpus_hash: Hash
    question: ShortText
    retrieval_query: ShortText
    retrieval_index_version: str
    retrieved: tuple[ContextChunk, ...]
    context: tuple[ContextChunk, ...]
    omitted_chunk_ids: tuple[Identifier, ...]
    model: ModelIdentity
    policy: ProposalPolicy
    policy_hash: Hash
    prompt_version: Literal["proposal-chatml-v1", "proposal-chatml-v2"] = "proposal-chatml-v1"
    proposal_schema_version: Literal["0.3"] = "0.3"
    prompt: str
    prompt_hash: Hash
    output_schema: str
    template_content: str = ""
    template_hash: Hash | None = None
    started_at: datetime

    @model_validator(mode="after")
    def integrity(self) -> Self:
        if (
            self.protocol_hash != self.protocol.content_hash
            or self.policy_hash != self.policy.content_hash
        ):
            raise ValueError("proposal input hash mismatch")
        if digest(self.prompt) != self.prompt_hash:
            raise ValueError("prompt hash mismatch")
        if self.template_hash is not None and digest(self.template_content) != self.template_hash:
            raise ValueError("template hash mismatch")
        if len(self.prompt.encode("utf-8")) > self.policy.max_prompt_bytes:
            raise ValueError("prompt budget exceeded")
        if sum(len(c.chunk.text) for c in self.context) > self.policy.max_context_chars:
            raise ValueError("context budget exceeded")
        if len(self.context) > self.policy.retrieval_top_k:
            raise ValueError("top-k exceeded")
        if any(c not in self.retrieved for c in self.context):
            raise ValueError("context must be an exact retrieved subset")
        return self


class ModelResponse(Snapshot):
    status: str
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    duration_seconds: float = 0.0
    stdout_hash: Hash = digest("")
    stdout_truncated: bool = False
    stderr_truncated: bool = False


class ProposalResult(Snapshot):
    operation_id: Identifier
    completed_at: datetime
    status: str
    response: ModelResponse
    parsed: ProposalOutput | None
    error: str = ""


class ProposalCandidate(Snapshot):
    candidate_id: Identifier
    operation_id: Identifier
    kind: Literal["CLAIM", "QUESTION"]
    text: ShortText
    reason: str
    question: ShortText
    chunk_ids: tuple[Identifier, ...]
    status: Literal["CANDIDATE"] = "CANDIDATE"
    created_at: datetime


class ReviewDecision(Snapshot):
    decision_id: Identifier
    candidate_id: Identifier
    action: Literal["ACCEPTED", "REJECTED", "EDITED_ACCEPTED"]
    reviewer: ShortText
    reviewed_at: datetime
    provenance: Literal["HUMAN_REVIEWED"] = "HUMAN_REVIEWED"
    edited_text: ShortText | None = None
    reason_code: (
        Literal[
            "NOT_GROUNDED",
            "DUPLICATE",
            "IRRELEVANT",
            "TOO_VAGUE",
            "WRONG_SCOPE",
            "BAD_FORMULATION",
            "OTHER",
        ]
        | None
    ) = None
    comment: Annotated[str, Field(max_length=2000)] = ""
    changed_characters: Annotated[int, Field(ge=0)] = 0

    @model_validator(mode="after")
    def editing(self) -> Self:
        if (self.action == "EDITED_ACCEPTED") != (self.edited_text is not None):
            raise ValueError("edited text is required only for EDITED_ACCEPTED")
        return self
