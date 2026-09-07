"""Immutable Step 1 snapshots; no HTTP, persistence or research execution."""

import hashlib
import json
import math
from datetime import date, datetime
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

Text = Annotated[str, Field(min_length=1, max_length=20000, pattern=r"\S")]
Identifier = Annotated[str, Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_.-]+$")]
Positive = Annotated[int, Field(gt=0)]
Fraction = Annotated[float, Field(ge=0, le=1)]
Hash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Unit = Literal[
    "EUR",
    "USD",
    "AUD",
    "GBP",
    "bytes",
    "seconds",
    "hours",
    "days",
    "kg",
    "g",
    "mm",
    "cm",
    "m",
    "W",
    "Wh",
    "percent",
    "count",
    "ratio",
    "text",
]


class Snapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, allow_inf_nan=False)

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


class KeyOutputDefinition(Snapshot):
    name: Identifier
    description: Text
    value_type: Literal["number", "text"]
    unit: Unit

    @model_validator(mode="after")
    def compatible_unit(self) -> Self:
        if (self.value_type == "text") != (self.unit == "text"):
            raise ValueError(
                "text outputs require text units; numeric outputs require numeric units"
            )
        return self


class ConstraintDefinition(Snapshot):
    output: Identifier
    type: Literal["USER", "REGULATORY", "PHYSICAL", "TECHNICAL", "METHODOLOGICAL_EVALUATION"]
    operator: Literal["eq", "lt", "le", "gt", "ge"]
    value: int | float | Text
    unit: Unit
    origin: Text


class ResearchProtocol(Snapshot):
    schema_version: Literal["0.1"]
    protocol_id: Identifier
    version: Positive
    original_idea: Text
    neutral_description: Text
    product_scope: Text
    geography: Text
    target_population: Text
    time_horizon: Text | None
    source_cutoff: date | None
    languages: Annotated[tuple[Text, ...], Field(min_length=1)]
    key_outputs: Annotated[tuple[KeyOutputDefinition, ...], Field(min_length=1)]
    assumptions: tuple[Text, ...]
    constraints: tuple[ConstraintDefinition, ...]
    playbook_reference: Text | None
    playbook_version: Text | None

    @model_validator(mode="after")
    def consistent_scope(self) -> Self:
        outputs = {item.name: item for item in self.key_outputs}
        if len(outputs) != len(self.key_outputs) or len(set(self.languages)) != len(self.languages):
            raise ValueError("output names and languages must be unique")
        if (self.playbook_reference is None) != (self.playbook_version is None):
            raise ValueError("playbook reference and version must be supplied together")
        for constraint in self.constraints:
            output = outputs.get(constraint.output)
            if output is None or output.unit != constraint.unit:
                raise ValueError("constraint must reference an output with matching unit")
            if (output.value_type == "text") != isinstance(constraint.value, str):
                raise ValueError("constraint value must match output type")
            if output.value_type == "text" and constraint.operator != "eq":
                raise ValueError("text constraints support eq only")
        return self


class SchedulerPolicy(Snapshot):
    schema_version: Literal["0.1"]
    mode: Literal["SIMPLE"]
    frontier_capacity: Positive
    children_per_proposal: Positive
    lane_shares: tuple[Fraction, Fraction, Fraction]
    exploration_seed: Annotated[int, Field(ge=0, lt=2**32)]

    @model_validator(mode="after")
    def shares(self) -> Self:
        if not math.isclose(sum(self.lane_shares), 1, abs_tol=1e-12, rel_tol=0):
            raise ValueError("lane shares must sum to one")
        if min(self.lane_shares[1:]) <= 0:
            raise ValueError("FIFO and exploration require positive shares")
        if self.children_per_proposal > self.frontier_capacity:
            raise ValueError("children exceed frontier capacity")
        return self


class StopPolicy(Snapshot):
    schema_version: Literal["0.1"]
    informative_window_batches: Positive
    min_independent_exposure_origins: Positive
    novelty_ceiling: Fraction
    output_rel_tolerance: Annotated[float, Field(gt=0, le=1)] | None
    freshness_interval_seconds: Positive | None


