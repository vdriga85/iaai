import json
import re
from html.parser import HTMLParser

import pytest
from test_entrypoints import valid_form

from iaai.application import parse_protocol
from iaai.cli import main
from iaai.web import create_app, form_protocol
from iaai.web_display import byte_size, duration


class FormStructure(HTMLParser):
    """Inspect semantics without adding a DOM/browser dependency."""

    def __init__(self, html):
        super().__init__()
        self.details = []
        self.fields = {}
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "details":
            self.details.append("open" in attrs)
        if tag in ("input", "textarea") and "name" in attrs:
            self.fields[attrs["name"]] = (attrs, tuple(self.details))

    def handle_endtag(self, tag):
        if tag == "details":
            self.details.pop()


def test_russian_navigation_form_and_cutoff(service):
    client = create_app(service).test_client()
    for page in ("/", "/research/new/advanced", "/diagnostics"):
        html = client.get(page).get_data(as_text=True)
        assert '<html lang="ru">' in html
        for label in ("Исследования", "Новое исследование", "Диагностика"):
            assert label in html
    html = client.get("/research/new/advanced").get_data(as_text=True)
    for label in (
        "Исходная идея",
        "Что именно мы исследуем",
        "Конфигурация продукта",
        "Рынок / география",
        "Для кого предназначен продукт",
        "Языки источников",
        "Горизонт исследования",
        "Использовать источники не позднее",
        "Что нужно установить в ходе исследования",
        "Явные предположения",
        "Создать исследование",
        "историческую дату",
        "оставьте поле пустым",
        "не дата окончания исследования",
        "вручную",
        "Idea Parser",
    ):
        assert label in html
    structure = FormStructure(html)
    assert structure.fields["source_cutoff"][0]["type"] == "date"
    for field in (
        "constraints",
        "policy",
        "advanced_key_outputs",
        "playbook_reference",
        "playbook_version",
    ):
        attrs, details = structure.fields[field]
        assert details and not any(details), field
        assert "required" not in attrs
    assert not structure.fields["key_outputs"][1]


def test_plain_russian_outputs_exact_text_and_stable_ids(service):
    client = create_app(service).test_client()
    form = valid_form(client)
    descriptions = ["Время работы от батареи", "  Цена | стоимость  ", "Время работы от батареи"]
    form["key_outputs"] = "\n".join(descriptions)
    del form["constraints"]  # Browser/user does not need to supply developer settings.
    first = json.loads(form_protocol(form))["key_outputs"]
    assert first == json.loads(form_protocol(form))["key_outputs"]
    response = client.post("/research/new/advanced", data=form)
    assert response.status_code == 303
    bundle = service.get(service.list_researches()[0].research_id)
    assert [o.description for o in bundle.protocol.key_outputs] == descriptions
    assert [o.name for o in bundle.protocol.key_outputs] == ["output_1", "output_2", "output_3"]
    assert all(re.fullmatch(r"[a-zA-Z0-9_.-]+", o.name) for o in bundle.protocol.key_outputs)
    assert bundle.protocol.constraints == ()
    assert parse_protocol(bundle.protocol.canonical_json()) == bundle.protocol


def test_advanced_outputs_and_constraints(service):
    client = create_app(service).test_client()
    form = valid_form(client)
    form["key_outputs"] = ""
    form["advanced_key_outputs"] = "prototype_cost|number|EUR|Стоимость прототипа\nalternatives"
    form["constraints"] = json.dumps(
        [
            {
                "output": "prototype_cost",
                "type": "USER",
                "operator": "le",
                "value": 20000,
                "unit": "EUR",
                "origin": "Задано пользователем",
            }
        ]
    )
    response = client.post("/research/new/advanced", data=form, follow_redirects=True)
    assert response.status_code == 200
    bundle = service.get(service.list_researches()[0].research_id)
    assert bundle.protocol.key_outputs[0].name == "prototype_cost"
    assert bundle.protocol.key_outputs[0].value_type == "number"
    assert bundle.protocol.constraints[0].type == "USER"
    assert "не больше 20000 EUR" in response.get_data(as_text=True)


