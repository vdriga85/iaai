import json
import sys

import pytest

from iaai.local_proposal_model import (
    LocalProposalModel,
    bounded_process,
    inference_slot,
    process_environment,
)


def test_process_command_contract(proposal_setup, tmp_path):
    service, _, snap, fake = proposal_setup
    service.proposals.run(snap.snapshot_id, "battery")
    request = fake.requests[0]
    args = LocalProposalModel.command(request, tmp_path / "prompt.txt", tmp_path / "schema.json")
    assert "--offline" in args and "--no-conversation" in args
    assert "--json-schema-file" in args
    assert "--gpu-layers" in args and args[args.index("--gpu-layers") + 1] == "0"
    assert request.question not in args
    assert not any("Delete the database" in arg for arg in args)


def test_bounded_process_success_nonzero_timeout():
    result = bounded_process([sys.executable, "-c", "print('hello')"], 5, 1024, 1024)
    assert result.status == "OK" and result.stdout.strip() == "hello"
    result = bounded_process([sys.executable, "-c", "import sys; sys.exit(7)"], 5, 1024, 1024)
    assert result.status == "MODEL_PROCESS_FAILED" and result.exit_code == 7
    result = bounded_process([sys.executable, "-c", "import time; time.sleep(20)"], 0.1, 1024, 1024)
    assert result.status == "MODEL_TIMEOUT" and result.duration_seconds < 10


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
def test_output_ceiling(stream):
    result = bounded_process(
        [sys.executable, "-c", f"import sys; sys.{stream}.write('x'*1000000)"], 5, 1024, 1024
    )
    assert result.status == "MODEL_OUTPUT_LIMIT"
    assert len(result.stdout) <= 1024 and len(result.stderr) <= 1024
    assert getattr(result, stream + "_truncated")


def test_no_shell_and_minimal_environment(monkeypatch):
    import iaai.local_proposal_model as runtime

    actual = runtime.subprocess.Popen
    calls = []

    def observed(*args, **kwargs):
        calls.append(kwargs)
        return actual(*args, **kwargs)

    monkeypatch.setattr(runtime.subprocess, "Popen", observed)
    monkeypatch.setenv("LLAMA_ARG_RPC", "host:1234")
    monkeypatch.setenv("HF_TOKEN", "do-not-inherit")
    bounded_process([sys.executable, "-c", "pass"], 5, 1024, 1024)
    assert calls[0]["shell"] is False
    assert "LLAMA_ARG_RPC" not in process_environment()
    assert "HF_TOKEN" not in calls[0]["env"]


def test_missing_and_invalid_configuration(tmp_path):
    config = tmp_path / "config.json"
    model = LocalProposalModel(config)
    assert model.identity().status == "NOT_CONFIGURED"
    config.write_text("not json", encoding="utf-8")
    assert model.identity().status == "MODEL_CONFIG_INVALID"
    value = {
        "executable": str(tmp_path / "missing.exe"),
        "model_path": str(tmp_path / "missing.gguf"),
        "name": "fixture",
        "quantization": "UNKNOWN",
        "expected_sha256": "0" * 64,
    }
    config.write_text(json.dumps(value), encoding="utf-8")
    assert model.identity().status == "MODEL_RUNTIME_MISSING"
    value["executable"] = sys.executable
    config.write_text(json.dumps(value), encoding="utf-8")
    assert model.identity().status == "MODEL_FILE_MISSING"
    value["executable"] = "relative.exe"
    config.write_text(json.dumps(value), encoding="utf-8")
    assert model.identity().status == "MODEL_CONFIG_INVALID"


def test_single_inference_slot(monkeypatch, tmp_path):
    import iaai.local_proposal_model as runtime

    monkeypatch.setattr(runtime.tempfile, "gettempdir", lambda: str(tmp_path))
    with inference_slot() as first:
        assert first
        with inference_slot() as second:
            assert not second
    with inference_slot() as third:
        assert third
