"""CLI preparation commands, delegated to the same service as web."""

from pathlib import Path


def add_commands(commands):
    sources = commands.add_parser("source").add_subparsers(dest="action", required=True)
    url = sources.add_parser("add-url")
    url.add_argument("research_id")
    url.add_argument("url")
    manual = sources.add_parser("import-text")
    manual.add_argument("research_id")
    manual.add_argument("--file", type=Path, required=True)
    for name in ("url", "title", "source-date", "note"):
        manual.add_argument("--" + name)
    manual.add_argument("--initiated-by", default="local-user")
    sources.add_parser("list").add_argument("research_id")
    sources.add_parser("show").add_argument("artifact_id")
    corpora = commands.add_parser("corpus").add_subparsers(dest="action", required=True)
    for name in ("show", "freeze"):
        corpora.add_parser(name).add_argument("research_id")
    for name in ("include", "exclude"):
        command = corpora.add_parser(name)
        command.add_argument("research_id")
        command.add_argument("artifact_id")
    search = corpora.add_parser("search")
    search.add_argument("snapshot_id")
    search.add_argument("query")


def execute(args, service, read_text):
    if args.command == "source":
        if args.action == "add-url":
            return service.add_url(args.research_id, args.url).model_dump(mode="json")
        if args.action == "import-text":
            return service.import_text(
                args.research_id,
                read_text(args.file),
                args.url,
                args.title,
                args.source_date,
                args.initiated_by,
                args.note or "",
            ).model_dump(mode="json")
        if args.action == "list":
            return service.list_sources(args.research_id)
        return service.artifact(args.artifact_id).model_dump(mode="json")
    if args.action == "show":
        return service.corpus(args.research_id)
    if args.action == "freeze":
        return service.freeze(args.research_id).model_dump(mode="json")
    if args.action == "search":
        return service.search(args.snapshot_id, args.query)
    return service.select(args.research_id, args.artifact_id, args.action == "include")
