from __future__ import annotations

import hashlib
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile


PRESENTATION_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_template(path: str | Path) -> dict:
    path = Path(path).resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    with ZipFile(path) as archive:
        presentation = ElementTree.fromstring(archive.read("ppt/presentation.xml"))
        slide_size = presentation.find(f".//{{{PRESENTATION_NS}}}sldSz")
        if slide_size is None:
            raise ValueError("template presentation.xml is missing p:sldSz")
        width = int(slide_size.attrib["cx"])
        height = int(slide_size.attrib["cy"])
        guide_count = 0
        if "ppt/viewProps.xml" in archive.namelist():
            view_props = ElementTree.fromstring(archive.read("ppt/viewProps.xml"))
            guide_count = len(view_props.findall(f".//{{{PRESENTATION_NS}}}guide"))
    return {
        "schema_version": "5.8",
        "path": str(path),
        "sha256": sha256_file(path),
        "slide_width_emu": width,
        "slide_height_emu": height,
        "aspect_ratio": width / height,
        "guide_count": guide_count,
        "geometry_source": "slide_size_and_v58_internal_safe_area",
        "guides_consumed_for_geometry": False,
    }
