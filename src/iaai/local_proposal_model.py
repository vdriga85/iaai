"""One offline llama.cpp completion adapter. No shell, tools or cloud fallback."""

import hashlib
import json
import os
import platform
import signal
import subprocess
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from iaai.corpus_domain import digest
from iaai.proposal_domain import ModelIdentity, ModelResponse


@contextmanager
def inference_slot():
    """One local inference across app/CLI processes; OS releases lock after crash."""
    with (Path(tempfile.gettempdir()) / "iaai-proposal-inference.lock").open("a+b") as lock:
        if lock.seek(0, 2) == 0:
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        acquired = False
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except OSError:
            pass
        try:
            yield acquired
        finally:
            if acquired:
                lock.seek(0)
                if os.name == "nt":
                    msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def file_hash(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def process_environment():
    # Do not inherit LLAMA_ARG_RPC/HF/model URLs, credentials or dynamic-loader overrides.
    allowed = ("SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATH", "LANG", "LC_ALL")
    return {key: value for key, value in os.environ.items() if key.upper() in allowed}


def stop_process(process):
    if process.poll() is not None:
        return
    if os.name == "nt":
        killer = Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / "System32/taskkill.exe"
        try:
            subprocess.run(
                [str(killer), "/PID", str(process.pid), "/T", "/F"],
                shell=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except (OSError, subprocess.TimeoutExpired):
            process.kill()
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def bounded_process(args, timeout, stdout_limit, stderr_limit, cwd=None):
    """Drain pipes concurrently; cap memory and terminate on overflow/deadline."""
    started = time.monotonic()
    flags = (
        {"creationflags": subprocess.CREATE_NO_WINDOW}
        if os.name == "nt"
        else {"start_new_session": True}
    )
    try:
        process = subprocess.Popen(
            args,
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            env=process_environment(),
            **flags,
        )
    except OSError:
        return ModelResponse(
            status="MODEL_START_FAILED", duration_seconds=time.monotonic() - started
        )
    buffers = [bytearray(), bytearray()]
    truncated = [False, False]
    overflow = threading.Event()

    def drain(index, pipe, limit):
        try:
            while data := pipe.read1(4096):
                available = max(0, limit - len(buffers[index]))
                buffers[index].extend(data[:available])
                if len(data) > available:
                    truncated[index] = True
                    overflow.set()
        finally:
            pipe.close()

    readers = [
        threading.Thread(target=drain, args=(i, pipe, limit), daemon=True)
        for i, pipe, limit in ((0, process.stdout, stdout_limit), (1, process.stderr, stderr_limit))
    ]
    for reader in readers:
        reader.start()
    status = "OK"
    try:
        while process.poll() is None:
            if overflow.wait(0.02):
                status = "MODEL_OUTPUT_LIMIT"
                break
            if time.monotonic() - started >= timeout:
                status = "MODEL_TIMEOUT"
                break
        if status != "OK":
            stop_process(process)
        process.wait(timeout=5)
    finally:
        stop_process(process)
        for reader in readers:
            reader.join(timeout=5)
    if any(truncated):
        status = "MODEL_OUTPUT_LIMIT"
    if status == "OK" and process.returncode != 0:
        status = "MODEL_PROCESS_FAILED"
    stdout = bytes(buffers[0]).decode("utf-8", errors="replace")
    return ModelResponse(
        status=status,
        stdout=stdout,
        stderr=bytes(buffers[1]).decode("utf-8", errors="replace"),
        exit_code=process.returncode,
        duration_seconds=time.monotonic() - started,
        stdout_hash=digest(stdout),
        stdout_truncated=truncated[0],
        stderr_truncated=truncated[1],
    )


class LocalProposalModel:
    def __init__(self, config_path):
        self.config_path = Path(config_path)
        self._cached = None

    def identity(self):
        if not self.config_path.is_file():
            return ModelIdentity(status="NOT_CONFIGURED")
        try:
            if self.config_path.stat().st_size > 8192:
                return ModelIdentity(status="MODEL_CONFIG_INVALID")
            config = json.loads(self.config_path.read_text("utf-8"))
            if set(config) != {
                "executable",
                "model_path",
                "name",
                "quantization",
                "expected_sha256",
            }:
                return ModelIdentity(status="MODEL_CONFIG_INVALID")
            executable, model = Path(config["executable"]), Path(config["model_path"])
            base = dict(
                name=config["name"],
                executable=str(executable),
                model_path=str(model),
                basename=model.name,
                quantization=config["quantization"],
                model_file_exists=model.is_file(),
                executable_exists=executable.is_file(),
                host_architecture=platform.machine(),
                logical_cpus=os.cpu_count(),
            )
            if not executable.is_absolute() or not model.is_absolute():
                return ModelIdentity(status="MODEL_CONFIG_INVALID", **base)
            if not executable.is_file():
                return ModelIdentity(status="MODEL_RUNTIME_MISSING", **base)
            if not model.is_file() or model.suffix.lower() != ".gguf":
                return ModelIdentity(status="MODEL_FILE_MISSING", **base)
            signature = (
                self.config_path.read_bytes(),
                executable.stat().st_mtime_ns,
                model.stat().st_size,
                model.stat().st_mtime_ns,
            )
            if self._cached and self._cached[0] == signature:
                return self._cached[1]
            model_digest = file_hash(model)
            if model_digest != config["expected_sha256"]:
                return ModelIdentity(status="MODEL_HASH_MISMATCH", **base)
            with model.open("rb") as stream:
                if stream.read(4) != b"GGUF":
                    return ModelIdentity(status="MODEL_CONFIG_INVALID", **base)
            version = bounded_process([str(executable), "--version"], 10, 4096, 4096)
            runtime_version = (version.stdout + version.stderr).strip()
            result = ModelIdentity(
                status="USABLE" if version.status == "OK" else version.status,
                runtime_version=runtime_version,
                executable_hash=file_hash(executable),
                model_hash=model_digest,
                model_size=model.stat().st_size,
                **base,
            )
            self._cached = (signature, result)
            return result
        except (OSError, ValueError, TypeError, KeyError):
            return ModelIdentity(status="MODEL_CONFIG_INVALID")

    @staticmethod
    def command(request, prompt_path, schema_path):
        p = request.policy
        return [
            request.model.executable,
            "--model",
            request.model.model_path,
            "--file",
            str(prompt_path),
            "--json-schema-file",
            str(schema_path),
            "--no-conversation",
            "--no-display-prompt",
            "--simple-io",
            "--no-escape",
            "--offline",
            "--no-context-shift",
            "--no-warmup",
            "--log-verbosity",
            "1",
            "--ctx-size",
            str(p.context_window),
            "--n-predict",
            str(p.max_output_tokens),
            "--threads",
            str(p.threads),
            "--gpu-layers",
            "0",
            "--device",
            "none",
            "--seed",
            str(p.seed),
            "--temp",
            str(p.temperature),
            "--samplers",
            "temperature",
            "--repeat-penalty",
            "1.0",
        ]

    def generate(self, request):
        identity = self.identity()
        if identity.status != "USABLE":
            return ModelResponse(status=identity.status)
        with inference_slot() as acquired:
            if not acquired:
                return ModelResponse(status="MODEL_BUSY")
            return self._generate(request)

    def _generate(self, request):
        identity = self.identity()
        if identity.status != "USABLE":
            return ModelResponse(status=identity.status)
        if identity != request.model:
            return ModelResponse(status="MODEL_IDENTITY_CHANGED")
        # Hash again before inference, even if diagnostics metadata was cached.
        if file_hash(identity.model_path) != identity.model_hash:
            return ModelResponse(status="MODEL_HASH_MISMATCH")
        with tempfile.TemporaryDirectory(prefix="iaai-proposal-") as directory:
            prompt, schema = Path(directory) / "prompt.txt", Path(directory) / "schema.json"
            prompt.write_text(request.prompt, encoding="utf-8")
            schema.write_text(request.output_schema, encoding="utf-8")
            return bounded_process(
                self.command(request, prompt, schema),
                request.policy.timeout_seconds,
                request.policy.stdout_bytes,
                request.policy.stderr_bytes,
                cwd=directory,
            )

    def diagnostics(self):
        return {
            **self.identity().model_dump(mode="json"),
            "host": platform.machine(),
            "cpu_threads": os.cpu_count(),
            "gpu_required": False,
            "compatibility": "runtime --version checked; inference pilot required",
        }
