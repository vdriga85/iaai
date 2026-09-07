import ast
import json
from pathlib import Path

import pytest

from iaai.cli import main
from iaai.web import create_app


def valid_form(client):
    client.get("/research/new")
    with client.session_transaction() as session:
        token = session["csrf"]
    return {
        "csrf": token,
        "original_idea": "A test idea",
        "neutral_description": "Neutral scope",
        "product_scope": "Laptop",
        "geography": "Australia",
        "target_population": "Adults",
        "languages": "en",
        "key_outputs": "Время работы от батареи\nСуществующие альтернативы",
        "constraints": "[]",
    }


def test_ui_shared_creation_and_read(service, monkeypatch):
    calls = []
    create = service.create

    def spy(*args):
        calls.append(args)
        return create(*args)

    monkeypatch.setattr(service, "create", spy)
    client = create_app(service).test_client()
    assert client.get("/").status_code == 200
    response = client.post("/research/new", data=valid_form(client))
    assert response.status_code == 303
    assert len(calls) == 1
    details = client.get(response.location)
    assert details.status_code == 200
    for label in (
        "A test idea",
        "UNVALIDATED",
        "Ревизия исследования №1",
        "Manifest — технический паспорт",
        "Не заданы",
        "Показать исходный JSON",
    ):
        assert label in details.get_data(as_text=True)
    assert b"A test idea" in client.get("/").data
    assert client.get("/diagnostics").status_code == 200
    assert b"5000" in client.get("/diagnostics").data
    assert (
        service.get(service.list_researches()[0].research_id).protocol.original_idea
        == "A test idea"
    )
    assert client.get(response.location + "?revision=oops").status_code == 400
    assert client.get("/research/absent").status_code == 404


@pytest.mark.parametrize(
    "field,value",
    [
        ("geography", ""),
        ("constraints", "bad JSON"),
        ("advanced_key_outputs", "bad|format"),
        ("policy", '{"schema_version":"unknown"}'),
    ],
)
def test_ui_validation(service, field, value):
    client = create_app(service).test_client()
    form = valid_form(client)
    form[field] = value
    response = client.post("/research/new", data=form)
    assert response.status_code == 400
    assert b"VALIDATION_ERROR" in response.data
    assert not service.list_researches()


def test_local_security_and_escaping(service):
    client = create_app(service).test_client()
    assert client.get("/", headers={"Host": "evil.example"}).status_code == 400
    assert client.post("/research/new", data={}).status_code == 400
    form = valid_form(client)
    assert (
        client.post(
            "/research/new", data=form, headers={"Origin": "https://evil.example"}
        ).status_code
        == 403
    )
    form["original_idea"] = "<script>alert(1)</script>"
    response = client.post("/research/new", data=form, follow_redirects=True)
    assert b"<script>alert(1)</script>" not in response.data
    assert b"&lt;script&gt;" in response.data
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]


def test_serve_local_only(service, monkeypatch):
    from flask import Flask

    captured = {}
    monkeypatch.setattr(Flask, "run", lambda self, **kwargs: captured.update(kwargs))
    assert main(["serve"], service) == 0
    assert captured == {"host": "127.0.0.1", "port": 8765, "debug": False, "use_reloader": False}
    assert main(["serve", "--port", "0"], service) == 1


def test_cli_workflow(service, protocol, tmp_path, capsys):
    file = tmp_path / "protocol.json"
    file.write_text(json.dumps(protocol), encoding="utf-8")
    assert main(["doctor"], service) == 0
    assert json.loads(capsys.readouterr().out)["database"]["journal_mode"] == "wal"
    assert main(["research", "create", "--protocol", str(file)], service) == 0
    bundle = json.loads(capsys.readouterr().out)
    rid, run_id = bundle["research"]["research_id"], bundle["manifest"]["run_id"]
    for command in (["research", "list"], ["research", "show", rid], ["manifest", "show", run_id]):
        assert main(command, service) == 0
        assert rid in capsys.readouterr().out
    assert main(["research", "show", "absent"], service) == 1
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "NOT_FOUND"
    assert main(["research", "create", "--protocol", str(tmp_path / "missing")], service) == 1


def test_dependency_boundaries():
    root = Path(__file__).parents[1] / "src" / "iaai"
    for name in ("domain", "application", "ports", "web"):
        tree = ast.parse((root / f"{name}.py").read_text("utf-8"))
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.add(node.module or "")
        forbidden = {"sqlite3", "iaai.sqlite_store", "iaai.bootstrap"}
        if name != "web":
            forbidden |= {"flask", "iaai.web"}
        assert not imports & forbidden
    assert "SELECT " not in (root / "web.py").read_text("utf-8")
