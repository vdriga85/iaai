"""Use cases shared by CLI and web. No infrastructure imports."""

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from pydantic import ValidationError

from iaai.domain import (
    Research,
    ResearchPolicy,
    ResearchProtocol,
    ResearchRevision,
    RevisionBundle,
    RunManifest,
    RuntimeMetadata,
)
from iaai.errors import IAAIError
from iaai.ports import ResearchStore
from iaai.simple_input import SimpleIdeaInput, build_protocol

logger = logging.getLogger(__name__)


def parse_protocol(raw: str) -> ResearchProtocol:
    try:
        return ResearchProtocol.model_validate_json(raw)
    except ValidationError as exc:
        raise validation_error(exc) from exc


def parse_policy(raw: str) -> ResearchPolicy:
    try:
        return ResearchPolicy.model_validate_json(raw)
    except ValidationError as exc:
        raise validation_error(exc) from exc


def validation_error(exc: ValidationError) -> IAAIError:
    # Do not log user ideas, values or entire validation input.
    issues = [
        f"{'.'.join(map(str, e['loc'])) or 'input'}: {e['msg']}"
        for e in exc.errors(include_input=False, include_url=False)[:10]
    ]
    return IAAIError("VALIDATION_ERROR", "; ".join(issues))


class ResearchService:
    def __init__(
        self,
        store: ResearchStore,
        default_policy: ResearchPolicy,
        capture_runtime: Callable[[], RuntimeMetadata],
        system_diagnostics: Callable[[], dict],
        corpus=None,
    ):
        self.store = store
        self.default_policy = default_policy
        self.capture_runtime = capture_runtime
        self.system_diagnostics = system_diagnostics
        self.corpus = corpus
        self.proposals = None

    def create(self, protocol_json: str, policy_json: str | None = None) -> RevisionBundle:
        protocol = parse_protocol(protocol_json)
        policy = parse_policy(policy_json) if policy_json is not None else self.default_policy
        now = datetime.now(UTC)
        research = Research(
            research_id=str(uuid4()),
            original_idea=protocol.original_idea,
            status="CREATED",
            current_revision=1,
            created_at=now,
        )
        return self._save(research, protocol, policy, 0)

    def create_simple(self, input_json: str) -> RevisionBundle:
        try:
            build = build_protocol(SimpleIdeaInput.model_validate_json(input_json))
        except ValidationError as exc:
            raise validation_error(exc) from exc
        research = Research(
            research_id=str(uuid4()),
            original_idea=build.input.idea,
            status="CREATED",
            current_revision=1,
            created_at=datetime.now(UTC),
        )
        return self._save(research, build.protocol, self.default_policy, 0, build)

    def input_build(self, research_id, revision=1):
        return self.store.input_build(research_id, revision)

    def revise(self, research_id: str, protocol_json: str, policy_json: str) -> RevisionBundle:
        protocol, policy = parse_protocol(protocol_json), parse_policy(policy_json)
        previous = self.store.load(research_id)
        if (
            protocol.content_hash == previous.protocol.content_hash
            and policy.content_hash == previous.policy.content_hash
        ):
            raise IAAIError("UNCHANGED_REVISION", "Protocol and policy have not changed")
        if (
            protocol.content_hash != previous.protocol.content_hash
            and protocol.protocol_id == previous.protocol.protocol_id
            and protocol.version <= previous.protocol.version
        ):
            raise IAAIError("VERSION_CONFLICT", "Changed protocol requires a higher version")
        if policy.content_hash != previous.policy.content_hash:
            if policy.parent_policy_hash != previous.policy.content_hash:
                raise IAAIError("VERSION_CONFLICT", "Changed policy must reference its parent hash")
            if (
                policy.policy_id == previous.policy.policy_id
                and policy.version <= previous.policy.version
            ):
                raise IAAIError("VERSION_CONFLICT", "Changed policy requires a higher version")
        research = Research(
            research_id=research_id,
            original_idea=protocol.original_idea,
            status="CREATED",
            current_revision=previous.research.current_revision + 1,
            created_at=previous.research.created_at,
        )
        return self._save(research, protocol, policy, previous.research.current_revision)

    def _save(
        self,
        research: Research,
        protocol: ResearchProtocol,
        policy: ResearchPolicy,
        expected_revision: int,
        input_build=None,
    ) -> RevisionBundle:
        now, run_id = datetime.now(UTC), str(uuid4())
        revision = ResearchRevision(
            research_id=research.research_id,
            revision=research.current_revision,
            protocol_hash=protocol.content_hash,
            policy_hash=policy.content_hash,
            run_id=run_id,
            created_at=now,
        )
        manifest = RunManifest(
            schema_version="0.1", runtime=self.capture_runtime(), **revision.model_dump()
        )
        bundle = RevisionBundle(
            research=research,
            revision=revision,
            protocol=protocol,
            policy=policy,
            manifest=manifest,
        )
        if input_build is None:
            self.store.save(bundle, expected_revision)
        else:
            self.store.save(bundle, expected_revision, input_build=input_build)
        logger.info(
            "revision_saved operation_id=%s run_id=%s revision=%d",
            run_id,
            run_id,
            revision.revision,
        )
        return bundle

    def list_researches(self) -> tuple[Research, ...]:
        return self.store.list_researches()

    def get(self, research_id: str, revision: int | None = None) -> RevisionBundle:
        return self.store.load(research_id, revision)

    def get_manifest(self, run_id: str) -> RunManifest:
        return self.store.manifest(run_id)

    def doctor(self) -> dict:
        result = self.system_diagnostics()
        try:
            result["database"] = self.store.diagnostics()
            result["ok"] = True
        except IAAIError as exc:
            result["database"] = {"status": "ERROR", **exc.as_dict()}
            result["ok"] = False
        result["policy_hash"] = self.default_policy.content_hash
        result["policy_status"] = self.default_policy.status
        if self.corpus is not None:
            try:
                result["corpus"] = self.corpus.diagnostics()
            except IAAIError as exc:
                result["corpus"] = {"error": exc.as_dict()}
                result["ok"] = False
        if self.proposals is not None:
            try:
                result["proposal_model"] = self.proposals.diagnostics()
            except IAAIError as exc:
                result["proposal_model"] = {"status": "DIAGNOSTIC_ERROR", "error": exc.as_dict()}
        return result
