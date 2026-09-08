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


class ProtocolBuild(Snapshot):
    schema_version: Literal["0.1"] = "0.1"
    builder_version: Literal["simple-explicit-v1"] = "simple-explicit-v1"
    input: SimpleIdeaInput
    input_hash: Hash
    protocol: ResearchProtocol
    protocol_hash: Hash
    origins: tuple[FieldOrigin, ...]
    neutralization: Literal["NOT_PERFORMED"] = "NOT_PERFORMED"

    @model_validator(mode="after")
    def integrity(self) -> Self:
        protocol, origins = build_parts(self.input)
        if (
            self.input_hash != self.input.content_hash
            or self.protocol != protocol
            or self.protocol_hash != protocol.content_hash
            or self.origins != origins
        ):
            raise ValueError("Input/build/protocol mismatch")
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
    constraints = list(c.user_constraints)
    if c.budget is not None:
        constraints.insert(0, "Budget clarification (not parsed): " + c.budget)
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
        {
            "name": f"user_constraint_{i}",
            "description": "USER_SUPPLIED boundary (unparsed), NOT evidence: " + text,
            "value_type": "text",
            "unit": "text",
        }
        for i, text in enumerate(constraints)
    ]
    outputs += [
        {"name": f"user_question_{i}", "description": text, "value_type": "text", "unit": "text"}
        for i, text in enumerate(c.additional_questions)
    ]
    # Text constraints preserve exact boundaries without guessing currency/operator/meaning.
    constraint_defs = [
        {
            "output": f"user_constraint_{i}",
            "type": "USER",
            "operator": "eq",
            "value": text,
            "unit": "text",
            "origin": "SimpleIdeaInput explicit boundary",
        }
        for i, text in enumerate(constraints)
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
        constraints=constraint_defs,
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
    )
