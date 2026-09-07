"""Small argparse adapter; JSON files use the same schema as the UI."""

import argparse
import json
import logging
from pathlib import Path

from iaai.application import ResearchService
from iaai.bootstrap import build_service
from iaai.corpus_cli import add_commands, execute
from iaai.errors import IAAIError


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="iaai", description="IAAI experimental session foundation")
    root.add_argument("--db", type=Path, help="SQLite path (default: ./runtime/iaai.db)")
    commands = root.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="Local UI; always binds 127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    commands.add_parser("doctor")
    research = commands.add_parser("research").add_subparsers(dest="action", required=True)
    research.add_parser("list")
    show = research.add_parser("show")
    show.add_argument("id")
    show.add_argument("--revision", type=int)
    for name in ("create", "revise"):
        command = research.add_parser(name)
        if name == "revise":
            command.add_argument("id")
        command.add_argument("--protocol", type=Path, required=True)
        command.add_argument("--policy", type=Path, required=name == "revise")
    manifest = commands.add_parser("manifest").add_subparsers(dest="action", required=True)
    manifest.add_parser("show").add_argument("id")
    add_commands(commands)
    return root


def read_json(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise IAAIError("INPUT_FILE", f"Cannot read UTF-8 input file: {path}") from exc


def main(argv: list[str] | None = None, service: ResearchService | None = None) -> int:
    args = parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        service = service or build_service(args.db)
        if args.command == "serve":
            if not 1 <= args.port <= 65535:
                raise IAAIError("CONFIG_ERROR", "Port must be between 1 and 65535")
            from iaai.web import create_app

            print(f"IAAI: http://127.0.0.1:{args.port} (experimental foundation, no analysis)")
            create_app(service).run(
                host="127.0.0.1", port=args.port, debug=False, use_reloader=False
            )
            return 0
        if args.command in ("source", "corpus"):
            result = execute(args, service.corpus, read_json)
        elif args.command == "doctor":
            result = service.doctor()
        elif args.command == "manifest":
            result = service.get_manifest(args.id).model_dump(mode="json")
        elif args.action == "list":
            result = [item.model_dump(mode="json") for item in service.list_researches()]
        elif args.action == "show":
            result = service.get(args.id, args.revision).model_dump(mode="json")
        else:
            protocol = read_json(args.protocol)
            policy = read_json(args.policy) if args.policy else None
            bundle = (
                service.create(protocol, policy)
                if args.action == "create"
                else service.revise(args.id, protocol, policy)
            )
            result = bundle.model_dump(mode="json")
        print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
        return 1 if args.command == "doctor" and not result["ok"] else 0
    except IAAIError as exc:
        print(json.dumps({"error": exc.as_dict()}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
