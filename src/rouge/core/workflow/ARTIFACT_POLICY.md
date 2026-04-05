# Artifact Policy

## Dependency Kinds

- **required** (implicit default): the step cannot proceed without this artifact; its absence raises `StepInputError`.
- **optional**: the step gracefully continues when the artifact is absent; its absence returns `None`.
- **ordering-only**: exists solely to enforce DAG execution order; the step never reads the artifact as data.

## Policy

1. **ArtifactStore is always available.** `WorkflowContext.artifact_store` is a required, non-optional field. Every step can safely call `context.artifact_store` without a None guard.

2. **Use `load_required_artifact` for declared required dependencies.** If the artifact file does not exist, `load_required_artifact` raises `StepInputError` with a clear message identifying the missing artifact and the step that should have produced it.

3. **Use `load_optional_artifact` for declared optional dependencies.** If the artifact file does not exist, `load_optional_artifact` returns `None` and logs at DEBUG level. The step must handle the `None` case explicitly.

4. **Ordering-only dependencies are never read as artifacts.** A step whose registry entry marks a dependency as `ordering-only` must not call any artifact-loading helper for that dependency. The dependency exists only to guarantee correct DAG sequencing.

5. **Steps must not access `context.issue` directly for cross-step issue data.** Issue data produced by `FetchIssueStep` is authoritative only via the `fetch-issue` artifact. Downstream steps that need issue fields must load them through `load_required_artifact` (or `load_optional_artifact`) rather than reading `context.issue`, which may be `None` in standalone workflows.

6. **`WorkflowContext.data` is for transient orchestration flags only.** Examples: `review_is_clean`, in-progress status bits. It is not a substitute for durable step outputs. Persistent step results must be written as typed artifacts via `artifact_store.write_artifact`.

7. **All steps write their output artifact unconditionally.** A step must not guard its `write_artifact` call behind a conditional. If the step's `run` method succeeds, it writes its artifact. This ensures downstream steps and the artifact CLI commands always find a consistent artifact on disk.

8. **`code-quality` and `compose-request` use optional dependency on `implement`.**
   These steps formerly declared an `ordering-only` dependency on `implement` purely for DAG sequencing. They now declare an `optional` dependency instead, allowing them to read the implement artifact for repo-targeting information (e.g. working directory, repository path) when it is available. When the implement artifact is absent, these steps continue to function without it.

