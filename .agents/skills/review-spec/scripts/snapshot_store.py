from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from rewrite_engine import ensure_effective_fields


def snapshot_root(working_dir: Path, pr_number: int) -> Path:
    return working_dir / ".rouge" / "review-spec" / f"pr-{pr_number}"


def _load_index(snapshot_dir: Path) -> Dict[str, Any]:
    index_path = snapshot_dir / "index.json"
    if not index_path.exists():
        return {}
    return json.loads(index_path.read_text())


def _save_index(snapshot_dir: Path, index: Dict[str, Any]) -> None:
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    (snapshot_dir / "index.json").write_text(json.dumps(index, indent=2))


def persist_snapshots(
    snapshot_dir: Path,
    owner: str,
    repo: str,
    pr_number: int,
    cycles: List[Dict[str, Any]],
    findings: List[Dict[str, Any]],
) -> None:
    snapshots_path = snapshot_dir / "snapshots"
    snapshots_path.mkdir(parents=True, exist_ok=True)

    grouped: Dict[int, List[Dict[str, Any]]] = {}
    for finding in findings:
        grouped.setdefault(int(finding["review_id"]), []).append(finding)

    for cycle in cycles:
        rid = int(cycle["id"])
        snapshot_path = snapshots_path / f"{rid}.json"
        existing_decisions: List[Dict[str, Any]] = []
        existing_findings_by_fp: Dict[str, Dict[str, Any]] = {}
        if snapshot_path.exists():
            existing = json.loads(snapshot_path.read_text())
            existing_decisions = existing.get("decisions", [])
            for f in existing.get("findings", []):
                fp = f.get("fingerprint")
                if fp:
                    existing_findings_by_fp[fp] = f

        def merge_finding(
            new_f: Dict[str, Any],
            _existing: Dict[str, Dict[str, Any]] = existing_findings_by_fp,
        ) -> Dict[str, Any]:
            fp = new_f.get("fingerprint")
            base = ensure_effective_fields(dict(new_f))
            if fp and fp in _existing:
                existing_f = _existing[fp]
                for field in [
                    "effective_problem",
                    "effective_fix_instructions",
                    "effective_status",
                    "rewrite_applied",
                    "rewrite_reason",
                    "rewrite_source",
                    "user_note",
                    "original_problem",
                    "original_fix_instructions",
                ]:
                    if field in existing_f:
                        base[field] = existing_f[field]
            return base

        snapshot = {
            "review_id": rid,
            "submitted_at": cycle.get("submitted_at"),
            "commit_id": cycle.get("commit_id"),
            "author": (cycle.get("user") or {}).get("login"),
            "findings": [merge_finding(f) for f in grouped.get(rid, [])],
            "decisions": existing_decisions,
        }
        snapshot_path.write_text(json.dumps(snapshot, indent=2))

    # Load existing index to preserve per-cycle metadata (spec_path, accepted, etc.)
    existing_index = _load_index(snapshot_dir)
    existing_cycles: Dict[int, Dict[str, Any]] = {
        int(c["review_id"]): c for c in existing_index.get("cycles", [])
    }

    index = {
        "repository": f"{owner}/{repo}",
        "pr_number": pr_number,
        "updated_at": datetime.now(tz=timezone.utc).isoformat(),
        "latest_review_id": int(cycles[-1]["id"]),
        "cycles": [
            {
                "review_id": int(c["id"]),
                "submitted_at": c.get("submitted_at"),
                "commit_id": c.get("commit_id"),
                "snapshot": f"snapshots/{int(c['id'])}.json",
                "spec_path": existing_cycles.get(int(c["id"]), {}).get("spec_path"),
                "generated_at": existing_cycles.get(int(c["id"]), {}).get(
                    "generated_at"
                ),
                "rewrite_complete": existing_cycles.get(int(c["id"]), {}).get(
                    "rewrite_complete", False
                ),
                "accepted": existing_cycles.get(int(c["id"]), {}).get(
                    "accepted", False
                ),
            }
            for c in cycles
        ],
    }
    _save_index(snapshot_dir, index)


def get_cycle_record(snapshot_dir: Path, cycle_id: int) -> Optional[Dict[str, Any]]:
    index = _load_index(snapshot_dir)
    for c in index.get("cycles", []):
        if int(c["review_id"]) == cycle_id:
            return c
    return None


def update_cycle_record(
    snapshot_dir: Path, cycle_id: int, updates: Dict[str, Any]
) -> None:
    index_path = snapshot_dir / "index.json"
    if not index_path.exists():
        raise FileNotFoundError(f"Snapshot index not found: {index_path}")
    index = json.loads(index_path.read_text())
    found = False
    for c in index.get("cycles", []):
        if int(c["review_id"]) == cycle_id:
            c.update(updates)
            found = True
            break
    if not found:
        raise ValueError(f"Cycle {cycle_id} not found in index")
    index["updated_at"] = datetime.now(tz=timezone.utc).isoformat()
    _save_index(snapshot_dir, index)