class ResourcePolicy(Snapshot):
    schema_version: Literal["0.1"]
    run_disk_bytes: Positive
    pool_disk_bytes: Positive
    host_free_reserve_bytes: Positive
    cpu_seconds: Positive
    active_elapsed_seconds: Positive
    wall_deadline_seconds: Positive
    rss_bytes: Positive

    @model_validator(mode="after")
    def ceilings(self) -> Self:
        if self.run_disk_bytes > self.pool_disk_bytes:
            raise ValueError("run disk budget exceeds pool disk budget")
        if self.cpu_seconds > self.active_elapsed_seconds:
            raise ValueError("CPU budget exceeds single-worker active budget")
        if self.active_elapsed_seconds > self.wall_deadline_seconds:
            raise ValueError("active budget exceeds wall deadline")
        return self


class RuntimePolicy(Snapshot):
    schema_version: Literal["0.1"]
    sqlite_busy_timeout_seconds: Annotated[int, Field(gt=0, le=60)]


class EvaluationPolicy(Snapshot):
    schema_version: Literal["0.1"]
    corpus_target_documents: Positive
    initial_questions_target: Positive
    repeat_seeds: Annotated[tuple[Annotated[int, Field(ge=0, lt=2**32)], ...], Field(min_length=1)]
    checkpoint_fractions: Annotated[
        tuple[Annotated[float, Field(gt=0, le=1)], ...], Field(min_length=1)
    ]

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if len(set(self.repeat_seeds)) != len(self.repeat_seeds):
            raise ValueError("repeat seeds must be distinct")
        if tuple(sorted(set(self.checkpoint_fractions))) != self.checkpoint_fractions:
            raise ValueError("checkpoints must be strictly increasing")
        if self.checkpoint_fractions[-1] != 1:
            raise ValueError("checkpoints must include the full budget")
        return self


class ResearchPolicy(Snapshot):
    schema_version: Literal["0.1"]
    policy_id: Identifier
    version: Positive
    status: Literal["UNVALIDATED", "PILOT_CALIBRATED", "EVALUATED"]
    parent_policy_hash: Hash | None
    calibration_dataset_reference: Text | None
    scheduler: SchedulerPolicy
    stop: StopPolicy
    resources: ResourcePolicy
    runtime: RuntimePolicy
    evaluation: EvaluationPolicy

    @model_validator(mode="after")
    def calibration_provenance(self) -> Self:
        if self.status != "UNVALIDATED" and self.calibration_dataset_reference is None:
            raise ValueError("calibrated/evaluated policy requires a dataset reference")
        return self


class Research(Snapshot):
    research_id: Identifier
    original_idea: Text
    status: Literal["CREATED"]
    current_revision: Positive
    created_at: datetime


class ResearchRevision(Snapshot):
    research_id: Identifier
    revision: Positive
    protocol_hash: Hash
    policy_hash: Hash
    run_id: Identifier
    created_at: datetime


class DependencyVersion(Snapshot):
    name: Text
    version: Text


class RuntimeMetadata(Snapshot):
    git_commit: Text | None
    git_dirty: bool | None
    git_status: Literal["AVAILABLE", "UNAVAILABLE"]
    python_version: Text
    python_implementation: Text
    dependencies: tuple[DependencyVersion, ...]
    os: Text
    machine: Text
    processor: Text | None
    logical_cpu_count: Positive | None
    physical_memory_bytes: Positive | None


class RunManifest(Snapshot):
    schema_version: Literal["0.1"]
    run_id: Identifier
    research_id: Identifier
    revision: Positive
    protocol_hash: Hash
    policy_hash: Hash
    runtime: RuntimeMetadata
    created_at: datetime


class RevisionBundle(Snapshot):
    research: Research
    revision: ResearchRevision
    protocol: ResearchProtocol
    policy: ResearchPolicy
    manifest: RunManifest

    @model_validator(mode="after")
    def references(self) -> Self:
        revision, manifest = self.revision, self.manifest
        if not (
            self.research.research_id == revision.research_id == manifest.research_id
            and revision.revision == manifest.revision
            and revision.run_id == manifest.run_id
            and revision.protocol_hash == manifest.protocol_hash == self.protocol.content_hash
            and revision.policy_hash == manifest.policy_hash == self.policy.content_hash
            and revision.created_at == manifest.created_at
        ):
            raise ValueError("inconsistent revision references or content hashes")
        return self
