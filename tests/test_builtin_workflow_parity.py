"""Parity tests for the built-in workflow configs.

These tests assert that ``resolve_workflow`` applied to each built-in
:class:`WorkflowConfig` produces a pipeline whose ``step_id`` sequence
and ``is_critical`` flags match the canonical expectations documented
in the Phase 7 refactor plan.  They also guard against dotenv leakage
by explicitly unsetting ``DEV_SEC_OPS_PLATFORM`` when testing the
"platform unset" case.
"""

from __future__ import annotations

from typing import Optional

import pytest

from rouge.core.workflow.builtin_configs import (
    DIRECT_WORKFLOW_CONFIG,
    FULL_WORKFLOW_CONFIG,
    PATCH_WORKFLOW_CONFIG,
    THIN_WORKFLOW_CONFIG,
)
from rouge.core.workflow.config import WorkflowConfig
from rouge.core.workflow.resolver import resolve_workflow
from rouge.core.workflow.step_registry import get_step_registry


def _apply_platform(monkeypatch: pytest.MonkeyPatch, platform: Optional[str]) -> None:
    """Set or unset ``DEV_SEC_OPS_PLATFORM`` for a single test.

    When ``platform`` is ``None`` we explicitly delete the env var so the
    dotenv-loaded default (``github``) cannot leak into the resolver.
    """
    if platform is None:
        monkeypatch.delenv("DEV_SEC_OPS_PLATFORM", raising=False)
    else:
        monkeypatch.setenv("DEV_SEC_OPS_PLATFORM", platform)


def _expected_is_critical(slug: str) -> bool:
    """Look up the canonical ``is_critical`` value for a slug.

    The step registry is the source of truth; tests must not hard-code
    per-slug booleans.
    """
    registry = get_step_registry()
    metadata = registry.get_step_metadata_by_slug(slug)
    assert metadata is not None, f"Slug '{slug}' is not registered"
    return metadata.is_critical


# ---------------------------------------------------------------------------
# Expected step-id sequences
# ---------------------------------------------------------------------------

_FULL_BASE = [
    "fetch-issue",
    "git-branch",
    "claude-code-plan",
    "implement-plan",
    "code-quality",
    "compose-request",
]

_THIN_BASE = [
    "fetch-issue",
    "git-branch",
    "thin-plan",
    "implement-plan",
    "compose-request",
]

_PATCH_EXPECTED = [
    "fetch-patch",
    "git-checkout",
    "patch-plan",
    "implement-plan",
    "code-quality",
    "compose-commits",
]

_DIRECT_EXPECTED = [
    "fetch-issue",
    "git-prepare",
    "implement-direct",
]


def _expected_for_full(platform: Optional[str]) -> list[str]:
    if platform == "github":
        return [*_FULL_BASE, "gh-pull-request"]
    if platform == "gitlab":
        return [*_FULL_BASE, "glab-pull-request"]
    return list(_FULL_BASE)


def _expected_for_thin(platform: Optional[str]) -> list[str]:
    if platform == "github":
        return [*_THIN_BASE, "gh-pull-request"]
    if platform == "gitlab":
        return [*_THIN_BASE, "glab-pull-request"]
    return list(_THIN_BASE)


# ---------------------------------------------------------------------------
# Platform-gated workflow parity (full + thin)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("platform", ["github", "gitlab", None])
def test_full_workflow_slug_sequence(
    monkeypatch: pytest.MonkeyPatch, platform: Optional[str]
) -> None:
    """FULL_WORKFLOW_CONFIG resolves to the expected slug sequence per platform."""
    _apply_platform(monkeypatch, platform)
    steps = resolve_workflow(FULL_WORKFLOW_CONFIG)
    assert [s.step_id for s in steps] == _expected_for_full(platform)


@pytest.mark.parametrize("platform", ["github", "gitlab", None])
def test_full_workflow_critical_flags(
    monkeypatch: pytest.MonkeyPatch, platform: Optional[str]
) -> None:
    """Every resolved full-workflow step's ``is_critical`` matches the registry."""
    _apply_platform(monkeypatch, platform)
    steps = resolve_workflow(FULL_WORKFLOW_CONFIG)
    for step in steps:
        assert step.is_critical == _expected_is_critical(step.step_id), (
            f"is_critical mismatch for slug '{step.step_id}': "
            f"step reports {step.is_critical}, "
            f"registry expects {_expected_is_critical(step.step_id)}"
        )


