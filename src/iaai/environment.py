"""Best-effort metadata; missing Git/hardware is explicit, never fabricated."""

import ctypes
import importlib.metadata
import os
import platform
import shutil
import subprocess
from pathlib import Path

from iaai.domain import DependencyVersion, RuntimeMetadata


def physical_memory() -> int | None:
    try:
        if os.name == "nt":

            class MemoryStatus(ctypes.Structure):
                _fields_ = [
                    ("length", ctypes.c_ulong),
                    ("load", ctypes.c_ulong),
                    *[
                        (name, ctypes.c_ulonglong)
                        for name in (
                            "total",
                            "available",
                            "page_total",
                            "page_available",
                            "virtual_total",
                            "virtual_available",
                            "extended",
                        )
                    ],
                ]

            status = MemoryStatus()
            status.length = ctypes.sizeof(status)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return status.total
        elif hasattr(os, "sysconf"):
            return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (AttributeError, OSError, ValueError):
        pass
    return None


def capture_runtime(repository: Path) -> RuntimeMetadata:
    commit, dirty = None, None
    try:

        def git(*args):
            return subprocess.run(
                ["git", "-C", str(repository), *args],
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            ).stdout.strip()

        commit = git("rev-parse", "HEAD")
        dirty = bool(git("status", "--porcelain", "--untracked-files=normal"))
    except (OSError, subprocess.SubprocessError):
        commit, dirty = None, None
    dependencies = tuple(
        sorted(
            (
                DependencyVersion(name=dist.metadata.get("Name", "unknown"), version=dist.version)
                for dist in importlib.metadata.distributions()
            ),
            key=lambda item: (item.name, item.version),
        )
    )
    return RuntimeMetadata(
        git_commit=commit,
        git_dirty=dirty,
        git_status="AVAILABLE" if commit else "UNAVAILABLE",
        python_version=platform.python_version(),
        python_implementation=platform.python_implementation(),
        dependencies=dependencies,
        os=platform.platform(),
        machine=platform.machine() or "unknown",
        processor=platform.processor() or None,
        logical_cpu_count=os.cpu_count(),
        physical_memory_bytes=physical_memory(),
    )


def system_diagnostics(database: Path, repository: Path) -> dict:
    parent = database.resolve().parent
    existing = parent
    while not existing.exists() and existing != existing.parent:
        existing = existing.parent
    try:
        free = shutil.disk_usage(existing).free
    except OSError:
        free = None
    return {
        "runtime_directory": str(parent),
        "runtime_directory_exists": parent.is_dir(),
        "free_disk_bytes": free,
        "runtime": capture_runtime(repository).model_dump(mode="json"),
    }
