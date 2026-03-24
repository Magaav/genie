#!/usr/bin/env python3

from __future__ import annotations

import re
from pathlib import Path


DOC_SCOPE_HINTS = (
    "readme",
    "documentation",
    "docs",
    "markdown",
    "guide",
    "explain",
)
TEST_SCOPE_HINTS = (
    "test",
    "tests",
    "unit test",
    "unittest",
    "pytest",
    "check",
    "benchmark",
)
CAPABILITY_GAP_HINTS = {
    "web_navigation": ("browse", "browser", "puppeteer", "search the web", "navigate the web", "internet"),
    "safe_repo_patch_executor": ("edit code", "patch code", "apply patch", "modify files", "write code"),
    "capability_synthesis": ("new capability", "evolve an arm", "create capability", "manifest capability"),
}


def slugify(value: str, *, limit: int = 48) -> str:
    lowered = str(value or "").strip().lower()
    lowered = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    if not lowered:
        return "task"
    return lowered[:limit].strip("-") or "task"


def infer_workcell_scope(text: str) -> str:
    lowered = str(text or "").strip().lower()
    if any(hint in lowered for hint in TEST_SCOPE_HINTS):
        return "tests"
    if any(hint in lowered for hint in DOC_SCOPE_HINTS):
        return "docs"
    return "draft_only"


def infer_capability_gap(text: str) -> str:
    lowered = str(text or "").strip().lower()
    for capability, hints in CAPABILITY_GAP_HINTS.items():
        if any(hint in lowered for hint in hints):
            return capability
    return ""


def safe_generated_relative_path(proposal_id: str, text: str, scope: str) -> str:
    slug = slugify(text)
    if scope == "docs":
        return f"docs/generated/{proposal_id}-{slug}.md"
    if scope == "tests":
        return f"tests/generated/test_{proposal_id.replace('-', '_')}_{slug}.py"
    return f"state/genie/runtime/workcells/{proposal_id}/draft-{slug}.md"


def extract_fenced_content(text: str, *, preferred_language: str = "") -> str:
    payload = str(text or "").strip()
    if not payload:
        return ""
    pattern = re.compile(r"```(?P<lang>[a-zA-Z0-9_-]*)\n(?P<body>.*?)```", re.DOTALL)
    matches = list(pattern.finditer(payload))
    if not matches:
        return payload
    if preferred_language:
        for match in matches:
            if match.group("lang").strip().lower() == preferred_language.lower():
                return match.group("body").strip()
    return matches[0].group("body").strip()


def parse_critique_report(text: str) -> dict[str, object]:
    approved = False
    safe_auto_apply = False
    summary = ""
    issues: list[str] = []
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        lowered = line.lower()
        if lowered.startswith("approved:"):
            approved = lowered.split(":", 1)[1].strip() in {"yes", "true", "approved"}
        elif lowered.startswith("safe_auto_apply:"):
            safe_auto_apply = lowered.split(":", 1)[1].strip() in {"yes", "true", "approved"}
        elif lowered.startswith("summary:"):
            summary = line.split(":", 1)[1].strip()
        elif line.startswith("- "):
            issues.append(line[2:].strip())
    return {
        "approved": approved,
        "safe_auto_apply": safe_auto_apply,
        "summary": summary,
        "issues": issues,
    }


def read_context_excerpt(path: str, *, limit: int = 2000) -> str:
    target = Path(path)
    if not target.exists() or not target.is_file():
        return ""
    try:
        text = target.read_text(encoding="utf-8")
    except OSError:
        return ""
    stripped = text.strip()
    if len(stripped) > limit:
        stripped = stripped[:limit] + "\n..."
    return stripped
