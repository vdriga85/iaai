"""Versioned external input and deterministic, non-semantic Protocol builder."""

import json
from datetime import date
from typing import Literal, Self

from pydantic import field_validator, model_validator

from iaai.domain import Hash, ResearchProtocol, Snapshot, Text


class OptionalClarifications(Snapshot):
    neutral_description: Text | None = None
    product_scope: Text | None = None
    geography: Text | None = None
    target_population: Text | None = None
    budget: Text | None = None
    user_constraints: tuple[Text, ...] = ()
    time_horizon: Text | None = None
    source_cutoff: date | None = None
    languages: tuple[Text, ...] = ()
    additional_questions: tuple[Text, ...] = ()
    assumptions: tuple[Text, ...] = ()

    @field_validator("*", mode="before")
    @classmethod
    def blank_optional(cls, value, info):
        lists = {"languages", "additional_questions", "assumptions", "user_constraints"}
        if value is None or (isinstance(value, str) and not value.strip()):
            return () if info.field_name in lists else None
        if info.field_name in lists and isinstance(value, list):
            return tuple(value)
        if info.field_name == "source_cutoff" and isinstance(value, str):
            return date.fromisoformat(value)
        return value


class SimpleIdeaInput(Snapshot):
    schema_version: Literal["0.1"] = "0.1"
    idea: Text
    clarifications: OptionalClarifications = OptionalClarifications()


class FieldOrigin(Snapshot):
    field: str
    origin: Literal["USER_SUPPLIED", "NOT_SUPPLIED", "SYSTEM_GENERATED"]
    note: str = ""


class FieldMapping(Snapshot):
    field: str
    status: Literal["MAPPED", "NOT_SUPPLIED", "DEFERRED_NOT_MAPPED"]


def mapping_for(value):
    return tuple(
        FieldMapping(
            field=name,
            status=(
                "NOT_SUPPLIED"
                if not item
                else "DEFERRED_NOT_MAPPED"
                if name in ("budget", "user_constraints")
                else "MAPPED"
            ),
        )
        for name, item in value.clarifications.model_dump(mode="json").items()
    )


class ProtocolBuild(Snapshot):
    schema_version: Literal["0.1"] = "0.1"
    builder_version: Literal["simple-explicit-v1", "simple-explicit-v2"] = "simple-explicit-v2"
    input: SimpleIdeaInput
    input_hash: Hash
    protocol: ResearchProtocol
    protocol_hash: Hash
    origins: tuple[FieldOrigin, ...]
    mapping: tuple[FieldMapping, ...] = ()
    neutralization: Literal["NOT_PERFORMED"] = "NOT_PERFORMED"

    def canonical_json(self) -> str:
        # Legacy audit artifacts predate mapping; never change their canonical bytes.
        if self.builder_version == "simple-explicit-v1":
            return json.dumps(
                self.model_dump(mode="json", exclude={"mapping"}),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
        return super().canonical_json()

    @model_validator(mode="after")
    def integrity(self) -> Self:
        protocol, origins = build_parts(self.input)
        if (
            self.input_hash != self.input.content_hash
            or self.protocol_hash != self.protocol.content_hash
        ):
            raise ValueError("Input/build/protocol mismatch")
        if self.builder_version == "simple-explicit-v2" and (
            self.protocol != protocol
            or self.origins != origins
            or self.mapping != mapping_for(self.input)
        ):
            raise ValueError("Input/build mapping mismatch")
        return self


def build_parts(value):
    c = value.clarifications
    supplied = c.model_dump(mode="json")
    origins = [
        FieldOrigin(field=name, origin="USER_SUPPLIED" if item else "NOT_SUPPLIED")
        for name, item in supplied.items()
    ]
    origins += [
        FieldOrigin(field="original_idea", origin="USER_SUPPLIED"),
        FieldOrigin(
            field="key_outputs",
            origin="SYSTEM_GENERATED",
            note="Initial research directions, NOT evidence or user verdicts",
        ),
    ]
    data = {
        name: supplied[name] or "UNKNOWN (NOT_SUPPLIED)"
        for name in ("neutral_description", "product_scope", "geography", "target_population")
    }
    outputs = [
        {
            "name": "research_questions",
            "description": "SYSTEM_GENERATED: Questions to clarify scope and identify evidence; "
            "not findings, NOT evidence. Replace or extend with an explicit playbook.",
            "value_type": "text",
            "unit": "text",
        }
    ]
    outputs += [
        {"name": f"user_question_{i}", "description": text, "value_type": "text", "unit": "text"}
        for i, text in enumerate(c.additional_questions)
    ]
    data.update(
        schema_version="0.1",
        protocol_id="simple_" + value.content_hash,
        version=1,
        original_idea=value.idea,
        languages=supplied["languages"] or ["UNKNOWN"],
        time_horizon=supplied["time_horizon"],
        source_cutoff=supplied["source_cutoff"],
        key_outputs=outputs,
        constraints=[],
        assumptions=supplied["assumptions"],
        playbook_reference=None,
        playbook_version=None,
    )
    return ResearchProtocol.model_validate_json(json.dumps(data)), tuple(origins)


def build_protocol(value: SimpleIdeaInput) -> ProtocolBuild:
    value = SimpleIdeaInput.model_validate_json(value.canonical_json())
    protocol, origins = build_parts(value)
    return ProtocolBuild(
        input=value,
        input_hash=value.content_hash,
        protocol=protocol,
        protocol_hash=protocol.content_hash,
        origins=origins,
        mapping=mapping_for(value),
    )