def set_cycle_spec(snapshot_dir: Path, cycle_id: int, spec_path: str) -> None:
    update_cycle_record(
        snapshot_dir,
        cycle_id,
        {
            "spec_path": spec_path,
            "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        },
    )


def set_cycle_rewrite_complete(snapshot_dir: Path, cycle_id: int) -> None:
    update_cycle_record(snapshot_dir, cycle_id, {"rewrite_complete": True})


def set_cycle_accepted(snapshot_dir: Path, cycle_id: int) -> None:
    update_cycle_record(snapshot_dir, cycle_id, {"accepted": True})


def load_cycle_snapshot(
    snapshot_dir: Path, cycle_id: int
) -> Tuple[Dict[str, Any], Path]:
    snapshot_path = snapshot_dir / "snapshots" / f"{cycle_id}.json"
    if not snapshot_path.exists():
        raise FileNotFoundError(
            f"Snapshot not found for cycle {cycle_id}: {snapshot_path}"
        )
    return json.loads(snapshot_path.read_text()), snapshot_path


def save_cycle_snapshot(
    snapshot: Dict[str, Any],
    snapshot_path: Path,
    decisions: List[str],
    applied: List[Dict[str, Any]],
) -> None:
    history = snapshot.get("decisions", [])
    history.append(
        {
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "applied": applied,
            "raw_directives": decisions,
        }
    )
    snapshot["decisions"] = history
    snapshot_path.write_text(json.dumps(snapshot, indent=2))


def load_latest_snapshot(
    snapshot_dir: Path,
) -> Tuple[Dict[str, Any], Path, Dict[str, Any]]:
    """Load the latest cycle's snapshot. Kept for backward compatibility."""
    index_path = snapshot_dir / "index.json"
    if not index_path.exists():
        raise FileNotFoundError(f"Snapshot index not found: {index_path}")

    index_data = json.loads(index_path.read_text())
    latest_review_id = index_data.get("latest_review_id")
    if not latest_review_id:
        raise ValueError("Snapshot index has no latest review id")

    latest_snapshot, latest_snapshot_path = load_cycle_snapshot(
        snapshot_dir, latest_review_id
    )
    return latest_snapshot, latest_snapshot_path, index_data


def save_latest_snapshot(
    latest_snapshot: Dict[str, Any],
    latest_snapshot_path: Path,
    decisions: List[str],
    applied: List[Dict[str, Any]],
) -> None:
    """Save the latest cycle's snapshot. Kept for backward compatibility."""
    save_cycle_snapshot(latest_snapshot, latest_snapshot_path, decisions, applied)


def merge_rewritten_findings(
    snapshot: Dict[str, Any],
    rewritten_active: List[Dict[str, Any]],
    rewritten_skipped: List[Dict[str, Any]],
) -> None:
    rewritten_by_fp = {
        f["fingerprint"]: f
        for f in rewritten_active + rewritten_skipped
        if f.get("fingerprint")
    }
    merged_findings: List[Dict[str, Any]] = []
    for finding in snapshot.get("findings", []):
        fp = finding.get("fingerprint")
        if fp in rewritten_by_fp:
            merged_findings.append(rewritten_by_fp[fp])
        else:
            merged_findings.append(ensure_effective_fields(dict(finding)))
    snapshot["findings"] = merged_findings


def load_all_snapshot_findings(
    snapshot_dir: Path, index_data: Dict[str, Any]
) -> List[Dict[str, Any]]:
    all_snapshot_findings: List[Dict[str, Any]] = []
    for cycle in index_data.get("cycles", []):
        cycle_path = snapshot_dir / cycle["snapshot"]
        if cycle_path.exists():
            data = json.loads(cycle_path.read_text())
            all_snapshot_findings.extend(
                [ensure_effective_fields(dict(f)) for f in data.get("findings", [])]
            )
    return all_snapshot_findings


def append_rouge_issue(
    snapshot_dir: Path,
    rouge_issue_id: str,
    spec_path: str,
    cycle_ids: List[Union[int, str]],
) -> None:
    # Validate and coerce cycle_ids to integers
    validated_cycle_ids: List[int] = []
    for cid in cycle_ids:
        if isinstance(cid, str):
            try:
                validated_cycle_ids.append(int(cid))
            except ValueError as err:
                raise ValueError(
                    f"Invalid cycle_id: '{cid}' cannot be converted to int"
                ) from err
        elif isinstance(cid, int):
            validated_cycle_ids.append(cid)
        else:
            raise TypeError(
                f"Invalid cycle_id type: expected int or str, got {type(cid).__name__}"
            )

    rouge_issues_path = snapshot_dir / "rouge-issues.json"
    if rouge_issues_path.exists():
        data = json.loads(rouge_issues_path.read_text())
    else:
        data = {"issues": []}
    data["issues"].append(
        {
            "rouge_issue_id": rouge_issue_id,
            "created_at": datetime.now(tz=timezone.utc).isoformat(),
            "spec_path": spec_path,
            "cycle_ids": validated_cycle_ids,
        }
    )
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    rouge_issues_path.write_text(json.dumps(data, indent=2))


def load_rouge_issues(snapshot_dir: Path) -> Dict[str, Any]:
    rouge_issues_path = snapshot_dir / "rouge-issues.json"
    if not rouge_issues_path.exists():
        return {"issues": []}
    return json.loads(rouge_issues_path.read_text())
