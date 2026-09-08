import json

import pytest
from test_proposals import FakeModel

from iaai.cli import main
from iaai.web import create_app


@pytest.mark.parametrize("bad_id", ["art_forbidden", "chk_invented"])
def test_invalid_reference_visible_in_operation_and_queue(proposal_setup, bad_id):
    service, rid, snap, _ = proposal_setup

    def invalid(value):
        value["claims"][0]["chunk_ids"].append(bad_id)
        return json.dumps(value)

    service.proposals.model = FakeModel(invalid)
    operation = service.proposals.run(snap.snapshot_id, "battery")
    assert operation["status"] == "MODEL_OUTPUT_INVALID"
    assert not operation["candidates"]
    client = create_app(service).test_client()
    link = f"/proposal/{operation['request'].operation_id}"
    for url in (link, f"/research/{rid}/proposals"):
        html = client.get(url).get_data(as_text=True)
        assert "Результат модели отклонён валидатором" in html
        assert "MODEL_OUTPUT_INVALID" in html and "Открыть операцию" in html
        assert link in html
    queue_html = client.get(f"/research/{rid}/proposals").get_data(as_text=True)
    assert bad_id not in queue_html


@pytest.mark.parametrize("status", ["MODEL_TIMEOUT", "NOT_CONFIGURED"])
def test_other_terminal_failures_visible(proposal_setup, status):
    service, rid, snap, _ = proposal_setup
    service.proposals.model = FakeModel(status=status)
    service.proposals.run(snap.snapshot_id, "battery")
    html = (
        create_app(service).test_client().get(f"/research/{rid}/proposals").get_data(as_text=True)
    )
    assert "Генерация завершилась без кандидатов" in html and status in html


def test_ui_review_workflow(proposal_setup):
    service, rid, snap, _ = proposal_setup
    client = create_app(service).test_client()
    page = client.get(f"/corpus/{snap.snapshot_id}/proposals/new")
    assert "Новый вопрос для модели" in page.get_data(as_text=True)
    assert "не являются доказанными фактами" in page.get_data(as_text=True)
    with client.session_transaction() as session:
        csrf = session["csrf"]
    url = f"/corpus/{snap.snapshot_id}/proposals"
    assert client.post(url, data={"question": "battery"}).status_code == 400
    response = client.post(url, data={"csrf": csrf, "question": "battery"})
    assert response.status_code == 303
    html = client.get(response.location).get_data(as_text=True)
    assert "Ожидает проверки" in html and "Кандидат утверждения" in html
    entries = service.proposals.queue(rid)["entries"]
    for entry, action in zip(entries, ("ACCEPTED", "REJECTED", "EDITED_ACCEPTED"), strict=True):
        data = {"csrf": csrf, "action": action, "reviewer": "Human"}
        if action == "EDITED_ACCEPTED":
            data["edited_text"] = "Отредактированный кандидат"
        result = client.post(
            f"/proposal/candidate/{entry['candidate'].candidate_id}/review", data=data
        )
        assert result.status_code == 303
    html = client.get(f"/research/{rid}/proposals").get_data(as_text=True)
    assert "HUMAN_REVIEWED" in html and "Отредактированный кандидат" in html
    assert "Battery use increases in the fixture" in html
    assert "PENDING_REVIEW</p>" not in html


def test_cli_review_and_doctor(proposal_setup, capsys):
    service, rid, snap, _ = proposal_setup
    assert main(["model", "doctor"], service) == 0
    capsys.readouterr()
    assert main(["proposal", "run", snap.snapshot_id, "--question", "battery"], service) == 0
    op = json.loads(capsys.readouterr().out)
    oid = op["request"]["operation_id"]
    assert main(["proposal", "show", oid], service) == 0
    capsys.readouterr()
    for entry, action in zip(op["candidates"], ("accept", "reject", "edit-accept"), strict=True):
        args = ["proposal", action, entry["candidate"]["candidate_id"]]
        if action == "edit-accept":
            args += ["--text", "human edit"]
        assert main(args, service) == 0
        capsys.readouterr()
    assert main(["proposal", "queue", rid], service) == 0
    assert json.loads(capsys.readouterr().out)["measurements"]["ACCEPTED"] == 1
