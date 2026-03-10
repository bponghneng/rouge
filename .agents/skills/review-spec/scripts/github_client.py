from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any, Dict, List, Tuple, cast


def run_gh(cmd_args: List[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    gh_path = shutil.which("gh")
    if not gh_path:
        raise RuntimeError("GitHub CLI `gh` not found in PATH.")
    return subprocess.run([gh_path, *cmd_args], **kwargs)


def get_repo_info() -> Tuple[str, str]:
    result = run_gh(
        ["repo", "view", "--json", "owner,name"],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(result.stdout)
    return data["owner"]["login"], data["name"]


def fetch_pr_metadata(owner: str, repo: str, pr_number: int) -> Dict[str, Any]:
    result = run_gh(
        ["api", f"repos/{owner}/{repo}/pulls/{pr_number}"],
        capture_output=True,
        text=True,
        check=True,
    )
    return cast(Dict[str, Any], json.loads(result.stdout))


def fetch_pr_reviews(owner: str, repo: str, pr_number: int) -> List[Dict[str, Any]]:
    result = run_gh(
        ["api", f"repos/{owner}/{repo}/pulls/{pr_number}/reviews?per_page=100"],
        capture_output=True,
        text=True,
        check=True,
    )
    return cast(List[Dict[str, Any]], json.loads(result.stdout))


def fetch_review_threads(owner: str, repo: str, pr_number: int) -> List[Dict[str, Any]]:
    query = """
query($owner: String!, $repo: String!, $number: Int!, $after: String) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) {
      reviewThreads(first: 100, after: $after) {
        pageInfo {
          hasNextPage
          endCursor
        }
        nodes {
          id
          isResolved
          path
          line
          originalLine
          comments(first: 20) {
            nodes {
              author { login }
              body
              path
              line
              createdAt
            }
          }
        }
      }
    }
  }
}
"""

    threads: List[Dict[str, Any]] = []
    after = None

    while True:
        cmd = [
            "api",
            "graphql",
            "-f",
            f"query={query}",
            "-F",
            f"owner={owner}",
            "-F",
            f"repo={repo}",
            "-F",
            f"number={pr_number}",
        ]
        if after:
            cmd.extend(["-F", f"after={after}"])

        result = run_gh(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        review_threads = data["data"]["repository"]["pullRequest"]["reviewThreads"]
        threads.extend(review_threads["nodes"])
        page_info = review_threads["pageInfo"]

        if not page_info["hasNextPage"]:
            break
        after = page_info["endCursor"]

    return threads
