"""Thin local human-review routes. No SQL or process execution."""

from flask import redirect, render_template, request, url_for

from iaai.proposal_cli import serializable


def register_proposal_routes(app, service):
    app.jinja_env.globals["has_proposals"] = True
    app.jinja_env.filters["proposal_json"] = serializable

    @app.get("/corpus/<snapshot_id>/proposals/new")
    def proposal_new(snapshot_id):
        return render_template(
            "proposal_new.html",
            snapshot=service.corpus.snapshot(snapshot_id),
            model=service.diagnostics(),
        )

    @app.post("/corpus/<snapshot_id>/proposals")
    def proposal_run(snapshot_id):
        operation = service.run(snapshot_id, request.form.get("question", ""))
        return redirect(
            url_for("proposal_show", operation_id=operation["request"].operation_id), code=303
        )

    @app.get("/proposal/<operation_id>")
    def proposal_show(operation_id):
        return render_template("proposal_operation.html", operation=service.show(operation_id))

    @app.get("/research/<research_id>/proposals")
    def proposal_queue(research_id):
        return render_template(
            "proposal_queue.html", research_id=research_id, queue=service.queue(research_id)
        )

    @app.post("/proposal/candidate/<candidate_id>/review")
    def proposal_review(candidate_id):
        service.review(
            candidate_id,
            request.form.get("action", ""),
            request.form.get("reviewer", ""),
            edited_text=request.form.get("edited_text") or None,
            reason_code=request.form.get("reason_code") or None,
            comment=request.form.get("comment", ""),
        )
        candidate = service.store.candidate(candidate_id)
        return redirect(url_for("proposal_show", operation_id=candidate.operation_id), code=303)
