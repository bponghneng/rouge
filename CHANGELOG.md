# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- **BREAKING**: `WorkflowContext.artifact_store` is now required (was `Optional[ArtifactStore]`)
  - All workflow execution modes (`rouge workflow run`, `rouge-adw`, `rouge-worker`) automatically provide an `ArtifactStore` instance
  - Custom workflow implementations must provide an `ArtifactStore` when creating `WorkflowContext`

### Added

- New `WorkflowContext.load_required_artifact()` method for loading mandatory artifacts
  - Raises `RuntimeError` if artifact is missing
  - Does not store value in `context.data` (callers manage their own variables)
  - Use when workflow step cannot proceed without the artifact

- New `WorkflowContext.load_optional_artifact()` method for loading optional artifacts
  - Returns `None` if artifact is missing (with debug log)
  - Does not store value in `context.data` (callers manage their own variables)
  - Use when workflow step can proceed with or without the artifact

### Deprecated

- `WorkflowContext.load_artifact_if_missing()` is now deprecated
  - Kept for gradual migration of existing steps
  - New code should use `load_required_artifact()` or `load_optional_artifact()` instead
  - This method will be removed in a future release after all workflow steps migrate

### Migration Guide

If you have custom workflow steps or are creating `WorkflowContext` instances directly:

1. **Provide ArtifactStore**: Ensure `artifact_store` is provided when creating `WorkflowContext`
   ```python
   # Before (no longer valid)
   context = WorkflowContext(adw_id="abc123", artifact_store=None)

   # After (required)
   from rouge.core.workflow.artifacts import ArtifactStore
   store = ArtifactStore(workflow_id="abc123", base_path=base_path)
   context = WorkflowContext(adw_id="abc123", artifact_store=store)
   ```

2. **Update artifact loading in custom steps**:
   ```python
   # Old pattern (deprecated)
   value = context.load_artifact_if_missing(
       "my_key", "my-artifact", MyArtifact, lambda a: a.data
   )

   # New pattern for required artifacts
   value = context.load_required_artifact(
       "my-artifact", MyArtifact, lambda a: a.data
   )

   # New pattern for optional artifacts
   value = context.load_optional_artifact(
       "my-artifact", MyArtifact, lambda a: a.data
   )
   ```

3. **Note the behavior difference**: The new methods do NOT store loaded values in `context.data`. Manage variables in your step's local scope instead.
