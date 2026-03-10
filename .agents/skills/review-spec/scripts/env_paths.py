from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Tuple

from dotenv import load_dotenv


def find_nearest_env_path(start: Path) -> Optional[Path]:
    """Find nearest .env by searching current directory and parents."""
    current = start
    while True:
        candidate = current / ".env"
        if candidate.exists():
            return candidate
        if current.parent == current:
            return None
        current = current.parent


def resolve_env_path(cwd: Path, repo_path_opt: Optional[str]) -> Optional[Path]:
    """Prefer workspace-root .env (repo parent), then fall back to nearest .env."""
    repo_path_hint = repo_path_opt or os.getenv("REPO_PATH")
    if repo_path_hint:
        workspace_env = Path(repo_path_hint).expanduser().resolve().parent / ".env"
        if workspace_env.exists():
            return workspace_env

    if (cwd / ".git").exists():
        workspace_env = cwd.parent / ".env"
        if workspace_env.exists():
            return workspace_env

    return find_nearest_env_path(cwd)


def resolve_runtime_paths(
    cwd: Path, repo_path_opt: Optional[str]
) -> Tuple[Path, Path, Optional[Path]]:
    """Load .env and resolve repository and working directories.

    Returns (repo_path, working_dir, env_path).
    """
    env_path = resolve_env_path(cwd, repo_path_opt)
    if env_path:
        load_dotenv(env_path)

    repo_dir = repo_path_opt or os.getenv("REPO_PATH") or str(cwd)
    repo_path_raw = Path(repo_dir).expanduser()
    if not repo_path_raw.is_absolute():
        raise ValueError(f"REPO_PATH must be an absolute path: {repo_dir}")
    repo_path = repo_path_raw.resolve()
    if not repo_path.exists() or not (repo_path / ".git").exists():
        raise ValueError(f"Invalid git repository path: {repo_path}")

    working_dir_raw = os.getenv("WORKING_DIR")
    if working_dir_raw:
        working_dir_path_raw = Path(working_dir_raw).expanduser()
        if not working_dir_path_raw.is_absolute():
            raise ValueError(f"WORKING_DIR must be an absolute path: {working_dir_raw}")
        working_dir = working_dir_path_raw.resolve()
        if not working_dir.exists() or not working_dir.is_dir():
            raise ValueError(
                f"WORKING_DIR does not exist or is not a directory: {working_dir}"
            )
    else:
        working_dir = cwd

    return repo_path, working_dir, env_path
