from __future__ import annotations

import hashlib
import re
from typing import Any

PROMPT_ALL_MARKER = "Prompt for all review comments with AI agents"

# Maps lowercase section header text (without trailing colon) to display label
CATEGORY_HEADERS: dict[str, str] = {
    "inline comments": "Inline",
    "outside diff comments": "Outside diff",
    "nitpick comments": "Nitpick",
}


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def determine_severity(text: str) -> str:
    value = text.lower()
    if any(
        marker in value
        for marker in ["[critical]", "critical", "[high]", "🟠 major", "major"]
    ):
        return "Major"
    if any(marker in value for marker in ["[medium]", "[low]", "🟡 minor", "minor"]):
        return "Minor"
    if any(marker in value for marker in ["🔵 trivial", "nitpick", "suggestion"]):
        return "Trivial"
    return "Unknown"


def extract_ai_prompt(body: str) -> str:
    marker_match = re.search(
        r"🤖\s*(?:Prompt for AI Agents|AI Agent Prompt)[^\n]*\n",
        body,
        re.IGNORECASE,
    )
    if not marker_match:
        return ""
    after_marker = body[marker_match.end() :]
    fence_match = re.search(
        r"^(`{3,})(?:\w+)?\n(.*?)\n\1$",
        after_marker,
        re.DOTALL | re.MULTILINE,
    )
    if fence_match:
        return fence_match.group(2).strip()
    return ""


def extract_prompt_for_all(review_body: str) -> str:
    if PROMPT_ALL_MARKER not in review_body:
        return ""

    marker_match = re.search(
        r"<summary>🤖\s*Prompt for all review comments with AI agents</summary>"
        r"[^\n]*\n",
        review_body,
        re.IGNORECASE,
    )
    if not marker_match:
        return ""
    after_marker = review_body[marker_match.end() :]
    fence_match = re.search(
        r"^(`{3,})(?:\w+)?\n(.*?)\n\1$",
        after_marker,
        re.DOTALL | re.MULTILINE,
    )
    if not fence_match:
        return ""
    return fence_match.group(2).strip()


def parse_prompt_findings(
    prompt_text: str, review_id: int, submitted_at: str, commit_id: str
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    current_path = "N/A"
    current_category = ""
    pending_bullet: str | None = None
    awaiting_path_after_in = False

    lines = [ln.rstrip() for ln in prompt_text.splitlines()]

    def flush_pending() -> None:
        nonlocal pending_bullet
        if not pending_bullet:
            return

        finding = build_finding_from_bullet(
            pending_bullet,
            current_path,
            review_id,
            submitted_at,
            commit_id,
            current_category,
        )
        if finding:
            findings.append(finding)
        pending_bullet = None

    for line in lines:
        stripped = line.strip()

        # Detect category section headers (e.g. "Inline comments:", "Nitpick comments:")
        header_key = stripped.rstrip(":").lower()
        if header_key in CATEGORY_HEADERS:
            flush_pending()
            current_category = CATEGORY_HEADERS[header_key]
            continue

        if stripped in {"In", "In:"}:
            awaiting_path_after_in = True
            continue

        path_match = re.match(r"^(?:In\s+)?`@([^`]+)`:?\s*$", stripped)
        if path_match:
            flush_pending()
            current_path = path_match.group(1)
            awaiting_path_after_in = False
            continue

        if awaiting_path_after_in and stripped:
            awaiting_path_after_in = False

        if stripped.startswith("- "):
            flush_pending()
            pending_bullet = stripped[2:].strip()
            continue

        if pending_bullet and stripped and not stripped.startswith("---"):
            pending_bullet += f" {stripped}"

    flush_pending()
    return findings


def build_finding_from_bullet(
    bullet: str,
    path: str,
    review_id: int,
    submitted_at: str,
    commit_id: str,
    category: str = "",
) -> dict[str, Any] | None:
    line_match = re.search(
        r"line[s]?\s+(\d+)(?:\s*[-–]\s*(\d+))?", bullet, re.IGNORECASE
    )
    start_line: int | None = None
    end_line: int | None = None
    line_range = "N/A"

    if line_match:
        start_line = int(line_match.group(1))
        end_line = int(line_match.group(2)) if line_match.group(2) else start_line
        line_range = (
            str(start_line) if start_line == end_line else f"{start_line}-{end_line}"
        )

    instruction = bullet
    if ":" in bullet:
        instruction = bullet.split(":", 1)[1].strip()

    if not instruction:
        return None

    severity = determine_severity(instruction)
    normalized = normalize_text(f"{path}|{line_range}|{instruction}")
    fingerprint = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]

    problem = instruction[:220]
    return {
        "review_id": review_id,
        "submitted_at": submitted_at,
        "commit_id": commit_id,
        "path": path,
        "line_range": line_range,
        "start_line": start_line,
        "end_line": end_line,
        "problem": problem,
        "proposed_fix": "",
        "ai_prompt": instruction,
        "severity": severity,
        "category": category,
        "fingerprint": fingerprint,
        "thread_resolved": None,
        "resolution_status": "unknown",
        "resolution_confidence": "low",
        "original_problem": problem,
        "original_fix_instructions": instruction,
        "effective_problem": problem,
        "effective_fix_instructions": instruction,
        "effective_status": "active",
        "rewrite_applied": False,
        "rewrite_reason": "",
        "rewrite_source": "",
        "user_note": "",
    }
