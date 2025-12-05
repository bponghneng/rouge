"""OpenCode agent provider for CAPE."""

from cape.core.agents.opencode.opencode import (
    OpenCodeAgent,
    check_opencode_installed,
    convert_jsonl_to_json,
    get_opencode_env,
    iter_opencode_items,
    parse_opencode_jsonl,
)

__all__ = [
    "OpenCodeAgent",
    "check_opencode_installed",
    "convert_jsonl_to_json",
    "get_opencode_env",
    "iter_opencode_items",
    "parse_opencode_jsonl",
]
