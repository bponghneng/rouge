from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from extract_cycles import determine_severity, extract_ai_prompt


def build_thread_evidence(
    threads: List[Dict[str, Any]], reviewer_logins: Set[str]
) -> List[Dict[str, Any]]:
    evidence: List[Dict[str, Any]] = []

    for thread in threads:
        is_resolved = thread.get("isResolved")
        path = thread.get("path") or "N/A"

        for comment in thread.get("comments", {}).get("nodes", []):
            author = ((comment.get("author") or {}).get("login") or "").lower()
            if author not in reviewer_logins:
                continue

            line = (
                comment.get("line") or thread.get("line") or thread.get("originalLine")
            )
            body = comment.get("body") or ""
            ai_prompt = extract_ai_prompt(body)
            severity = determine_severity(body)

            evidence.append(
                {
                    "thread_id": thread.get("id"),
                    "path": path,
                    "line": line,
                    "is_resolved": is_resolved,
                    "ai_prompt": ai_prompt,
                    "severity": severity,
                }
            )

    return evidence


def apply_resolution_status(
    findings: List[Dict[str, Any]], thread_evidence: List[Dict[str, Any]]
) -> None:
    findings_by_review: Dict[int, List[Dict[str, Any]]] = {}
    review_submitted_at: Dict[int, str] = {}

    for finding in findings:
        rid = int(finding["review_id"])
        if rid not in findings_by_review:
            findings_by_review[rid] = []
        submitted_at = str(finding.get("submitted_at") or "")
        existing = review_submitted_at.get(rid)
        if existing is None or (submitted_at and submitted_at < existing):
            review_submitted_at[rid] = submitted_at
        findings_by_review[rid].append(finding)

    review_order = sorted(
        findings_by_review,
        key=lambda rid: (review_submitted_at.get(rid, ""), rid),
    )

    for finding in findings:
        finding["thread_resolved"] = match_thread_evidence(finding, thread_evidence)
        matched_severity = match_thread_severity(finding, thread_evidence)
        if matched_severity and matched_severity != "Unknown":
            finding["severity"] = matched_severity

    for idx, rid in enumerate(review_order):
        later_fingerprints = {
            f["fingerprint"]
            for next_rid in review_order[idx + 1 :]
            for f in findings_by_review[next_rid]
        }

        for finding in findings_by_review[rid]:
            if finding.get("thread_resolved") is True:
                finding["resolution_status"] = "resolved"
                finding["resolution_confidence"] = "high"
            elif finding.get("thread_resolved") is False:
                finding["resolution_status"] = "unresolved"
                finding["resolution_confidence"] = "high"
            elif idx == len(review_order) - 1:
                finding["resolution_status"] = "unresolved"
                finding["resolution_confidence"] = "medium"
            elif finding["fingerprint"] in later_fingerprints:
                finding["resolution_status"] = "unresolved"
                finding["resolution_confidence"] = "medium"
            else:
                finding["resolution_status"] = "likely_resolved"
                finding["resolution_confidence"] = "medium"


def match_thread_evidence(
    finding: Dict[str, Any], evidence: List[Dict[str, Any]]
) -> Optional[bool]:
    path = finding["path"]
    start_line = finding.get("start_line")
    end_line = finding.get("end_line")

    candidate_states: List[bool] = []
    for item in evidence:
        if item["path"] != path:
            continue

        line = item.get("line")
        if line is None:
            continue

        if start_line is not None and end_line is not None:
            if not (start_line <= int(line) <= end_line):
                continue

        candidate_states.append(bool(item["is_resolved"]))

    if not candidate_states:
        return None

    if any(state is False for state in candidate_states):
        return False
    return True


def match_thread_severity(
    finding: Dict[str, Any], evidence: List[Dict[str, Any]]
) -> Optional[str]:
    """Return severity from the first matching thread comment, or None."""
    path = finding["path"]
    start_line = finding.get("start_line")
    end_line = finding.get("end_line")

    for item in evidence:
        if item["path"] != path:
            continue

        line = item.get("line")
        if line is None:
            continue

        if start_line is not None and end_line is not None:
            try:
                line_int = int(line)
            except (ValueError, TypeError):
                continue
            if not (start_line <= line_int <= end_line):
                continue

        severity = item.get("severity")
        if severity and severity != "Unknown":
            return severity

    return None
