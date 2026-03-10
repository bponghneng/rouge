#!/usr/bin/env uv run
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "typer>=0.9.0",
#   "python-dotenv>=1.0.0",
# ]
# ///

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import typer
from env_paths import resolve_runtime_paths
from extract_cycles import extract_prompt_for_all, parse_prompt_findings
from github_client import (
    fetch_pr_metadata,
    fetch_pr_reviews,
    fetch_review_threads,
    get_repo_info,
)
from resolution import apply_resolution_status, build_thread_evidence
from rewrite_engine import (
    apply_issue_decisions,
    collect_decisions,
    ensure_effective_fields,
)
from snapshot_store import (
    append_rouge_issue,
    get_cycle_record,
    load_cycle_snapshot,
    load_latest_snapshot,
    merge_rewritten_findings,
    persist_snapshots,
    save_cycle_snapshot,
    set_cycle_accepted,
    set_cycle_rewrite_complete,
    set_cycle_spec,
    snapshot_root,
)
from spec_renderer import render_merged_spec, render_spec, write_spec_file

DEFAULT_REVIEW_AUTHORS: Set[str] = {"coderabbitai", "coderabbitai[bot]"}

app = typer.Typer()


@app.command()
def main(
    pr_number: int = typer.Argument(..., help="GitHub PR number"),
    output_dir: str | None = typer.Option(
        None, "--output-dir", "-o", help="Output directory for spec file"
    ),
    repo_path: str | None = typer.Option(
        None, "--repo-path", "-r", help="Repository path (overrides REPO_PATH env var)"
    ),
    reviewer: List[str] = typer.Option(
        [],
        "--reviewer",
        help=(
            "Reviewer login(s) to include. Repeat flag for multiple values. "
            "Defaults to CodeRabbit accounts."
        ),
    ),
    rewrite: bool = typer.Option(
        False,
        "--rewrite",
        help="Rewrite a cycle's snapshot using decisions and regenerate spec.",
    ),
    cycle: str | None = typer.Option(
        None,
        "--cycle",
        help=(
            "Target cycle ID for --rewrite or --accept. "
            "Defaults to latest cycle when used with --rewrite."
        ),
    ),
    decision: List[str] = typer.Option(
        [],
        "--decision",
        help=(
            "User decision directive, e.g. "
            "'On issue number one, don't fix.' or "
            "'On issue number three, timeout should be 30 seconds.'"
        ),
    ),
    decisions_file: str | None = typer.Option(
        None,
        "--decisions-file",
        help="Path to newline-delimited decision directives.",
    ),
    accept: bool = typer.Option(
        False,
        "--accept",
        help=(
            "Accept a cycle's spec as-is, marking it ready for merge. Requires --cycle."
        ),
    ),
    merge: str | None = typer.Option(
        None,
        "--merge",
        help=(
            "Comma-separated cycle IDs to merge into a single spec. "
            "All listed cycles must have accepted=true."
        ),
    ),
    record_issue: bool = typer.Option(
        False,
        "--record-issue",
        help="Record a Rouge issue created from a spec.",
    ),
    rouge_id: str | None = typer.Option(
        None,
        "--rouge-id",
        help="Rouge issue ID to record (used with --record-issue).",
    ),
    spec_path_record: str | None = typer.Option(
        None,
        "--spec-path",
        help="Spec file path used to create the Rouge issue (used with --record-issue).",  # noqa: E501
    ),
    record_cycles: str | None = typer.Option(
        None,
        "--cycles",
        help=(
            "Comma-separated cycle IDs included in the Rouge issue "
            "(used with --record-issue)."
        ),
    ),
) -> None:
    print(f"\n{'=' * 70}")
    print("  GitHub PR Review Spec Generator")
    print(f"{'=' * 70}\n")

    cwd = Path.cwd().resolve()
    try:
        repo_path_obj, working_dir, env_path = resolve_runtime_paths(cwd, repo_path)
    except ValueError as e:
        print(f"❌ {e}")
        sys.exit(1)

    if env_path:
        print(f"🧾 Loaded environment from: {env_path}")

    os.chdir(repo_path_obj)
    print(f"📂 Working in repository: {repo_path_obj}")
    print(f"📁 Output working directory: {working_dir}")

    snapshots = snapshot_root(working_dir, pr_number)

    # Enforce mutual exclusion for action flags
    action_flags = {
        "record_issue": record_issue,
        "accept": accept,
        "merge": merge is not None,
        "rewrite": rewrite,
    }
    active_actions = [name for name, is_active in action_flags.items() if is_active]
    if len(active_actions) > 1:
        print("❌ Only one action flag may be used at a time.")
        flag_names = ", ".join(f"--{name.replace('_', '-')}" for name in active_actions)  # noqa: E501
        print(f"   Active flags: {flag_names}")
        sys.exit(1)

    # --record-issue does not need GitHub API calls
    if record_issue:
        run_record_issue_flow(
            pr_number=pr_number,
            snapshots=snapshots,
            rouge_id=rouge_id,
            spec_path=spec_path_record,
            record_cycles=record_cycles,
        )
        return

    # --accept does not need GitHub API calls
    if accept:
        run_accept_flow(
            pr_number=pr_number,
            snapshots=snapshots,
            cycle_str=cycle,
        )
        return

    print("\n📋 Getting repository information...")
    try:
        owner, repo = get_repo_info()
        print(f"   Repository: {owner}/{repo}")
    except Exception as e:
        print(f"\n❌ Failed to get repo info: {e}")
        sys.exit(1)

    print(f"\n🌿 Fetching PR #{pr_number} metadata...")
    try:
        pr_data = fetch_pr_metadata(owner, repo, pr_number)
        head_branch = ((pr_data.get("head") or {}).get("ref")) or ""
        if head_branch:
            print(f"   PR branch: {head_branch}")
    except Exception as e:
        print(f"\n❌ Failed to fetch PR metadata: {e}")
        sys.exit(1)

    reviewer_logins = {
        x.strip().lower() for x in reviewer if x.strip()
    } or DEFAULT_REVIEW_AUTHORS
    print(f"   Reviewer filter: {', '.join(sorted(reviewer_logins))}")

    # --merge does not need to re-fetch cycles
    if merge is not None:
        run_merge_flow(
            pr_number=pr_number,
            merge_str=merge,
            snapshots=snapshots,
            owner=owner,
            repo=repo,
            head_branch=head_branch,
            working_dir=working_dir,
            output_dir=output_dir,
        )
        return

    if rewrite and not (decision or decisions_file):
        print(
            "❌ No decisions provided. Use --decision or "
            "--decisions-file with --rewrite."
        )
        sys.exit(1)

    if rewrite:
        run_rewrite_flow(
            pr_number=pr_number,
            owner=owner,
            repo=repo,
            head_branch=head_branch,
            working_dir=working_dir,
            output_dir=output_dir,
            decision=decision,
            decisions_file=decisions_file,
            cycle_str=cycle,
            snapshots=snapshots,
        )
        return

    if decision or decisions_file:
        print(
            "⚠️ Decisions were provided during generation and were ignored. "
            "Use --rewrite to apply decisions to snapshot data."
        )

    run_generate_flow(
        pr_number=pr_number,
        owner=owner,
        repo=repo,
        head_branch=head_branch,
        reviewer_logins=reviewer_logins,
        working_dir=working_dir,
        output_dir=output_dir,
        snapshots=snapshots,
    )


