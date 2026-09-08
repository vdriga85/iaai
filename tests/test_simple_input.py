import json
import sqlite3

import pytest
from pydantic import ValidationError

from iaai.bootstrap import build_service
from iaai.proposal_context import assemble
from iaai.proposal_domain import ProposalPolicy
from iaai.simple_input import ProtocolBuild, SimpleIdeaInput, build_protocol
from iaai.web import create_app


def test_deferred_constraints_restart(service, tmp_path):
    supplied = {"budget": "200 AUD", "user_constraints": ["  Must fit my desk  "]}
    bundle = service.create_simple(json.dumps({"idea": "idea", "clarifications": supplied}))
    rid = bundle.research.research_id
    build = service.input_build(rid)
    assert build.input.clarifications.budget == "200 AUD"
    assert build.input.clarifications.user_constraints == ("  Must fit my desk  ",)
    for name in supplied:
        assert next(o.origin for o in build.origins if o.field == name) == "USER_SUPPLIED"
        assert next(m.status for m in build.mapping if m.field == name) == "DEFERRED_NOT_MAPPED"
    assert not build.protocol.constraints
    assert [o.name for o in build.protocol.key_outputs] == ["research_questions"]
    assert "200 AUD" not in build.protocol.canonical_json()
    assert "user_constraint_" not in build.protocol.canonical_json()
    restarted = build_service(service.store.path, tmp_path)
    assert restarted.input_build(rid).canonical_json() == build.canonical_json()
    page = create_app(restarted).test_client().get(f"/research/{rid}").get_data(as_text=True)
    assert "DEFERRED_NOT_MAPPED" in page and "USER_SUPPLIED" in page
    absent = build_protocol(SimpleIdeaInput(idea="idea"))
    assert absent.input.clarifications.budget is None
    assert next(m.status for m in absent.mapping if m.field == "budget") == "NOT_SUPPLIED"
    assert next(o.origin for o in absent.origins if o.field == "budget") == "NOT_SUPPLIED"
    assert absent.input_hash != build.input_hash
    with pytest.raises(ValidationError):
        ProtocolBuild.model_validate_json(build.model_copy(update={"mapping": ()}).canonical_json())


def test_legacy_build_canonical_bytes():
    data = build_protocol(SimpleIdeaInput(idea="legacy")).model_dump(mode="json")
    data["builder_version"] = "simple-explicit-v1"
    del data["mapping"]
    raw = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    assert ProtocolBuild.model_validate_json(raw).canonical_json() == raw


def test_one_line_creation_restart(service, tmp_path):
    bundle = service.create_simple(json.dumps({"idea": "Двухэкранный ноутбук"}))
    rid = bundle.research.research_id
    build = service.input_build(rid)
    assert build.input.idea == "Двухэкранный ноутбук"
    assert build.protocol == bundle.protocol
    assert bundle.protocol.geography == "UNKNOWN (NOT_SUPPLIED)"
    assert bundle.protocol.target_population == "UNKNOWN (NOT_SUPPLIED)"
    assert build.input.clarifications.budget is None
    assert not bundle.protocol.constraints
    assert bundle.protocol.languages == ("UNKNOWN",)
    assert bundle.protocol.key_outputs[0].name == "research_questions"
    assert "SYSTEM_GENERATED" in bundle.protocol.key_outputs[0].description
    assert build_protocol(build.input) == build
    restarted = build_service(service.store.path, tmp_path)
    assert restarted.get(rid) == bundle and restarted.input_build(rid) == build


