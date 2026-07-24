from __future__ import annotations

from copy import deepcopy
from typing import Any


SCHEMA_VERSION = "6.0"
PIPELINE_REVISION = "6.0.0"
PRODUCTION_MODE = "blueprint"
BLUEPRINT_ENGINE = "builtin_imagegen"
PLATFORM_TARGET = "auto"

CONSTRUCTION_MODE_DECONSTRUCT = "deconstruct"
CONSTRUCTION_MODE_BITMAP = "bitmap"
CONSTRUCTION_MODES = frozenset(
    {CONSTRUCTION_MODE_DECONSTRUCT, CONSTRUCTION_MODE_BITMAP}
)

DECONSTRUCT_RUNTIME_PAGE_SPECS_PATH = ".build/page_specs.json"
BITMAP_RUNTIME_PAGE_SPECS_PATH = ".build/bitmap_page_specs.json"

ERROR_SCHEMA_VERSION = "V6_SCHEMA_VERSION_INVALID"
ERROR_PIPELINE_REVISION = "V6_PIPELINE_REVISION_INVALID"
ERROR_PRODUCTION_MODE = "V6_PRODUCTION_MODE_INVALID"
ERROR_CONSTRUCTION_MODE_REQUIRED = "V6_CONSTRUCTION_MODE_REQUIRED"
ERROR_BLUEPRINT_ENGINE = "V6_BLUEPRINT_ENGINE_INVALID"
ERROR_PLATFORM_TARGET = "V6_PLATFORM_TARGET_INVALID"

_UPSTREAM_EXCLUDED_FIELDS = frozenset(
    {
        "construction_mode",
        "platform_target",
        "backend",
        "builder_backend",
        "runtime_backend",
    }
)


def is_v6(brief: dict[str, Any]) -> bool:
    """Return whether *brief* declares the V6 contract version."""
    return (
        isinstance(brief, dict)
        and brief.get("schema_version") == SCHEMA_VERSION
        and brief.get("pipeline_revision") == PIPELINE_REVISION
    )


def construction_mode(brief: dict[str, Any]) -> str | None:
    """Return the explicit valid construction mode, never a default."""
    if not isinstance(brief, dict):
        return None
    value = brief.get("construction_mode")
    return value if value in CONSTRUCTION_MODES else None


def validate_v6_brief(brief: dict[str, Any]) -> list[str]:
    """Validate the fields fixed by the V6 blueprint contract."""
    if not isinstance(brief, dict):
        return [
            ERROR_SCHEMA_VERSION,
            ERROR_PIPELINE_REVISION,
            ERROR_PRODUCTION_MODE,
            ERROR_CONSTRUCTION_MODE_REQUIRED,
            ERROR_BLUEPRINT_ENGINE,
            ERROR_PLATFORM_TARGET,
        ]

    errors: list[str] = []
    if brief.get("schema_version") != SCHEMA_VERSION:
        errors.append(ERROR_SCHEMA_VERSION)
    if brief.get("pipeline_revision") != PIPELINE_REVISION:
        errors.append(ERROR_PIPELINE_REVISION)
    if brief.get("production_mode") != PRODUCTION_MODE:
        errors.append(ERROR_PRODUCTION_MODE)
    if construction_mode(brief) is None:
        errors.append(ERROR_CONSTRUCTION_MODE_REQUIRED)
    if brief.get("blueprint_engine") != BLUEPRINT_ENGINE:
        errors.append(ERROR_BLUEPRINT_ENGINE)
    if brief.get("platform_target") != PLATFORM_TARGET:
        errors.append(ERROR_PLATFORM_TARGET)
    return errors


def upstream_cache_payload(brief: dict[str, Any]) -> dict[str, Any]:
    """Keep shared content/ImageGen inputs while removing runtime choices."""
    if not isinstance(brief, dict):
        raise TypeError("brief must be a mapping")
    return {
        key: deepcopy(value)
        for key, value in brief.items()
        if key not in _UPSTREAM_EXCLUDED_FIELDS
    }


def post_lock_cache_payload(brief: dict[str, Any], backend: str) -> dict[str, Any]:
    """Bind post-lock work to the selected construction mode and backend."""
    mode = construction_mode(brief)
    if mode is None:
        raise ValueError(ERROR_CONSTRUCTION_MODE_REQUIRED)
    if not isinstance(backend, str) or not backend:
        raise ValueError("V6_BACKEND_REQUIRED")
    payload = upstream_cache_payload(brief)
    payload["construction_mode"] = mode
    payload["backend"] = backend
    return payload


def runtime_page_specs_path(brief: dict[str, Any]) -> str:
    """Select the only runtime page-spec artifact for a valid V6 mode."""
    mode = construction_mode(brief)
    if mode == CONSTRUCTION_MODE_DECONSTRUCT:
        return DECONSTRUCT_RUNTIME_PAGE_SPECS_PATH
    if mode == CONSTRUCTION_MODE_BITMAP:
        return BITMAP_RUNTIME_PAGE_SPECS_PATH
    raise ValueError(ERROR_CONSTRUCTION_MODE_REQUIRED)


# Singular spelling is retained for callers that describe one selected path.
runtime_page_spec_path = runtime_page_specs_path
