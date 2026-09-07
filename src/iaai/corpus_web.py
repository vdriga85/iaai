"""Thin Russian preparation UI. Source HTML is never rendered or executed."""

from flask import redirect, render_template, request, url_for

from iaai.errors import IAAIError


def register_corpus_routes(app, service):
    @app.get("/research/<research_id>/sources")
    def sources(research_id):
        return render_template(
            "sources.html",
            research_id=research_id,
            sources=service.list_sources(research_id),
            corpus=service.corpus(research_id),
        )

    @app.post("/research/<research_id>/sources/url")
    def source_url(research_id):
        record = service.add_url(research_id, request.form.get("url", ""))
        return redirect(
            url_for("artifact_details", artifact_id=record.artifact.artifact_id), code=303
        )

    @app.post("/research/<research_id>/sources/text")
    def source_text(research_id):
        record = service.import_text(
            research_id,
            request.form.get("text", ""),
            url=request.form.get("url") or None,
            title=request.form.get("title") or None,
            source_date=request.form.get("source_date") or None,
            initiated_by=request.form.get("initiated_by", "local-user"),
            note=request.form.get("note", ""),
        )
        return redirect(
            url_for("artifact_details", artifact_id=record.artifact.artifact_id), code=303
        )

    @app.get("/artifact/<artifact_id>")
    def artifact_details(artifact_id):
        record = service.artifact(artifact_id)
        return render_template(
            "artifact.html",
            record=record,
            selected=None,
            eligibility=service.eligibility(record.observation.research_id, record),
        )

    @app.get("/artifact/<artifact_id>/chunk/<chunk_id>")
    def chunk_details(artifact_id, chunk_id):
        record = service.artifact(artifact_id)
        selected = next((c for c in record.chunks if c.chunk_id == chunk_id), None)
        if selected is None:
            raise IAAIError("NOT_FOUND", "Фрагмент не найден.")
        return render_template(
            "artifact.html",
            record=record,
            selected=selected,
            eligibility=service.eligibility(record.observation.research_id, record),
        )

    @app.post("/research/<research_id>/corpus/select")
    def corpus_select(research_id):
        service.select(
            research_id,
            request.form.get("artifact_id", ""),
            request.form.get("action") == "include",
        )
        return redirect(url_for("sources", research_id=research_id), code=303)

    @app.post("/research/<research_id>/corpus/freeze")
    def corpus_freeze(research_id):
        snapshot = service.freeze(research_id)
        return redirect(url_for("corpus_snapshot", snapshot_id=snapshot.snapshot_id), code=303)

    @app.get("/corpus/<snapshot_id>")
    def corpus_snapshot(snapshot_id):
        snapshot = service.snapshot(snapshot_id)
        query = request.args.get("query", "")
        results = service.search(snapshot_id, query) if query else None
        return render_template("corpus.html", snapshot=snapshot, results=results, query=query)
