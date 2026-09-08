import json

from iaai.cli import main
from iaai.web import create_app


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
