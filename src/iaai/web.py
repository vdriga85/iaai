"""Replaceable server-rendered UI adapter. All operations delegate to the service."""

import hmac
import json
import secrets
from uuid import uuid4

from flask import Flask, abort, redirect, render_template, request, session, url_for
from werkzeug.exceptions import HTTPException, SecurityError

from iaai.application import ResearchService
from iaai.corpus_web import register_corpus_routes
from iaai.errors import IAAIError
from iaai.proposal_web import register_proposal_routes
from iaai.web_display import (
    CONSTRAINT_TYPES,
    FIELD_LABELS,
    OPERATORS,
    POLICY_STATUSES,
    byte_size,
    display_error,
    duration,
    repository_state,
)


def form_protocol(form) -> str:
    outputs = []
    for line in form.get("advanced_key_outputs", "").splitlines():
        if not line.strip():
            continue
        parts = [part.strip() for part in line.split("|", 3)]
        if len(parts) == 1:
            outputs.append(
                {"name": parts[0], "description": parts[0], "value_type": "text", "unit": "text"}
            )
        elif len(parts) == 4:
            outputs.append(dict(zip(("name", "value_type", "unit", "description"), parts)))
        else:
            raise IAAIError(
                "VALIDATION_ERROR",
                "Расширенные настройки показателей: используйте имя или "
                "имя|number/text|единица|описание.",
            )
    used_names = {output["name"] for output in outputs}
    simple_outputs = []
    next_id = 1
    for line in form.get("key_outputs", "").splitlines():
        if not line.strip():
            continue
        while f"output_{next_id}" in used_names:
            next_id += 1
        name = f"output_{next_id}"
        used_names.add(name)
        simple_outputs.append(
            {"name": name, "description": line, "value_type": "text", "unit": "text"}
        )
        next_id += 1
    outputs = simple_outputs + outputs
    try:
        constraints = json.loads(form.get("constraints", "[]") or "[]")
    except (ValueError, TypeError) as exc:
        raise IAAIError(
            "VALIDATION_ERROR", "Явные ограничения: введите массив JSON или оставьте []."
        ) from exc
    protocol = {
        key: form.get(key, "").strip()
        for key in (
            "original_idea",
            "neutral_description",
            "product_scope",
            "geography",
            "target_population",
        )
    }
    protocol.update(
        schema_version="0.1",
        protocol_id=str(uuid4()),
        version=1,
        languages=[value.strip() for value in form.get("languages", "").split(",")],
        key_outputs=outputs,
        constraints=constraints,
        assumptions=[
            line.strip() for line in form.get("assumptions", "").splitlines() if line.strip()
        ],
    )
    for key in ("time_horizon", "source_cutoff", "playbook_reference", "playbook_version"):
        protocol[key] = form.get(key, "").strip() or None
    return json.dumps(protocol, ensure_ascii=False)


def create_app(service: ResearchService) -> Flask:
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=secrets.token_hex(32),
        MAX_CONTENT_LENGTH=256 * 1024,
        TRUSTED_HOSTS=["127.0.0.1", "localhost"],
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
    )
    app.jinja_env.filters.update(
        byte_size=byte_size, duration=duration, repository_state=repository_state
    )
    app.jinja_env.globals.update(
        field_labels=FIELD_LABELS,
        constraint_types=CONSTRAINT_TYPES,
        operators=OPERATORS,
        policy_statuses=POLICY_STATUSES,
    )
    if service.corpus is not None:
        register_corpus_routes(app, service.corpus)
    if service.proposals is not None:
        register_proposal_routes(app, service.proposals)

    @app.before_request
    def protect_local_write():
        # No authentication. CSRF and Host checks protect localhost from other web pages.
        if "csrf" not in session:
            session["csrf"] = secrets.token_hex(32)
        if request.method == "POST":
            token = request.form.get("csrf", "")
            if not hmac.compare_digest(token, session["csrf"]):
                abort(400, "Обновите страницу формы и повторите отправку: защитный код устарел.")
            origin = request.headers.get("Origin")
            if origin is not None and origin != request.host_url.rstrip("/"):
                abort(403, "Отправка данных с постороннего сайта запрещена.")

    @app.after_request
    def security_headers(response):
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; "
            "frame-ancestors 'none'; base-uri 'none'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.errorhandler(IAAIError)
    def application_error(error):
        status = (
            404 if error.code == "NOT_FOUND" else 400 if error.code == "VALIDATION_ERROR" else 503
        )
        return render_template("error.html", error=display_error(error)), status

    @app.errorhandler(HTTPException)
    def http_error(error):
        if isinstance(error, SecurityError):
            # Rejected Host has no URL adapter; do not render navigation with url_for.
            return (
                '<!doctype html><html lang="ru"><meta charset="utf-8">'
                "<title>IAAI — Ошибка</title><p>Недопустимый адрес сервера. "
                "Откройте IAAI по локальному адресу 127.0.0.1.</p></html>",
                400,
            )
        messages = {
            400: "Запрос не принят. Откройте локальную страницу и обновите форму перед отправкой.",
            403: "Отправка данных с постороннего сайта запрещена.",
            404: "Страница не найдена. Вернитесь к списку исследований.",
            405: "Этот способ обращения к странице не поддерживается.",
            413: "Форма слишком большая. Сократите текст или расширенные настройки.",
        }
        result = {
            "messages": [messages.get(error.code, "Не удалось открыть страницу.")],
            "technical": {"http_status": error.code},
        }
        return render_template("error.html", error=result), error.code

    @app.get("/")
    def home():
        return render_template("home.html", researches=service.list_researches())

    @app.route("/research/new", methods=["GET", "POST"])
    def new_research():
        error = None
        if request.method == "POST":
            try:
                bundle = service.create(
                    form_protocol(request.form), request.form.get("policy", "").strip() or None
                )
                return redirect(
                    url_for("details", research_id=bundle.research.research_id), code=303
                )
            except IAAIError as exc:
                error = display_error(exc)
        return render_template("new.html", form=request.form, error=error), 400 if error else 200

    @app.get("/research/<research_id>")
    def details(research_id):
        raw_revision = request.args.get("revision")
        try:
            revision = int(raw_revision) if raw_revision is not None else None
            if revision is not None and revision < 1:
                raise ValueError
        except ValueError as exc:
            raise IAAIError(
                "VALIDATION_ERROR", "Версия исследования: укажите целое число от 1."
            ) from exc
        bundle = service.get(research_id, revision)
        return render_template("details.html", bundle=bundle, has_corpus=service.corpus is not None)

    @app.get("/diagnostics")
    def diagnostics():
        result = service.doctor()
        return render_template("diagnostics.html", result=result), 200 if result["ok"] else 503

    return app
