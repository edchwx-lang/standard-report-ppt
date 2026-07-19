from __future__ import annotations

import argparse
import importlib
import json
import os
import platform
import site
import subprocess
import sys
from pathlib import Path
from typing import Callable


PYWIN32_VERSION = "312"
_DLL_DIRECTORY_HANDLES: list[object] = []


def activate_pywin32_runtime(site_packages: str | Path | None = None) -> list[str]:
    """Expose pywin32's non-package runtime directories to the current process."""

    pywin32_roots = {"pythoncom", "pywintypes", "win32api", "win32com"}
    for name, module in list(sys.modules.items()):
        root = name.split(".", 1)[0]
        if root in pywin32_roots and module is None:
            sys.modules.pop(name, None)

    if site_packages is not None:
        roots = [Path(site_packages)]
    else:
        roots = [Path(path) for path in site.getsitepackages()]
        user_site = site.getusersitepackages()
        if isinstance(user_site, str):
            roots.append(Path(user_site))

    activated: list[str] = []
    seen: set[str] = set()
    for root in roots:
        for runtime_path in (
            root / "win32",
            root / "win32" / "lib",
            root / "pythonwin",
            root / "pywin32_system32",
        ):
            if not runtime_path.is_dir():
                continue
            resolved = str(runtime_path.resolve())
            normalized = os.path.normcase(resolved)
            if normalized in seen:
                continue
            seen.add(normalized)
            if all(os.path.normcase(str(Path(path).resolve())) != normalized for path in sys.path if path):
                sys.path.insert(0, resolved)
            activated.append(resolved)
            if runtime_path.name == "pywin32_system32" and hasattr(os, "add_dll_directory"):
                try:
                    _DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(resolved))
                except OSError:
                    pass
    return activated


def expected_wheel_name() -> str:
    tag = f"cp{sys.version_info.major}{sys.version_info.minor}"
    machine = platform.machine().lower()
    architecture = "win_amd64" if machine in {"amd64", "x86_64"} else "win32"
    return f"pywin32-{PYWIN32_VERSION}-{tag}-{tag}-{architecture}.whl"


def _import_pywin32() -> dict[str, str]:
    modules = {}
    for name in ("win32com.client", "pythoncom", "pywintypes"):
        module = importlib.import_module(name)
        modules[name.split(".")[0]] = str(getattr(module, "__file__", "built-in"))
    return modules


def _install(command: list[str]) -> None:
    subprocess.run(command, check=True, timeout=180)


def _probe_com() -> None:
    pythoncom = importlib.import_module("pythoncom")
    pythoncom.CoInitialize()
    pythoncom.CoUninitialize()


def ensure_windows_runtime(
    *,
    importer: Callable[[], dict[str, str]] = _import_pywin32,
    installer: Callable[[list[str]], None] = _install,
    wheel_dir: str | Path | None = None,
    project_dir: str | Path | None = None,
    probe_com: bool = True,
) -> dict:
    installed = False
    install_source = "existing"
    try:
        modules = importer()
    except (ImportError, ModuleNotFoundError):
        root = Path(__file__).resolve().parents[1]
        wheels = Path(wheel_dir) if wheel_dir is not None else root / "assets" / "wheels"
        wheel = wheels / expected_wheel_name()
        if wheel.is_file():
            command = [sys.executable, "-m", "pip", "install", "--no-index", "--force-reinstall", str(wheel)]
            install_source = "offline_wheel"
        else:
            command = [sys.executable, "-m", "pip", "install", f"pywin32=={PYWIN32_VERSION}"]
            install_source = "locked_network_fallback"
        installer(command)
        installed = True
        importlib.invalidate_caches()
        activate_pywin32_runtime()
        modules = importer()
    if probe_com:
        _probe_com()
    result = {
        "schema_version": "5.8",
        "ok": True,
        "installed": installed,
        "install_source": install_source,
        "python": sys.executable,
        "python_version": platform.python_version(),
        "wheel": expected_wheel_name(),
        "modules": modules,
        "com_probe": bool(probe_com),
    }
    if project_dir is not None:
        destination = Path(project_dir) / ".build" / "windows_runtime_report.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Ensure the Windows PowerPoint Python runtime is ready.")
    parser.add_argument("--project", type=Path)
    parser.add_argument("--no-com-probe", action="store_true")
    args = parser.parse_args()
    print(json.dumps(ensure_windows_runtime(project_dir=args.project, probe_com=not args.no_com_probe), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