def run_generate_flow(
    pr_number: int,
    owner: str,
    repo: str,
    head_branch: str,
    reviewer_logins: Set[str],
    working_dir: Path,
    output_dir: str | None,
    snapshots: Path,
) -> None:
    print(f"\n🔍 Fetching review cycles for PR #{pr_number}...")
    reviews = fetch_pr_reviews(owner, repo, pr_number)
    cycles = [
        r
        for r in reviews
        if (r.get("user") or {}).get("login", "").lower() in reviewer_logins
    ]
    cycles.sort(key=lambda r: r.get("submitted_at") or "")

    if not cycles:
        print("\n✅ No matching reviewer cycles found.")
        sys.exit(0)

    print(f"   Found {len(cycles)} matching review cycles")

    print("\n🧩 Extracting findings from consolidated prompt blocks...")
    cycle_findings: List[Dict[str, Any]] = []
    for cycle in cycles:
        prompt_block = extract_prompt_for_all(cycle.get("body") or "")
        if not prompt_block:
            continue
        cycle_findings.extend(
            parse_prompt_findings(
                prompt_block,
                review_id=cycle["id"],
                submitted_at=cycle.get("submitted_at") or "",
                commit_id=cycle.get("commit_id") or "",
            )
        )

    if not cycle_findings:
        print("\n✅ No findings extracted from consolidated prompt blocks.")
        sys.exit(0)

    print(f"   Extracted {len(cycle_findings)} findings across cycles")

    print("\n🧵 Fetching review threads for resolution evidence...")
    threads = fetch_review_threads(owner, repo, pr_number)
    print(f"   Found {len(threads)} review threads")
    thread_evidence = build_thread_evidence(threads, reviewer_logins)
    apply_resolution_status(cycle_findings, thread_evidence)

    persist_snapshots(snapshots, owner, repo, pr_number, cycles, cycle_findings)

    output_base = Path(output_dir) if output_dir else (working_dir / "specs")
    if output_dir and not output_base.is_absolute():
        output_base = working_dir / output_base

    # Group findings by cycle for per-cycle spec generation
    findings_by_cycle: Dict[int, List[Dict[str, Any]]] = {}
    for f in cycle_findings:
        findings_by_cycle.setdefault(int(f["review_id"]), []).append(f)

    specs_generated = 0
    specs_skipped = 0

    print()
    for cycle in cycles:
        cycle_id = int(cycle["id"])
        record = get_cycle_record(snapshots, cycle_id)
        if record and record.get("spec_path"):
            print(f"   ⏭ Cycle {cycle_id}: spec already exists, skipping")
            specs_skipped += 1
            continue

        cycle_f = findings_by_cycle.get(cycle_id, [])
        if not cycle_f:
            print(f"   ⏭ Cycle {cycle_id}: no findings extracted, skipping")
            specs_skipped += 1
            continue

        spec_issues = [
            f for f in cycle_f if f["resolution_status"] in {"unresolved", "unknown"}
        ]
        if not spec_issues:
            if all(f["resolution_status"] == "resolved" for f in cycle_f):
                print(f"   ✅ Cycle {cycle_id}: all findings resolved, no spec needed")
                specs_skipped += 1
                continue
            spec_issues = cycle_f

        spec_issues, skipped_issues, applied_decisions = apply_issue_decisions(
            spec_issues, []
        )

        commit_id = cycle.get("commit_id") or ""
        print(f"📄 Generating spec for cycle {cycle_id} ({len(spec_issues)} issues)...")
        spec_content = render_spec(
            pr_number=pr_number,
            issues=spec_issues,
            skipped_issues=skipped_issues,
            applied_decisions=applied_decisions,
            owner=owner,
            repo=repo,
            all_findings=cycle_f,
            pr_branch=head_branch,
            cycle_id=cycle_id,
            commit_id=commit_id,
        )

        _, display_path = write_spec_file(
            spec_content, output_base, working_dir, repo, pr_number, cycle_id=cycle_id
        )

        set_cycle_spec(snapshots, cycle_id, display_path)
        print(f"   ✅ Spec: {display_path}")
        specs_generated += 1

    print("\n✅ Generation complete.")
    print(f"   Specs generated: {specs_generated}")
    print(f"   Cycles skipped:  {specs_skipped}")
    print(f"   Snapshots:       {snapshots}")

    if specs_generated > 0:
        print(
            "\n➡ Next steps per cycle:"
            "\n   1. Review each spec"
            '\n   2. Optionally rewrite: --rewrite --cycle <id> --decision "..."'
            "\n   3. Accept: --accept --cycle <id>"
            "\n   4. Merge when all accepted: --merge <id1>,<id2>"
        )
    print(f"\n{'=' * 70}")


def run_rewrite_flow(
    pr_number: int,
    owner: str,
    repo: str,
    head_branch: str,
    working_dir: Path,
    output_dir: str | None,
    decision: List[str],
    decisions_file: str | None,
    cycle_str: Optional[str],
    snapshots: Path,
) -> None:
    # Resolve target cycle
    if cycle_str:
        try:
            target_cycle_id = int(cycle_str)
        except ValueError as e:
            print(
                f"❌ Invalid cycle ID: {e}\n"
                "   Run generate first to create baseline snapshots."
            )
            sys.exit(1)
        try:
            target_snapshot, target_snapshot_path = load_cycle_snapshot(
                snapshots, target_cycle_id
            )
        except FileNotFoundError as e:
            print(f"❌ {e}\n   Run generate first to create baseline snapshots.")
            sys.exit(1)
        except ValueError as e:
            print(f"❌ {e}\n   Run generate first to create baseline snapshots.")
            sys.exit(1)
        except json.JSONDecodeError as e:
            print(f"❌ {e}\n   Run generate first to create baseline snapshots.")
            sys.exit(1)
        except OSError as e:
            print(f"❌ {e}\n   Run generate first to create baseline snapshots.")
            sys.exit(1)
        index_data: Dict[str, Any] = {}
    else:
        # Default to latest cycle (backward compat)
        try:
            target_snapshot, target_snapshot_path, index_data = load_latest_snapshot(
                snapshots
            )
            target_cycle_id = int(target_snapshot.get("review_id", 0))
        except FileNotFoundError as e:
            print(f"❌ {e}\n   Run generate first to create baseline snapshots.")
            sys.exit(1)
        except ValueError as e:
            print(f"❌ {e}\n   Run generate first to create baseline snapshots.")
            sys.exit(1)
        except json.JSONDecodeError as e:
            print(
                f"❌ JSON decode error: {e}\n"
                "   Run generate first to create baseline snapshots."
            )
            sys.exit(1)
        except KeyError as e:
            print(
                f"❌ Missing required key: {e}\n"
                "   Run generate first to create baseline snapshots."
            )
            sys.exit(1)
        except IndexError as e:
            print(
                f"❌ Index error: {e}\n"
                "   Run generate first to create baseline snapshots."
            )
            sys.exit(1)
        except OSError as e:
            print(
                f"❌ File operation error: {e}\n"
                "   Run generate first to create baseline snapshots."
            )
            sys.exit(1)

    decision_lines = collect_decisions(decision, decisions_file, working_dir)
    if not decision_lines:
        print(
            "❌ No decisions provided. Use --decision or "
            "--decisions-file with --rewrite."
        )
        sys.exit(1)

    target_findings = [
        ensure_effective_fields(dict(f))
        for f in target_snapshot.get("findings", [])
        if f.get("resolution_status") in {"unresolved", "unknown"}
    ]
    if not target_findings:
        target_findings = [
            ensure_effective_fields(dict(f))
            for f in target_snapshot.get("findings", [])
        ]

    rewritten_active, rewritten_skipped, applied_decisions = apply_issue_decisions(
        target_findings, decision_lines
    )

    merge_rewritten_findings(target_snapshot, rewritten_active, rewritten_skipped)
    save_cycle_snapshot(
        target_snapshot, target_snapshot_path, decision_lines, applied_decisions
    )
    set_cycle_rewrite_complete(snapshots, target_cycle_id)

    commit_id = target_snapshot.get("commit_id") or ""
    cycle_findings = [
        ensure_effective_fields(dict(f)) for f in target_snapshot.get("findings", [])
    ]

    print(
        f"\n📄 Regenerating specification from snapshot rewrite "
        f"(cycle {target_cycle_id})..."
    )
    spec_content = render_spec(
        pr_number=pr_number,
        issues=rewritten_active,
        skipped_issues=rewritten_skipped,
        applied_decisions=applied_decisions,
        owner=owner,
        repo=repo,
        all_findings=cycle_findings,
        pr_branch=head_branch,
        cycle_id=target_cycle_id,
        commit_id=commit_id,
    )

    output_base = Path(output_dir) if output_dir else (working_dir / "specs")
    if output_dir and not output_base.is_absolute():
        output_base = working_dir / output_base

    _, display_path = write_spec_file(
        spec_content,
        output_base,
        working_dir,
        repo,
        pr_number,
        cycle_id=target_cycle_id,
    )

    set_cycle_spec(snapshots, target_cycle_id, display_path)

    print(f"\n✅ Rewritten spec generated: {display_path}")
    print(f"   Active issues after rewrite: {len(rewritten_active)}")
    print(f"   Skipped issues after rewrite: {len(rewritten_skipped)}")
    print(f"   Snapshot updated: {target_snapshot_path}")
    print(f"   rewrite_complete set for cycle {target_cycle_id}")
    print(
        f"\n➡ Next step: accept this cycle when satisfied:"
        f"\n   --accept --cycle {target_cycle_id}"
    )
    print(f"\n{'=' * 70}")


def run_accept_flow(
    pr_number: int,
    snapshots: Path,
    cycle_str: Optional[str],
) -> None:
    if not cycle_str:
        print("❌ --cycle <id> is required with --accept")
        sys.exit(1)

    try:
        cycle_id = int(cycle_str)
    except ValueError:
        print(f"❌ Invalid cycle ID: {cycle_str}")
        sys.exit(1)

    record = get_cycle_record(snapshots, cycle_id)
    if not record:
        print(
            f"❌ Cycle {cycle_id} not found in index."
            f"\n   Run generate first: uv run ... {pr_number}"
        )
        sys.exit(1)

    if not record.get("spec_path"):
        print(
            f"❌ Cycle {cycle_id} has no spec generated yet."
            f"\n   Run generate first: uv run ... {pr_number}"
        )
        sys.exit(1)

    set_cycle_accepted(snapshots, cycle_id)

    print(f"\n✅ Cycle {cycle_id} accepted.")
    print(f"   Spec: {record['spec_path']}")
    print(f"   rewrite_complete: {record.get('rewrite_complete', False)}")
    print("\n➡ When all target cycles are accepted, merge them:")
    print(f"   --merge {cycle_id},<other_cycle_id>")
    print(f"\n{'=' * 70}")


def run_merge_flow(
    pr_number: int,
    merge_str: str,
    snapshots: Path,
    owner: str,
    repo: str,
    head_branch: str,
    working_dir: Path,
    output_dir: str | None,
) -> None:
    cycle_ids_raw = [c.strip() for c in merge_str.split(",") if c.strip()]
    if not cycle_ids_raw:
        print("❌ No cycle IDs provided to --merge")
        sys.exit(1)

    try:
        cycle_ids = [int(c) for c in cycle_ids_raw]
    except ValueError as e:
        print(f"❌ Invalid cycle ID in --merge: {e}")
        sys.exit(1)

    if len(cycle_ids) != len(set(cycle_ids)):
        print("❌ Duplicate cycle IDs detected in --merge")
        sys.exit(1)

    print(f"\n🔍 Validating cycles for merge: {', '.join(str(c) for c in cycle_ids)}")

    errors: List[str] = []
    records: List[Dict[str, Any]] = []
    for cycle_id in cycle_ids:
        record = get_cycle_record(snapshots, cycle_id)
        if not record:
            errors.append(f"  - Cycle {cycle_id}: not found in index (run generate)")
        elif not record.get("spec_path"):
            errors.append(
                f"  - Cycle {cycle_id}: no spec generated (run generate first)"
            )
        elif not record.get("accepted"):
            errors.append(
                f"  - Cycle {cycle_id}: not accepted"
                f" (run --accept --cycle {cycle_id} first)"
            )
        else:
            records.append(record)

    if errors:
        print("❌ Merge validation failed:\n" + "\n".join(errors))
        sys.exit(1)

    print(f"   All {len(cycle_ids)} cycles validated.")

    cycle_sections: List[Dict[str, Any]] = []
    for record in records:
        cycle_id = int(record["review_id"])
        snapshot, _ = load_cycle_snapshot(snapshots, cycle_id)
        findings = [
            ensure_effective_fields(dict(f)) for f in snapshot.get("findings", [])
        ]
        active_findings = [
            f
            for f in findings
            if f.get("resolution_status") in {"unresolved", "unknown"}
        ]
        if not active_findings:
            active_findings = findings

        active, skipped, applied = apply_issue_decisions(active_findings, [])
        cycle_sections.append(
            {
                "cycle_id": cycle_id,
                "submitted_at": record.get("submitted_at", ""),
                "commit_id": record.get("commit_id", ""),
                "issues": active,
                "skipped_issues": skipped,
                "applied_decisions": applied,
            }
        )

    total = sum(len(s["issues"]) for s in cycle_sections)
    print(
        f"\n📄 Generating merged spec ({total} issues across "
        f"{len(cycle_ids)} cycles)..."
    )

    spec_content = render_merged_spec(
        pr_number=pr_number,
        cycle_sections=cycle_sections,
        owner=owner,
        repo=repo,
        pr_branch=head_branch,
    )

    output_base = Path(output_dir) if output_dir else (working_dir / "specs")
    if output_dir and not output_base.is_absolute():
        output_base = working_dir / output_base

    _, display_path = write_spec_file(
        spec_content, output_base, working_dir, repo, pr_number
    )

    print(f"\n✅ Merged spec generated: {display_path}")
    print(f"   Cycles merged: {', '.join(str(c) for c in cycle_ids)}")
    print(f"   Total issues: {total}")
    print_patch_next_step(pr_number, display_path, head_branch, merged=True)


def run_record_issue_flow(
    pr_number: int,
    snapshots: Path,
    rouge_id: Optional[str],
    spec_path: Optional[str],
    record_cycles: Optional[str],
) -> None:
    if not rouge_id:
        print("❌ --rouge-id <id> is required with --record-issue")
        sys.exit(1)

    cycle_ids: List[str] = []
    if record_cycles:
        cycle_ids = [c.strip() for c in record_cycles.split(",") if c.strip()]

    resolved_spec = spec_path or "<unknown>"

    append_rouge_issue(
        snapshot_dir=snapshots,
        rouge_issue_id=rouge_id,
        spec_path=resolved_spec,
        cycle_ids=cycle_ids,
    )

    print(f"\n✅ Recorded Rouge issue: {rouge_id}")
    print(f"   Spec: {resolved_spec}")
    print(f"   Cycles: {', '.join(cycle_ids) if cycle_ids else '(none specified)'}")
    print(f"   Audit log: .rouge/review-spec/pr-{pr_number}/rouge-issues.json")
    print(f"\n{'=' * 70}")


def print_patch_next_step(
    pr_number: int,
    display_path: str,
    head_branch: str,
    rewritten: bool = False,
    merged: bool = False,
) -> None:
    patch_title = f"PR #{pr_number} review issues"
    patch_cmd_parent = (
        f'rouge issue create --spec-file "{display_path}" '
        f'--title "{patch_title}" --type patch --parent-issue-id <PARENT_ISSUE_ID>'
    )

    if merged:
        print("\n➡ Next step: create Rouge patch issue from merged spec.")
    elif rewritten:
        print("\n➡ Next step: create Rouge patch issue from this rewritten spec.")
    else:
        print("\n➡ Next step: create Rouge patch issue from this spec.")

    if head_branch:
        patch_cmd_branch = (
            f'rouge issue create --spec-file "{display_path}" '
            f'--title "{patch_title}" --type patch --branch "{head_branch}"'
        )
        print(f"   Using branch from PR: {patch_cmd_branch}")
    print(f"   Or use parent issue: {patch_cmd_parent}")

    cycle_ids_placeholder = "<cycle_id1>,<cycle_id2>"
    print(
        f"\n   After creating the issue, record it:"
        f"\n   --record-issue --rouge-id <ISSUE_ID>"
        f' --spec-path "{display_path}"'
        f" --cycles {cycle_ids_placeholder}"
    )
    print(f"\n{'=' * 70}")


if __name__ == "__main__":
    app()
