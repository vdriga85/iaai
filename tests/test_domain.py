import json

import pytest
from pydantic import ValidationError

from iaai.application import parse_policy, parse_protocol
from iaai.errors import IAAIError


def test_protocol_frozen_hash_and_nulls(protocol):
    model = parse_protocol(json.dumps(protocol))
    assert model.content_hash == parse_protocol(model.canonical_json()).content_hash
    assert model.content_hash == parse_protocol(json.dumps(protocol, sort_keys=True)).content_hash
    assert model.constraints == ()
    assert model.source_cutoff is None
    with pytest.raises(ValidationError):
        model.geography = "Elsewhere"
    with pytest.raises(ValidationError):
        model.key_outputs[0].unit = "AUD"


@pytest.mark.parametrize(
    "field,value",
    [
        ("geography", ""),
        ("product_scope", None),
        ("version", True),
        ("version", "1"),
        ("schema_version", "9"),
        ("languages", []),
        ("languages", ["en", "en"]),
        ("key_outputs", []),
        ("source_cutoff", "2026-02-30"),
        ("playbook_reference", "book"),
        ("extra", 1),
        ("target_population", "   "),
    ],
)
def test_bad_protocol(protocol, field, value):
    protocol[field] = value
    with pytest.raises(IAAIError) as failure:
        parse_protocol(json.dumps(protocol))
    assert failure.value.code == "VALIDATION_ERROR"


def test_required_scope(protocol):
    del protocol["neutral_description"]
    with pytest.raises(IAAIError):
        parse_protocol(json.dumps(protocol))


def constraint():
    return {
        "output": "prototype_cost",
        "type": "USER",
        "operator": "le",
        "value": 50000,
        "unit": "EUR",
        "origin": "Explicit user budget",
    }


def test_constraint_origin(protocol):
    protocol["constraints"] = [constraint()]
    model = parse_protocol(json.dumps(protocol))
    assert model.constraints[0].origin == "Explicit user budget"
    assert model.constraints[0].type == "USER"


@pytest.mark.parametrize(
    "field,value",
    [
        ("unit", "euros"),
        ("unit", "AUD"),
        ("value", "50000"),
        ("value", True),
        ("value", float("nan")),
        ("origin", ""),
        ("type", "BUSINESS_GOOD_BAD"),
        ("output", "missing"),
        ("operator", "bad"),
    ],
)
def test_bad_constraint(protocol, field, value):
    item = constraint()
    item[field] = value
    protocol["constraints"] = [item]
    with pytest.raises(IAAIError):
        parse_protocol(json.dumps(protocol))


def test_bad_output_unit_and_duplicates(protocol):
    protocol["key_outputs"][0]["unit"] = "text"
    with pytest.raises(IAAIError):
        parse_protocol(json.dumps(protocol))
    protocol["key_outputs"][0]["unit"] = "EUR"
    protocol["key_outputs"].append(protocol["key_outputs"][0])
    with pytest.raises(IAAIError):
        parse_protocol(json.dumps(protocol))


@pytest.mark.parametrize(
    "section,field,value",
    [
        ("resources", "run_disk_bytes", 0),
        ("resources", "rss_bytes", -1),
        ("resources", "cpu_seconds", "7200"),
        ("resources", "run_disk_bytes", 10**15),
        ("resources", "wall_deadline_seconds", 1),
        ("resources", "rss_bytes", None),
        ("resources", "cpu_seconds", True),
        ("runtime", "sqlite_busy_timeout_seconds", 0),
        ("runtime", "unknown", 1),
        ("scheduler", "lane_shares", [0.5, 0.5, 0]),
        ("scheduler", "lane_shares", [0.2, 0.2, 0.2]),
        ("scheduler", "mode", "ADV"),
        ("stop", "novelty_ceiling", 1.1),
        ("stop", "novelty_ceiling", float("inf")),
        ("stop", "output_rel_tolerance", 0),
        ("evaluation", "repeat_seeds", [0, 0]),
        ("evaluation", "checkpoint_fractions", [0.5, 0.25, 1.0]),
        ("evaluation", "checkpoint_fractions", [0.5]),
        ("stop", "schema_version", "2"),
    ],
)
def test_invalid_policy(policy, section, field, value):
    policy[section][field] = value
    with pytest.raises(IAAIError):
        parse_policy(json.dumps(policy))


def test_policy_hash_status_and_versions(policy):
    before = parse_policy(json.dumps(policy))
    assert before.status == "UNVALIDATED"
    assert before.content_hash == parse_policy(before.canonical_json()).content_hash
    policy["stop"]["novelty_ceiling"] = 0.1
    assert before.content_hash != parse_policy(json.dumps(policy)).content_hash
    policy["schema_version"] = "1.0"
    with pytest.raises(IAAIError):
        parse_policy(json.dumps(policy))


def test_calibration_requires_provenance(policy):
    policy["status"] = "EVALUATED"
    with pytest.raises(IAAIError):
        parse_policy(json.dumps(policy))
