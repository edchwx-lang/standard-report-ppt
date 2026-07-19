from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Callable


def detect_renderer() -> str | None:
    if Path("/Applications/Microsoft PowerPoint.app").exists():
        return "powerpoint_mac"
    if shutil.which("soffice"):
        return "libreoffice"
    return None


def _powerpoint_pdf(pptx: Path, pdf: Path, timeout: int) -> None:
    script = """
on run argv
  set inputPath to item 1 of argv
  set outputPath to item 2 of argv
  tell application "Microsoft PowerPoint"
    set deck to open POSIX file inputPath
    save deck in POSIX file outputPath as save as PDF
    close deck saving no
  end tell
end run
"""
    subprocess.run(
        ["osascript", "-e", script, str(pptx), str(pdf)],
        check=True,
        timeout=timeout,
        capture_output=True,
        text=True,
    )


def _libreoffice_pdf(pptx: Path, output_dir: Path, timeout: int) -> Path:
    subprocess.run(
        [
            "soffice", "--headless", "--convert-to", "pdf",
            "--outdir", str(output_dir), str(pptx),
        ],
        check=True,
        timeout=timeout,
        capture_output=True,
        text=True,
    )
    pdf = output_dir / f"{pptx.stem}.pdf"
    if not pdf.is_file():
        raise RuntimeError("LibreOffice did not create a PDF")
    return pdf


def rasterize_pdf(pdf: Path, output_dir: Path) -> list[Path]:
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument(str(pdf))
    outputs: list[Path] = []
    try:
        for index in range(len(document)):
            bitmap = document[index].render(scale=1600 / 960)
            image = bitmap.to_pil()
            destination = output_dir / f"S{index + 1:02d}.png"
            image.save(destination)
            outputs.append(destination)
    finally:
        document.close()
    return outputs


def render_project(
    pptx_path: str | Path,
    project_dir: str | Path,
    *,
    expected_page_count: int,
    timeout_seconds: int = 90,
    detector: Callable[[], str | None] = detect_renderer,
) -> dict:
    pptx = Path(pptx_path).resolve()
    project = Path(project_dir).resolve()
    if not pptx.is_file():
        raise FileNotFoundError(pptx)
    output_dir = project / ".build" / "rendered" / "current"
    output_dir.mkdir(parents=True, exist_ok=True)
    for stale in output_dir.glob("S*.png"):
        stale.unlink()
    renderer = detector()
    if renderer is None:
        return {
            "ok": True,
            "renderer": None,
            "visual_verification": False,
            "images": [],
            "status": "structurally_valid_unrendered",
        }
    if renderer not in {"powerpoint_mac", "libreoffice"}:
        raise ValueError(f"unsupported local renderer: {renderer}")
    pdf = project / ".build" / "rendered" / f"{pptx.stem}.pdf"
    if pdf.is_file():
        pdf.unlink()
    try:
        if renderer == "powerpoint_mac":
            _powerpoint_pdf(pptx, pdf, timeout_seconds)
        else:
            pdf = _libreoffice_pdf(pptx, pdf.parent, timeout_seconds)
        images = rasterize_pdf(pdf, output_dir)
    except (OSError, RuntimeError, subprocess.SubprocessError, ImportError) as exc:
        return {
            "ok": True,
            "renderer": renderer,
            "visual_verification": False,
            "images": [],
            "status": "structurally_valid_unrendered",
            "warning": str(exc),
        }
    if len(images) != expected_page_count:
        return {
            "ok": False,
            "renderer": renderer,
            "visual_verification": False,
            "images": [path.name for path in images],
            "status": "blocked",
            "warning": (
                f"expected {expected_page_count} renders, got {len(images)}"
            ),
        }
    return {
        "ok": True,
        "renderer": renderer,
        "visual_verification": True,
        "images": [path.name for path in images],
        "status": "pass" if renderer == "powerpoint_mac" else "pass_with_warnings",
    }