def test_supplied_scope_and_questions(service):
    bundle = service.create_simple(
        json.dumps(
            {
                "idea": "idea",
                "clarifications": {
                    "geography": "Australia",
                    "budget": "200 AUD",
                    "additional_questions": ["Repair cost?"],
                    "assumptions": ["Explicit assumption"],
                    "time_horizon": "",
                    "source_cutoff": "",
                    "neutral_description": "Neutral topic",
                    "languages": ["en"],
                },
            }
        )
    )
    build = service.input_build(bundle.research.research_id)
    assert bundle.protocol.geography == "Australia"
    origins = {item.field: item.origin for item in build.origins}
    assert origins["geography"] == "USER_SUPPLIED"
    assert origins["target_population"] == "NOT_SUPPLIED"
    assert bundle.protocol.time_horizon is None and bundle.protocol.source_cutoff is None
    assert bundle.protocol.assumptions == ("Explicit assumption",)
    assert build.input.clarifications.budget == "200 AUD"
    assert origins["budget"] == "USER_SUPPLIED"
    assert not bundle.protocol.constraints
    assert not any(o.name.startswith("user_constraint_") for o in bundle.protocol.key_outputs)
    assert any(o.description == "Repair cost?" for o in bundle.protocol.key_outputs)


def test_emotional_input_only_in_audit(service):
    idea = (
        "  Это гарантированно гениальный двухэкранный ноутбук, "
        "который точно уничтожит конкурентов  "
    )
    bundle = service.create_simple(json.dumps({"idea": idea}))
    assert bundle.protocol.original_idea == idea
    build = service.input_build(bundle.research.research_id)
    assert build.input.idea == idea and build.neutralization == "NOT_PERFORMED"
    prompt = assemble(bundle.protocol, "Which sources are needed?", (), ProposalPolicy())[2]
    assert idea not in prompt and "уничтожит" not in prompt and "гениальный" not in prompt


@pytest.mark.parametrize("idea", ["", " ", "\n"])
def test_empty_idea_rejected(idea):
    with pytest.raises(ValidationError):
        SimpleIdeaInput(idea=idea)


def test_explicit_date_and_unknown_value_distinguished():
    value = SimpleIdeaInput.model_validate_json(
        '{"idea":"idea","clarifications":{"source_cutoff":"2020-01-02",'
        '"geography":"UNKNOWN (NOT_SUPPLIED)"}}'
    )
    build = build_protocol(value)
    assert str(build.protocol.source_cutoff) == "2020-01-02"
    assert next(o for o in build.origins if o.field == "geography").origin == "USER_SUPPLIED"


def test_simple_ui_and_advanced_preserved(service):
    client = create_app(service).test_client()
    html = client.get("/research/new").get_data(as_text=True)
    assert "Что хотите исследовать?" in html and "Уточнить исследование" in html
    assert html.count(" required") == 1
    assert "<details>" in html and "<details open" not in html
    with client.session_transaction() as session:
        csrf = session["csrf"]
    response = client.post("/research/new", data={"csrf": csrf, "idea": "Двухэкранный ноутбук"})
    assert response.status_code == 303
    page = client.get(response.location).get_data(as_text=True)
    assert "NOT_SUPPLIED" in page and "Аудит input" in page
    assert client.get("/research/new/advanced").status_code == 200


def test_input_build_immutable_and_atomic(service):
    bundle = service.create_simple('{"idea":"test"}')
    with sqlite3.connect(service.store.path) as c:
        for action in ("UPDATE input_builds SET content=content", "DELETE FROM input_builds"):
            with pytest.raises(sqlite3.IntegrityError):
                c.execute(action)
    before = service.list_researches()
    build = service.input_build(bundle.research.research_id)
    with pytest.raises(ValidationError):
        type(build).model_validate_json(
            build.model_copy(update={"input_hash": "0" * 64}).canonical_json()
        )
    assert service.list_researches() == before


def test_build_conflict_rolls_back_research(service):
    from contextlib import contextmanager

    real = service.store.connection

    @contextmanager
    def failing(*args):
        with real(*args) as c:
            c.execute(
                "CREATE TEMP TRIGGER reject_build BEFORE INSERT ON input_builds "
                "BEGIN SELECT RAISE(ABORT, 'test failure'); END"
            )
            yield c

    service.store.connection = failing
    with pytest.raises(Exception):
        service.create_simple('{"idea":"atomic"}')
    service.store.connection = real
    assert service.list_researches() == ()
    with real() as c:
        for table in ("protocols", "policies", "revisions", "manifests", "input_builds"):
            assert c.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0