def test_generated_ids_do_not_collide(service):
    client = create_app(service).test_client()
    form = valid_form(client)
    form["advanced_key_outputs"] = "output_1|number|hours|Время работы"
    response = client.post("/research/new/advanced", data=form)
    assert response.status_code == 303
    outputs = service.get(service.list_researches()[0].research_id).protocol.key_outputs
    assert [o.name for o in outputs] == ["output_2", "output_3", "output_1"]


@pytest.mark.parametrize(
    "field,value,label",
    [
        ("source_cutoff", "yesterday", "Использовать источники не позднее"),
        ("target_population", "", "Для кого предназначен продукт"),
        ("key_outputs", "\n  \n", "Что нужно установить"),
        ("advanced_key_outputs", "bad|format", "Расширенные настройки показателей"),
        ("constraints", "not json", "Явные ограничения"),
    ],
)
def test_russian_validation_preserves_input(service, field, value, label):
    client = create_app(service).test_client()
    form = valid_form(client)
    form[field] = value
    response = client.post("/research/new/advanced", data=form)
    assert response.status_code == 400
    html = response.get_data(as_text=True)
    alert = html.split('<div class="error" role="alert">')[1]
    ordinary_message = alert.split("<details>")[0]
    assert label in ordinary_message
    assert "Input should" not in ordinary_message
    assert "VALIDATION_ERROR" not in ordinary_message
    assert "VALIDATION_ERROR" in alert
    assert "A test idea" in html
    assert not service.list_researches()


def test_details_readable_and_raw_exact(service, protocol, capsys):
    before = service.create(json.dumps(protocol))
    client = create_app(service).test_client()
    html = client.get(f"/research/{before.research.research_id}").get_data(as_text=True)
    for label in (
        "Исходная идея",
        "Границы исследования",
        "Явные ограничения",
        "Ревизия исследования №1",
        "Политика исследования",
        "технический паспорт",
        "2 GiB",
        "16 GiB",
        "2 ч",
        "24 ч",
    ):
        assert label in html
    ordinary = html.split("<summary>Технические детали</summary>")[0]
    assert before.protocol.content_hash not in ordinary
    assert "2147483648" not in ordinary
    assert before.protocol.content_hash in html
    assert "2147483648" in html
    assert main(["research", "show", before.research.research_id], service) == 0
    assert json.loads(capsys.readouterr().out) == before.model_dump(mode="json")
    assert service.get(before.research.research_id) == before


def test_localized_diagnostics_failure_and_security(service, tmp_path):
    client = create_app(service).test_client()
    html = client.get("/diagnostics").get_data(as_text=True)
    for label in (
        "База данных: OK",
        "Режим SQLite WAL",
        "Надёжная запись FULL",
        "Foreign Keys",
        "Версия схемы",
        "Рабочая папка",
        "Свободное место",
        "Git commit",
        "Состояние репозитория",
        "Недоступно",
    ):
        assert label in html
    from iaai.bootstrap import build_service

    broken = create_app(build_service(tmp_path)).test_client().get("/diagnostics")
    assert broken.status_code == 503
    assert "База данных: Ошибка" in broken.get_data(as_text=True)
    assert "баз" in broken.get_data(as_text=True)
    assert "Действие не выполнено" in client.post("/research/new/advanced").get_data(as_text=True)
    assert client.get("/", headers={"Host": "evil.example"}).status_code == 400


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, "Недоступно"),
        (0, "0 байт"),
        (1024, "1 KiB"),
        (1024**2, "1 MiB"),
        (2 * 1024**3, "2 GiB"),
    ],
)
def test_byte_display(value, expected):
    assert byte_size(value) == expected


def test_duration_display():
    assert duration(3661) == "1 ч 1 мин 1 с"
    assert duration(120) == "2 мин"
