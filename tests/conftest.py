import json
from pathlib import Path

import pytest

from iaai.bootstrap import build_service


@pytest.fixture
def protocol():
    return json.loads((Path(__file__).parents[1] / "examples/protocol.json").read_text("utf-8"))


@pytest.fixture
def service(tmp_path):
    return build_service(tmp_path / "runtime" / "test.db", tmp_path)


@pytest.fixture
def policy(service):
    return service.default_policy.model_dump(mode="json")
