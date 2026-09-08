"""Proposal CLI uses the same application service as the Russian UI."""

from iaai.domain import Snapshot


def serializable(value):
    if isinstance(value, Snapshot):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {key: serializable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [serializable(item) for item in value]
    return value


def add_proposal_commands(commands):
    commands.add_parser("model").add_subparsers(dest="action", required=True).add_parser("doctor")
    proposals = commands.add_parser("proposal").add_subparsers(dest="action", required=True)
    run = proposals.add_parser("run")
    run.add_argument("snapshot_id")
    run.add_argument("--question", required=True)
    proposals.add_parser("show").add_argument("operation_id")
    proposals.add_parser("queue").add_argument("research_id")
    for name in ("accept", "reject", "edit-accept"):
        command = proposals.add_parser(name)
        command.add_argument("candidate_id")
        command.add_argument("--reviewer", default="local-user")
        command.add_argument("--comment", default="")
        command.add_argument("--reason")
        if name == "edit-accept":
            command.add_argument("--text", required=True)


def execute_proposal(args, service):
    if args.command == "model":
        return service.diagnostics()
    if args.action == "run":
        return service.run(args.snapshot_id, args.question)
    if args.action == "show":
        return service.show(args.operation_id)
    if args.action == "queue":
        return service.queue(args.research_id)
    actions = {"accept": "ACCEPTED", "reject": "REJECTED", "edit-accept": "EDITED_ACCEPTED"}
    return service.review(
        args.candidate_id,
        actions[args.action],
        args.reviewer,
        edited_text=getattr(args, "text", None),
        reason_code=args.reason,
        comment=args.comment,
    )
