from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def collect_decisions(
    decision_args: List[str], decisions_file: Optional[str], working_dir: Path
) -> List[str]:
    collected = [d.strip() for d in decision_args if d.strip()]
    if decisions_file:
        file_path = Path(decisions_file)
        if not file_path.is_absolute():
            file_path = working_dir / file_path
        if not file_path.exists():
            return collected
        for line in file_path.read_text().splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                collected.append(stripped)
    return collected


def ensure_effective_fields(issue: Dict[str, Any]) -> Dict[str, Any]:
    issue.setdefault("original_problem", issue.get("problem", ""))
    issue.setdefault("original_fix_instructions", issue.get("ai_prompt", ""))
    issue.setdefault(
        "effective_problem", issue.get("original_problem", issue.get("problem", ""))
    )
    issue.setdefault(
        "effective_fix_instructions",
        issue.get("original_fix_instructions", issue.get("ai_prompt", "")),
    )
    issue.setdefault("effective_status", "active")
    issue.setdefault("rewrite_applied", False)
    issue.setdefault("rewrite_reason", "")
    issue.setdefault("rewrite_source", "")
    issue.setdefault("user_note", "")
    return issue


def apply_issue_decisions(
    issues: List[Dict[str, Any]], decisions: List[str]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    ordered = sorted(
        issues,
        key=lambda x: (
            {"Major": 0, "Minor": 1, "Trivial": 2, "Unknown": 3}.get(
                x.get("severity", "Unknown"), 3
            ),
            x.get("path") or "",
            x.get("start_line") or 0,
        ),
    )
    mutable = [ensure_effective_fields(dict(issue)) for issue in ordered]
    for idx, issue in enumerate(mutable, 1):
        issue["display_index"] = idx
        if issue.get("effective_status") not in {"active", "skipped"}:
            issue["effective_status"] = "active"
        issue.setdefault("user_note", "")

    applied: List[Dict[str, Any]] = []
    for raw in decisions:
        parsed = parse_decision(raw)
        if parsed is None:
            applied.append(
                {"directive": raw, "status": "ignored", "reason": "unparsed"}
            )
            continue

        issue_index = parsed["issue_index"]
        if issue_index < 1 or issue_index > len(mutable):
            applied.append(
                {
                    "directive": raw,
                    "status": "ignored",
                    "reason": f"issue index {issue_index} out of range",
                }
            )
            continue

        target = mutable[issue_index - 1]
        if parsed["action"] == "skip":
            target["effective_status"] = "skipped"
            target["user_note"] = raw
            applied.append(
                {
                    "directive": raw,
                    "status": "applied",
                    "action": "skip",
                    "issue_index": issue_index,
                }
            )
            continue

        if parsed["action"] == "override":
            rewrite_instruction = parsed["instruction"]
            target["effective_problem"] = compose_effective_problem(
                target.get("original_problem", target.get("problem", "")),
                rewrite_instruction,
            )
            target["effective_fix_instructions"] = compose_effective_fix_instructions(
                target.get("original_fix_instructions", target.get("ai_prompt", "")),
                rewrite_instruction,
            )
            target["effective_status"] = "active"
            target["rewrite_applied"] = True
            target["rewrite_reason"] = rewrite_instruction
            target["rewrite_source"] = "user_decision"
            target["user_note"] = raw
            applied.append(
                {
                    "directive": raw,
                    "status": "applied",
                    "action": "override",
                    "issue_index": issue_index,
                }
            )
            continue

        applied.append(
            {"directive": raw, "status": "ignored", "reason": "unknown action"}
        )

    active = [i for i in mutable if i["effective_status"] == "active"]
    skipped = [i for i in mutable if i["effective_status"] == "skipped"]
    return active, skipped, applied


def parse_decision(text: str) -> Optional[Dict[str, Any]]:
    issue_match = re.search(
        r"\bissue(?:\s+number)?\s+([a-zA-Z0-9-]+)\b", text, re.IGNORECASE
    )
    if not issue_match:
        return None

    issue_index = parse_issue_index_token(issue_match.group(1))
    if issue_index is None:
        return None

    lowered = text.lower()
    if any(token in lowered for token in ["don't fix", "do not fix", "skip", "ignore"]):
        return {"issue_index": issue_index, "action": "skip"}

    instruction = extract_override_instruction(text)
    if instruction:
        return {
            "issue_index": issue_index,
            "action": "override",
            "instruction": instruction,
        }

    return None


def parse_issue_index_token(token: str) -> Optional[int]:
    if token.isdigit():
        return int(token)

    words = {
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
        "eleven": 11,
        "twelve": 12,
    }
    return words.get(token.strip().lower())


def extract_override_instruction(text: str) -> str:
    prefix_match = re.match(
        r"^\s*(?:on\s+)?issue(?:\s+number)?\s+[a-zA-Z0-9-]+\s*[,:\-]\s*(.+?)\s*$",
        text,
        re.IGNORECASE,
    )
    if prefix_match:
        return prefix_match.group(1).strip()

    trailing = re.sub(
        r"^\s*(?:on\s+)?issue(?:\s+number)?\s+[a-zA-Z0-9-]+\s*",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()
    return trailing


def compose_effective_problem(original_problem: str, instruction: str) -> str:
    base = original_problem.strip() or "Review finding requires update."
    return f"{base} Refined requirement: {instruction.strip()}"[:220]


def normalize_sentence(text: str) -> str:
    value = re.sub(r"\s+", " ", (text or "").strip())
    value = re.sub(r"\s+([,;:])", r"\1", value)
    value = re.sub(r"\.{2,}", ".", value)
    if value and value[-1] not in ".!?":
        value += "."
    return value


def is_valid_rewrite(candidate: str, original_fix: str, refinement: str) -> bool:
    candidate_l = candidate.lower()
    refinement_l = refinement.lower().strip(".")
    has_refinement = bool(refinement_l and refinement_l in candidate_l)
    has_action = any(
        verb in candidate_l
        for verb in ["update", "change", "modify", "set", "replace", "ensure", "add"]
    )
    anchor_tokens = [
        t for t in re.findall(r"[a-z0-9_]+", original_fix.lower()) if len(t) > 4
    ]
    has_anchor = (
        any(token in candidate_l for token in anchor_tokens[:8])
        if anchor_tokens
        else True
    )
    return bool(has_refinement and has_action and has_anchor)


def compose_effective_fix_instructions(original_fix: str, instruction: str) -> str:
    base = normalize_sentence(original_fix).rstrip(".!?")
    refinement = normalize_sentence(instruction).rstrip(".!?")
    if not base:
        return f"{refinement}."

    candidate = (
        "Update the implementation to address the original review finding "
        "while explicitly "
        f"satisfying this refinement: {refinement}. "
        f"Required change scope from the original finding: {base}. "
        "Ensure the final code and related tests/config updates reflect this "
        "refinement directly."
    )
    if is_valid_rewrite(candidate, base, refinement):
        return candidate

    return (
        f"{base} Additional required constraint: {refinement}. "
        "Keep the original intent, but ensure the final implementation explicitly "
        "satisfies this added constraint."
    )
