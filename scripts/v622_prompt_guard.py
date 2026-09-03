from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "6.2.2"
AGENT_VISUAL_BAN = "V622_AGENT_VISUAL_BAN"
EDITABILITY_OVERRIDE = "V622_EDITABILITY_VISUAL_OVERRIDE"

_SUBJECTS_ZH = r"图标|照片|图片|人物|人像|地图|logo|标志|插画|设备|产品|建筑|园区实景"
_NEGATIVE_ZH = re.compile(
    rf"(?:无|不要|不得|禁止|禁用|避免|不使用|不可使用|不含|去除)(?:任何|所有)?(?:{_SUBJECTS_ZH})",
    re.IGNORECASE,
)
_COMPACT_NEGATIVE_ZH = re.compile(
    r"无(?:图标|照片|人物|地图|logo){2,}", re.IGNORECASE
)
_NEGATIVE_EN = re.compile(
    r"\b(?:no|without)\s+(?:icons?|photos?|pictures?|people|persons?|maps?|logos?|illustrations?|devices?|products?|buildings?)\b"
    r"|\bdo\s+not\s+(?:use|include|add)\s+(?:any\s+)?(?:icons?|photos?|pictures?|people|persons?|maps?|logos?|illustrations?|devices?|products?|buildings?)\b",
    re.IGNORECASE,
)
_EDITABILITY_OVERRIDE = re.compile(
    r"(?:全部|所有|仅|只)(?:使用|采用|用)?.{0,12}(?:可编辑)?(?:矩形|基础几何|原生对象)"
    r"|(?:为了|为)(?:便于|方便).{0,12}(?:解构|重建).{0,24}(?:禁止|不使用|不要|仅使用|只使用)",
    re.IGNORECASE,
)


def _blocker(code: str, message: str) -> dict[str, str]:
    return {"code": code, "severity": "blocker", "message": message}


def validate_prompt(prompt: str) -> dict[str, Any]:
    text = str(prompt or "")
    compact = re.sub(r"[\s、，,；;\/]+", "", text)
    blockers: list[dict[str, str]] = []
    if _NEGATIVE_ZH.search(text) or _COMPACT_NEGATIVE_ZH.search(compact) or _NEGATIVE_EN.search(text):
        blockers.append(
            _blocker(
                AGENT_VISUAL_BAN,
                "ImageGen prompt adds a visual-category ban; describe the evidence-selected visual positively instead",
            )
        )
    if _EDITABILITY_OVERRIDE.search(text):
        blockers.append(
            _blocker(
                EDITABILITY_OVERRIDE,
                "ImageGen prompt turns post-blueprint editability into a blueprint visual restriction",
            )
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": not blockers,
        "status": "pass" if not blockers else "blocked",
        "blockers": blockers,
        "blocker_count": len(blockers),
    }


def assert_prompt_allowed(prompt: str) -> None:
    report = validate_prompt(prompt)
    if not report["ok"]:
        raise ValueError("; ".join(item["message"] for item in report["blockers"]))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reject agent-added V6 ImageGen visual-category bans."
    )
    parser.add_argument("prompt_file", type=Path)
    args = parser.parse_args()
    prompt = args.prompt_file.read_text(encoding="utf-8")
    report = validate_prompt(prompt)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