@pytest.mark.parametrize("platform", ["github", "gitlab", None])
def test_thin_workflow_slug_sequence(
    monkeypatch: pytest.MonkeyPatch, platform: Optional[str]
) -> None:
    """THIN_WORKFLOW_CONFIG resolves to the expected slug sequence per platform."""
    _apply_platform(monkeypatch, platform)
    steps = resolve_workflow(THIN_WORKFLOW_CONFIG)
    assert [s.step_id for s in steps] == _expected_for_thin(platform)


@pytest.mark.parametrize("platform", ["github", "gitlab", None])
def test_thin_workflow_critical_flags(
    monkeypatch: pytest.MonkeyPatch, platform: Optional[str]
) -> None:
    """Every resolved thin-workflow step's ``is_critical`` matches the registry."""
    _apply_platform(monkeypatch, platform)
    steps = resolve_workflow(THIN_WORKFLOW_CONFIG)
    for step in steps:
        assert step.is_critical == _expected_is_critical(step.step_id), (
            f"is_critical mismatch for slug '{step.step_id}': "
            f"step reports {step.is_critical}, "
            f"registry expects {_expected_is_critical(step.step_id)}"
        )


# ---------------------------------------------------------------------------
# Non-gated workflow parity (patch + direct)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("platform", ["github", "gitlab", None])
def test_patch_workflow_slug_sequence(
    monkeypatch: pytest.MonkeyPatch, platform: Optional[str]
) -> None:
    """PATCH_WORKFLOW_CONFIG resolves to a fixed sequence regardless of platform."""
    _apply_platform(monkeypatch, platform)
    steps = resolve_workflow(PATCH_WORKFLOW_CONFIG)
    assert [s.step_id for s in steps] == _PATCH_EXPECTED


@pytest.mark.parametrize("platform", ["github", "gitlab", None])
def test_patch_workflow_critical_flags(
    monkeypatch: pytest.MonkeyPatch, platform: Optional[str]
) -> None:
    """Every resolved patch-workflow step's ``is_critical`` matches the registry."""
    _apply_platform(monkeypatch, platform)
    steps = resolve_workflow(PATCH_WORKFLOW_CONFIG)
    for step in steps:
        assert step.is_critical == _expected_is_critical(step.step_id), (
            f"is_critical mismatch for slug '{step.step_id}': "
            f"step reports {step.is_critical}, "
            f"registry expects {_expected_is_critical(step.step_id)}"
        )


@pytest.mark.parametrize("platform", ["github", "gitlab", None])
def test_direct_workflow_slug_sequence(
    monkeypatch: pytest.MonkeyPatch, platform: Optional[str]
) -> None:
    """DIRECT_WORKFLOW_CONFIG resolves to a fixed sequence regardless of platform."""
    _apply_platform(monkeypatch, platform)
    steps = resolve_workflow(DIRECT_WORKFLOW_CONFIG)
    assert [s.step_id for s in steps] == _DIRECT_EXPECTED


@pytest.mark.parametrize("platform", ["github", "gitlab", None])
def test_direct_workflow_critical_flags(
    monkeypatch: pytest.MonkeyPatch, platform: Optional[str]
) -> None:
    """Every resolved direct-workflow step's ``is_critical`` matches the registry."""
    _apply_platform(monkeypatch, platform)
    steps = resolve_workflow(DIRECT_WORKFLOW_CONFIG)
    for step in steps:
        assert step.is_critical == _expected_is_critical(step.step_id), (
            f"is_critical mismatch for slug '{step.step_id}': "
            f"step reports {step.is_critical}, "
            f"registry expects {_expected_is_critical(step.step_id)}"
        )


# ---------------------------------------------------------------------------
# Aggregate sanity check across all four built-in configs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "config",
    [
        FULL_WORKFLOW_CONFIG,
        THIN_WORKFLOW_CONFIG,
        PATCH_WORKFLOW_CONFIG,
        DIRECT_WORKFLOW_CONFIG,
    ],
    ids=["full", "thin", "patch", "direct"],
)
def test_builtin_config_resolves_without_errors(
    monkeypatch: pytest.MonkeyPatch, config: WorkflowConfig
) -> None:
    """Every built-in config must resolve cleanly for each gated platform value."""
    for platform in ("github", "gitlab", None):
        _apply_platform(monkeypatch, platform)
        steps = resolve_workflow(config)
        assert len(steps) >= 1, (
            f"Config '{config.type_id}' produced an empty pipeline " f"for platform={platform!r}"
        )
