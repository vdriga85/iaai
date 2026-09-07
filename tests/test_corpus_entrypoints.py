import ast
import json
from pathlib import Path

from test_corpus import fake_fetch

from iaai.cli import main
from iaai.web import create_app


def test_corpus_ui_workflow(service, protocol):
    rid = service.create(json.dumps(protocol)).research.research_id
    service.corpus.acquisition = fake_fetch(b"<title>Fixture</title><p>battery fixture text</p>")
    client = create_app(service).test_client()
    base = f"/research/{rid}"
    assert "Источники и корпус" in client.get(base).get_data(as_text=True)
    assert "Импортировать текст вручную" in client.get(base + "/sources").get_data(as_text=True)
    with client.session_transaction() as session:
        csrf = session["csrf"]
    assert client.post(base + "/sources/text", data={"text": "test"}).status_code == 400
    response = client.post(base + "/sources/url", data={"csrf": csrf, "url": "https://example.com"})
    assert response.status_code == 303
    html = client.get(response.location).get_data(as_text=True)
    assert "Fixture" in html and "FETCHED" in html and "Нормализованный текст" in html
    manual = client.post(
        base + "/sources/text",
        data={
            "csrf": csrf,
            "text": "Батарея батарея 😀",
            "title": "Ручной тест",
            "initiated_by": "tester",
            "note": "Fixture",
        },
    )
    assert manual.status_code == 303
    aid = manual.location.rsplit("/", 1)[1]
    assert "Импортировано вручную" in client.get(manual.location).get_data(as_text=True)
    assert (
        client.post(
            base + "/corpus/select", data={"csrf": csrf, "artifact_id": aid, "action": "include"}
        ).status_code
        == 303
    )
    frozen = client.post(base + "/corpus/freeze", data={"csrf": csrf})
    assert frozen.status_code == 303
    result = client.get(frozen.location, query_string={"query": "батарея"})
    assert result.status_code == 200
    assert "Место 1" in result.get_data(as_text=True)
    assert "не достоверность" in result.get_data(as_text=True)
    chunk = service.corpus.artifact(aid).chunks[0]
    page = client.get(f"/artifact/{aid}/chunk/{chunk.chunk_id}")
    assert page.status_code == 200 and "<mark>Батарея батарея 😀</mark>" in page.get_data(
        as_text=True
    )
    assert client.get(f"/artifact/{aid}/chunk/missing").status_code == 404
    assert "SQLite FTS5" in client.get("/diagnostics").get_data(as_text=True)


def test_corpus_cli_workflow(service, protocol, tmp_path, capsys):
    rid = service.create(json.dumps(protocol)).research.research_id
    file = tmp_path / "manual.txt"
    file.write_text("Battery test fixture", encoding="utf-8")
    assert main(["source", "import-text", rid, "--file", str(file)], service) == 0
    aid = json.loads(capsys.readouterr().out)["artifact"]["artifact_id"]
    for command in (
        ["source", "list", rid],
        ["source", "show", aid],
        ["corpus", "include", rid, aid],
        ["corpus", "show", rid],
    ):
        assert main(command, service) == 0
        assert aid in capsys.readouterr().out
    assert main(["corpus", "freeze", rid], service) == 0
    sid = json.loads(capsys.readouterr().out)["snapshot_id"]
    assert main(["corpus", "search", sid, "battery"], service) == 0
    assert json.loads(capsys.readouterr().out)["results"][0]["rank"] == 1
    assert main(["corpus", "exclude", rid, aid], service) == 0


def test_step2_dependency_boundaries():
    root = Path(__file__).parents[1] / "src/iaai"
    for name in ("corpus_domain", "corpus_application", "corpus_ports", "corpus_web"):
        imports = set()
        source = (root / f"{name}.py").read_text("utf-8")
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.add(node.module)
        forbidden = {"sqlite3", "urllib3", "bs4", "iaai.http_acquisition", "iaai.sqlite_corpus"}
        if name != "corpus_web":
            forbidden.add("flask")
        assert not imports & forbidden
        assert "SELECT " not in source
