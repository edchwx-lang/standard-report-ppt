from __future__ import annotations

import json
import platform
from pathlib import Path
from typing import NamedTuple


class RuntimeSelection(NamedTuple):
    os_name: str
    machine: str
    backend: str | None
    supported: bool
    reason: str | None = None


def select_backend(system_name: str | None = None, machine: str | None = None) -> RuntimeSelection:
    os_name = system_name or platform.system()
    architecture = machine or platform.machine()
    if os_name == "Windows":
        return RuntimeSelection(os_name, architecture, "windows_com_v584", True)
    if os_name == "Darwin":
        return RuntimeSelection(os_name, architecture, "mac_python_pptx_v1", True)
    return RuntimeSelection(
        os_name,
        architecture,
        None,
        False,
        f"{os_name} is unsupported by Standard Report PPT V5.9",
    )


def require_supported_backend(selection: RuntimeSelection) -> RuntimeSelection:
    if not selection.supported or selection.backend is None:
        raise RuntimeError(selection.reason or "unsupported operating system")
    return selection


def write_runtime_report(project_dir: str | Path, selection: RuntimeSelection) -> dict:
    project = Path(project_dir).resolve()
    payload = {
        "schema_version": "5.9",
        **selection._asdict(),
        "builder_backend": selection.backend,
    }
    destination = project / ".build" / "runtime_report.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(destination)
    return payload
