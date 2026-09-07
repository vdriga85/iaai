"""Replaceable server-rendered UI adapter. All operations delegate to the service."""

import hmac
import json
import secrets
from uuid import uuid4

from flask import Flask, abort, redirect, render_template, request, session, url_for

from iaai.application import ResearchService
from iaai.errors import IAAIError


def form_protocol(form) -> str:
    outputs = []
    for line in form.get("key_outputs", "").splitlines():
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
                "VALIDATION_ERROR", "Outputs: name or name|number/text|unit|description"
            )
    try:
        constraints = json.loads(form.get("constraints", "[]") or "[]")
    except (ValueError, TypeError) as exc:
        raise IAAIError("VALIDATION_ERROR", "Constraints must be a JSON array") from exc
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

    @app.before_request
    def protect_local_write():
        # No authentication. CSRF and Host checks protect localhost from other web pages.
        if "csrf" not in session:
            session["csrf"] = secrets.token_hex(32)
        if request.method == "POST":
            token = request.form.get("csrf", "")
            if not hmac.compare_digest(token, session["csrf"]):
                abort(400, "Invalid form token; reload the form")
            origin = request.headers.get("Origin")
            if origin is not None and origin != request.host_url.rstrip("/"):
                abort(403, "Cross-origin writes are disabled")

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
        return render_template("error.html", error=error.as_dict()), status

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
                error = exc.as_dict()
        return render_template("new.html", form=request.form, error=error), 400 if error else 200

    @app.get("/research/<research_id>")
    def details(research_id):
        raw_revision = request.args.get("revision")
        try:
            revision = int(raw_revision) if raw_revision is not None else None
            if revision is not None and revision < 1:
                raise ValueError
        except ValueError as exc:
            raise IAAIError("VALIDATION_ERROR", "Revision must be a positive integer") from exc
        bundle = service.get(research_id, revision)
        return render_template("details.html", bundle=bundle)

    @app.get("/diagnostics")
    def diagnostics():
        result = service.doctor()
        return render_template("diagnostics.html", result=result), 200 if result["ok"] else 503

    return app
