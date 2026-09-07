import json
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

import pytest

from iaai.application import ResearchService
from iaai.bootstrap import build_service
from iaai.errors import IAAIError


def test_concurrent_creations(tmp_path, protocol):
    path = tmp_path / "concurrent.db"

    def create(_):
        return build_service(path, tmp_path).create(json.dumps(protocol))

    with ThreadPoolExecutor(max_workers=2) as executor:
        bundles = list(executor.map(create, range(2)))
    assert len(build_service(path, tmp_path).list_researches()) == 2
    assert bundles[0].manifest.run_id != bundles[1].manifest.run_id


def test_stale_revision_rolls_back(service, protocol, policy):
    first = service.create(json.dumps(protocol))
    protocol["version"] = 2
    protocol["geography"] = "Germany"
    service.revise(first.research.research_id, json.dumps(protocol), json.dumps(policy))

    class StaleStore:
        def load(self, research_id):
            return first

        def save(self, bundle, expected_revision):
            service.store.save(bundle, expected_revision)

    stale = ResearchService(
        StaleStore(), service.default_policy, service.capture_runtime, service.system_diagnostics
    )
    with pytest.raises(IAAIError) as failure:
        stale.revise(first.research.research_id, json.dumps(protocol), json.dumps(policy))
    assert failure.value.code == "REVISION_CONFLICT"
    assert service.get(first.research.research_id).revision.revision == 2


def test_custom_busy_timeout_applied(service, protocol, policy, monkeypatch):
    policy["runtime"]["sqlite_busy_timeout_seconds"] = 2
    connect = service.store.connection
    observed = []

    @contextmanager
    def spy(timeout=None):
        with connect(timeout) as connection:
            observed.append(connection.execute("PRAGMA busy_timeout").fetchone()[0])
            yield connection

    monkeypatch.setattr(service.store, "connection", spy)
    service.create(json.dumps(protocol), json.dumps(policy))
    assert observed == [2000]
