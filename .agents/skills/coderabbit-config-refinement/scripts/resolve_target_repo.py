#!/usr/bin/env -S uv run --script
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


def normalize(path: Path) -> str:
    return os.path.realpath(path)


def contains(items: list[str], needle: str) -> bool:
    return needle in items


def add_unique(items: list[str], path: str) -> None:
    if not contains(items, path):
        items.append(path)


def consider_dir(dir_path: Path, candidates: list[str], preferred: list[str]) -> None:
    if not (dir_path / ".git").is_dir():
        return

    abs_path = normalize(dir_path)
    add_unique(candidates, abs_path)

    if Path(abs_path, ".coderabbit.yaml").is_file():
        add_unique(preferred, abs_path)


def tokenize_hint(hint: str) -> list[str]:
    tokens: list[str] = []
    for raw in hint.split():
        token = re.sub(r"^[\"\'()]|[\"\'(),]$", "", raw)
        if token:
            tokens.append(token)
    return tokens


def main() -> int:
    hint = sys.argv[1] if len(sys.argv) > 1 else ""
    workspace = Path(sys.argv[2]) if len(sys.argv) > 2 else Path.cwd()

    if not workspace.is_dir():
        print("NO_REPO_FOUND")
        return 1

    candidates: list[str] = []
    preferred: list[str] = []
    hinted: list[str] = []

    if hint:
        for token in tokenize_hint(hint):
            token_path = Path(token)
            if token_path.is_dir():
                consider_dir(token_path, candidates, preferred)
                if (token_path / ".git").is_dir():
                    add_unique(hinted, normalize(token_path))
            else:
                workspace_token = workspace / token
                if workspace_token.is_dir():
                    consider_dir(workspace_token, candidates, preferred)
                    if (workspace_token / ".git").is_dir():
                        add_unique(hinted, normalize(workspace_token))

    if len(hinted) == 1:
        print(f"TARGET_REPO={hinted[0]}")
        return 0

    if len(hinted) > 1:
        print("MULTIPLE_REPOS")
        for path in hinted:
            print(path)
        return 2

    git_path = shutil.which("git")
    if git_path is not None:
        try:
            repo_root = subprocess.run(
                [git_path, "rev-parse", "--show-toplevel"],
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            ).stdout.strip()
            if repo_root:
                consider_dir(Path(repo_root), candidates, preferred)
        except (
            subprocess.CalledProcessError,
            FileNotFoundError,
            subprocess.TimeoutExpired,
        ):
            pass

    for entry in workspace.iterdir():
        if entry.is_dir():
            consider_dir(entry, candidates, preferred)

    if preferred:
        candidates = preferred

    if len(candidates) == 1:
        print(f"TARGET_REPO={candidates[0]}")
        return 0

    if len(candidates) > 1:
        print("MULTIPLE_REPOS")
        for path in candidates:
            print(path)
        return 2

    print("NO_REPO_FOUND")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
