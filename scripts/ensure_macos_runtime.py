from __future__ import annotations

import importlib
import importlib.metadata
import json
import sys
from pathlib import Path
from typing import Callable


REQUIRED = ("pptx", "PIL", "lxml", "xlsxwriter", "fontTools")


def _imports() -> dict[str, str | None]:
    distributions = {
        "pptx": "python-pptx", "PIL": "Pillow", "lxml": "lxml",
        "xlsxwriter": "XlsxWriter", "fontTools": "fonttools",
    }
    result: dict[str, str | None] = {}
    for module_name, distribution in distributions.items():
        try:
            importlib.import_module(module_name)
            result[module_name] = importlib.metadata.version(distribution)
        except (ImportError, importlib.metadata.PackageNotFoundError):
            result[module_name] = None
    return result


def ensure_macos_runtime(
    *,
    project_dir: str | Path | None = None,
    importer: Callable[[], dict[str, str | None]] = _imports,
    wheel_path: str | Path | None = None,
) -> dict:
    skill = Path(__file__).resolve().parents[1]
    wheel = Path(wheel_path) if wheel_path else skill / "assets" / "vendor" / "fonttools-4.63.0-py3.zip"
    modules = importer()
    fonttools_source = "existing"
    if modules.get("fontTools") is None and wheel.is_file():
        sys.path.insert(0, str(wheel))
        importlib.invalidate_caches()
        modules = importer()
        fonttools_source = "vendored_wheel"
    missing = [name for name in REQUIRED if modules.get(name) is None]
    if missing:
        raise RuntimeError(
            "missing macOS runtime dependencies: " + ", ".join(missing)
            + "; V5.9 does not install packages from the network at runtime"
        )
    payload = {
        "schema_version": "5.9", "ok": True, "python": sys.executable,
        "modules": modules, "fonttools_source": fonttools_source,
    }
    if project_dir is not None:
        destination = Path(project_dir).resolve() / ".build" / "macos_runtime_report.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload
