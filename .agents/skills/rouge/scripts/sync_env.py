#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.9"
# ///

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

KEY_RE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")
LINE_RE = re.compile(
    r"^(\s*(?:export\s+)?)([A-Za-z_][A-Za-z0-9_]*)(\s*=\s*)(.*?)(\s*)$"
)
COMMENTED_LINE_RE = re.compile(
    r"^(\s*)#\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)(\s*=\s*)(.*?)(\s*)$"
)
TEMPLATE_KEY_RE = re.compile(r"^\s*#?\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")


def parse_env_map(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        m = KEY_RE.match(line)
        if m:
            result[m.group(1)] = m.group(2)
    return result


def parse_template_keys(text: str) -> set[str]:
    keys: set[str] = set()
    for line in text.splitlines():
        m = TEMPLATE_KEY_RE.match(line)
        if m:
            keys.add(m.group(1))
    return keys


def merge_template_with_values(
    template_text: str, old_values: dict[str, str]
) -> tuple[str, int]:
    merged_count = 0
    out_lines: list[str] = []
    for line in template_text.splitlines():
        stripped = line.strip()
        if not stripped:
            out_lines.append(line)
            continue

        commented_match = COMMENTED_LINE_RE.match(line)
        if commented_match:
            indent, key, sep, _rhs, trail = commented_match.groups()
            if key in old_values:
                out_lines.append(f"{indent}{key}{sep}{old_values[key]}{trail}")
                merged_count += 1
            else:
                out_lines.append(line)
            continue

        if line.lstrip().startswith("#"):
            out_lines.append(line)
            continue
        m = LINE_RE.match(line)
        if not m:
            out_lines.append(line)
            continue
        prefix, key, sep, _rhs, trail = m.groups()
        if key in old_values:
            out_lines.append(f"{prefix}{key}{sep}{old_values[key]}{trail}")
            merged_count += 1
        else:
            out_lines.append(line)

    merged_text = "\n".join(out_lines)
    if template_text.endswith("\n"):
        merged_text += "\n"
    return merged_text, merged_count


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sync .env from a template and merge matching key values from backup."  # noqa: E501
    )
    parser.add_argument(
        "--template",
        default="~/git/rouge/rouge/.env.example",
        help="Source template path (default: ~/git/rouge/rouge/.env.example)",
    )
    parser.add_argument(
        "--target",
        default=".env",
        help="Target .env path (default: .env)",
    )
    parser.add_argument(
        "--backup",
        default=".env.old",
        help="Backup path for current target (default: .env.old)",
    )
    args = parser.parse_args()

    template_path = Path(args.template).expanduser().resolve()
    target_path = Path(args.target).expanduser().resolve()
    backup_path = Path(args.backup).expanduser().resolve()

    if not template_path.exists():
        print(f"Template file not found: {template_path}", file=sys.stderr)
        return 1
    if not template_path.is_file():
        print(f"Template path is not a file: {template_path}", file=sys.stderr)
        return 1

    backup_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    if target_path.exists():
        shutil.copy2(target_path, backup_path)
    else:
        backup_path.write_text("", encoding="utf-8")

    old_text = backup_path.read_text(encoding="utf-8")
    template_text = template_path.read_text(encoding="utf-8")

    old_map = parse_env_map(old_text)
    template_keys = parse_template_keys(template_text)
    merged_text, merged_keys = merge_template_with_values(template_text, old_map)
    target_path.write_text(merged_text, encoding="utf-8")

    old_keys = set(old_map.keys())
    new_keys = set(template_keys)
    overlap = old_keys & new_keys
    dropped = old_keys - new_keys
    added = new_keys - old_keys

    print(f"template path: {template_path}")
    print(f"target path: {target_path}")
    print(f"backup path: {backup_path}")
    print(f"number of merged keys: {merged_keys}")
    print(f"old keys count: {len(old_keys)}")
    print(f"new keys count: {len(new_keys)}")
    print(f"preserved overlap count: {len(overlap)}")
    print(f"dropped keys count: {len(dropped)}")
    print(f"added keys count: {len(added)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
