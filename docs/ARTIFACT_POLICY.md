# Artifact Policy

This document defines the artifact system policy for workflow steps in Rouge. All workflow steps must adhere to these policies to ensure consistent, reliable, and maintainable cross-step communication.

## Overview

Workflow artifacts are typed, filesystem-backed data structures that enable workflow steps to communicate without tight coupling. The artifact system provides a single source of truth for step outputs and enforces explicit dependency declarations through the step registry.

## Core Policies

### 1. Source of Truth: Artifacts Are the Single Source of Truth for Cross-Step Data

**Policy**: Workflow steps must not pass data to each other through context dictionaries, global variables, or other ad-hoc mechanisms. All cross-step data sharing must use typed artifacts persisted to the ArtifactStore.

**Rationale**: Using artifacts as the single source of truth ensures data persistence, enables step recovery, supports independent step execution, and provides a clear audit trail.

**Requirements**:
- Steps must write all outputs to artifacts before completing
- Steps must read all inputs from artifacts (not from context dictionaries)
- Context dictionaries may only contain workflow metadata (workflow_id, issue_id, etc.)
- All cross-step data must be typed using Pydantic artifact models

**Example Violation**:
```python
# BAD: Passing data through context dictionary
def run(self, context: WorkflowContext) -> StepResult:
    classify_data = context.data.get("classify_data")  # Wrong!
    ...
```

**Correct Approach**:
```python
# GOOD: Reading data from artifact
def run(self, context: WorkflowContext) -> StepResult:
    classify_data = context.load_required_artifact(
        "classify", ClassifyArtifact, lambda a: a.classify_data
    )
    ...
```

### 2. Cross-Step Reads: All Cross-Step Reads Must Use Artifacts

**Policy**: When a workflow step needs data produced by a previous step, it must load that data from the ArtifactStore using the appropriate artifact type. Direct access to other steps' internal state is prohibited.

**Rationale**: Enforcing artifact-based reads ensures steps remain loosely coupled, testable in isolation, and resilient to implementation changes in upstream steps.

**Requirements**:
- Use `context.load_required_artifact(artifact_type, model_class, extract_fn)` for required dependencies
- Use `context.load_optional_artifact(artifact_type, model_class, extract_fn)` for optional dependencies
- Never access step instances or internal state from other steps
- Declare all artifact dependencies in the step registry

**Example** (Required Dependency):
```python
# ClassifyStep depends on FetchIssueStep's output
def run(self, context: WorkflowContext) -> StepResult:
    # Load required artifact - raises RuntimeError if missing
    issue = context.load_required_artifact(
        "fetch-issue", FetchIssueArtifact, lambda a: a.issue
    )

    # Classify the issue...
    classify_data = self._classify_issue(issue, context.adw_id)

    # Write output artifact
    artifact = ClassifyArtifact(
        workflow_id=context.adw_id,
        classify_data=classify_data.data,
    )
    context.artifact_store.write_artifact(artifact)
    return StepResult.ok(classify_data.data)
```

### 3. Context Scope: Context Is Limited to Current Step Execution

**Policy**: The `WorkflowContext` object must only contain workflow metadata and provide access to the ArtifactStore. It must not be used to pass step output data between steps.

**Rationale**: Limiting context scope prevents implicit dependencies, ensures clear data flow, and maintains the artifact system as the single source of truth.

**Requirements**:
- Context may only contain: `workflow_id`, `adw_id`, `issue_id`, `artifact_store` (ArtifactStore)
- Context must not contain step output data (e.g., no `context.classify_data`)
- Context provides convenience methods for loading artifacts (`load_required_artifact`, `load_optional_artifact`)
- All step outputs must be written to artifacts, not stored in context

**Allowed Context Usage**:
```python
# GOOD: Using context for metadata and artifact access
workflow_id = context.adw_id
issue_id = context.require_issue_id
issue = context.load_required_artifact(
    "fetch-issue", FetchIssueArtifact, lambda a: a.issue
)
```

**Prohibited Context Usage**:
```python
# BAD: Storing step output in context
context.data["classify_result"] = classify_data  # Wrong!
context.plan_data = plan_data  # Wrong!
```

### 4. Dependency Typing: Dependencies Are Classified by Kind

**Policy**: All artifact dependencies must be classified into one of three kinds: `required`, `optional`, or `ordering-only`. The step registry must declare dependency kinds for all non-required dependencies.

**Dependency Kinds**:

- **Required** (default): Step reads and requires the artifact. Workflow aborts if missing.
  - Use `context.load_required_artifact(artifact_type, model_class, extract_fn)` to load
  - Raises `RuntimeError` if artifact doesn't exist

- **Optional**: Step reads the artifact but gracefully handles its absence
  - Use `context.load_optional_artifact(artifact_type, model_class, extract_fn)` to load
  - Returns `None` if artifact doesn't exist
  - Step must handle `None` case without failing

- **Ordering-only**: Step doesn't read the artifact, just requires ordering constraint
  - Does not call `load_required_artifact` or `load_optional_artifact`
  - Used to enforce execution order without data dependency
  - Common for steps that need side effects to complete first

**Requirements**:
- Declare `dependency_kinds` in registry for optional/ordering-only dependencies
- Required dependencies need no explicit declaration (they're the default)
- Step implementation must match registry declarations
- Tests must verify correct dependency handling

**Examples**:

**Required Dependency**:
```python
# Step registry declares fetch-issue as required (default)
registry.register(
    ClassifyStep,
    slug="classify",
    dependencies=["fetch-issue"],
    outputs=["classify"],
)

# Step implementation loads required artifact
def run(self, context: WorkflowContext) -> StepResult:
    issue = context.load_required_artifact(
        "fetch-issue", FetchIssueArtifact, lambda a: a.issue
    )
    # Use issue for classification...
```

**Optional Dependency**:
```python
# Step registry declares compose-request as optional
registry.register(
    GhPullRequestStep,
    slug="gh-pull-request",
    dependencies=["compose-request"],
    outputs=["gh-pull-request"],
    dependency_kinds={"compose-request": "optional"},
)

# Step implementation handles missing artifact gracefully
def run(self, context: WorkflowContext) -> StepResult:
    pr_details = context.load_optional_artifact(
        "compose-request",
        ComposeRequestArtifact,
        lambda a: {"title": a.title, "summary": a.summary},
    )

    if pr_details is None:
        logger.info("PR creation skipped: no PR details available")
        return StepResult.ok(None)

    # Create PR with details...
```

**Ordering-Only Dependency**:
```python
# Step registry declares implement as ordering-only
registry.register(
    CodeQualityStep,
    slug="code-quality",
    dependencies=["implement"],
    outputs=["code-quality"],
    dependency_kinds={"implement": "ordering-only"},
)

# Step implementation does NOT load implement artifact
def run(self, context: WorkflowContext) -> StepResult:
    # No artifact loading - just ensures implementation happened first
    # Quality checks run directly on repository files
    request = ClaudeAgentTemplateRequest(
        agent_name=AGENT_CODE_QUALITY_CHECKER,
        slash_command="/adw-code-quality",
        args=[],
        # ...
    )
    # Run checks on files...
```

### 5. Failure Semantics: Fail Fast with Clear Errors

**Policy**: Steps must fail immediately with clear error messages when required artifacts are missing or invalid. Optional artifacts may be missing without causing failure.

**Rationale**: Clear failure semantics prevent cascading errors, simplify debugging, and ensure workflows fail at the earliest point of invalidity.

**Requirements**:
- Required artifact loading must raise exceptions when artifacts are missing
- Error messages must identify the missing artifact type and step
- Optional artifact loading must return `None` for missing artifacts (not raise)
- Validation errors must include the artifact type and validation failure details
- Steps must not suppress or swallow artifact loading errors

**Example** (Required Artifact Missing):
```python
# Loading required artifact that doesn't exist
issue = context.load_required_artifact(
    "fetch-issue", FetchIssueArtifact, lambda a: a.issue
)
# Raises: RuntimeError: Required artifact 'fetch-issue' not found for workflow ...
```

**Example** (Invalid Artifact Data):
```python
# Artifact exists but fails validation
classify_data = context.load_required_artifact(
    "classify", ClassifyArtifact, lambda a: a.classify_data
)
# Raises: ValueError: Failed to validate artifact classify: <validation details>
```

**Example** (Optional Artifact Missing - No Error):
```python
# Loading optional artifact that doesn't exist
pr_details = context.load_optional_artifact(
    "compose-request",
    ComposeRequestArtifact,
    lambda a: {"title": a.title},
)
# Returns: None (no exception raised)
```

### 6. Registry Alignment: Step Declarations Must Match Runtime Behavior

**Policy**: The step registry declarations (dependencies, outputs, dependency_kinds) must accurately reflect the step's runtime behavior. Mismatches between registry and implementation are bugs.

**Rationale**: Registry alignment enables accurate dependency resolution, supports independent step execution, and provides reliable workflow validation.

**Requirements**:
- Registry `dependencies` must list all artifacts the step loads (required, optional, or ordering-only)
- Registry `outputs` must list all artifacts the step writes
- Registry `dependency_kinds` must match step's actual loading patterns:
  - If step uses `load_required_artifact()`, dependency is required (default)
  - If step uses `load_optional_artifact()`, dependency must be marked `"optional"`
  - If step doesn't load artifact, dependency must be marked `"ordering-only"`
- Tests must verify registry alignment

**Example** (Aligned Registry and Implementation):
```python
# Registry declares dependencies and kinds
registry.register(
    GhPullRequestStep,
    slug="gh-pull-request",
    dependencies=["compose-request"],
    outputs=["gh-pull-request"],
    dependency_kinds={"compose-request": "optional"},  # Matches implementation
)

# Implementation uses load_optional_artifact (matches registry)
def run(self, context: WorkflowContext) -> StepResult:
    pr_details = context.load_optional_artifact(
        "compose-request",
        ComposeRequestArtifact,
        lambda a: {"title": a.title},
    )
    # ...
```

**Example** (Registry/Implementation Mismatch - Bug):
```python
# BAD: Registry says optional, but implementation treats as required
registry.register(
    BadStep,
    dependencies=["some-artifact"],
    dependency_kinds={"some-artifact": "optional"},  # Says optional...
)

def run(self, context: WorkflowContext) -> StepResult:
    data = context.load_required_artifact(
        "some-artifact", SomeArtifact, lambda a: a.data
    )  # ...but loads as required!
    # This is a bug - registry and implementation don't match
```

### 7. Write-Before-Complete: Artifacts Must Be Written Before Step Completes

**Policy**: Steps must write all output artifacts to the ArtifactStore before returning a successful `StepResult`. Artifacts must not be written after the step completes or in finally blocks.

**Rationale**: Writing artifacts before completion ensures downstream steps can safely depend on artifact availability, enables workflow recovery, and maintains consistency.

**Requirements**:
- Call `context.artifact_store.write_artifact(artifact)` before returning `StepResult.ok()`
- Do not write artifacts in exception handlers or finally blocks
- If step fails, do not write output artifacts (abort before writing)
- Ensure all declared outputs are written on success

**Example** (Correct Artifact Writing):
```python
def run(self, context: WorkflowContext) -> StepResult:
    # Perform step work...
    classify_data = self._classify_issue(issue, context.adw_id)

    # Write output artifact BEFORE returning success
    artifact = ClassifyArtifact(
        workflow_id=context.adw_id,
        classify_data=classify_data.data,
    )
    context.artifact_store.write_artifact(artifact)  # Write before return

    # Return success after artifact is written
    return StepResult.ok(classify_data.data)
```

**Example** (Incorrect - Writing After Return):
```python
def run(self, context: WorkflowContext) -> StepResult:
    classify_data = self._classify_issue(issue, context.adw_id)

    # BAD: Returning before writing artifact
    result = StepResult.ok(classify_data.data)

    artifact = ClassifyArtifact(...)
    context.artifact_store.write_artifact(artifact)  # Too late! Already returned.

    return result
```

### 8. Test Contract: All Tests Must Provide ArtifactStore

**Policy**: All workflow step tests must provide an `ArtifactStore` in the `WorkflowContext`. Tests must populate required input artifacts before executing the step under test.

**Rationale**: Providing ArtifactStore in tests ensures steps are tested with realistic artifact loading patterns, validates registry alignment, and prevents test/production behavioral divergence.

**Requirements**:
- Test fixtures must create an `ArtifactStore` instance
- Test fixtures must pre-populate required input artifacts
- Tests must verify output artifacts are written correctly
- Tests must verify optional artifact handling (both present and absent cases)
- Tests must use real artifact models (not mocks) for validation

**Example** (Test Fixture with ArtifactStore):
```python
import pytest
from pathlib import Path
from rouge.core.workflow.artifacts import ArtifactStore, FetchIssueArtifact
from rouge.core.workflow.step_base import WorkflowContext

@pytest.fixture
def workflow_context(tmp_path: Path) -> WorkflowContext:
    """Create workflow context with ArtifactStore for testing."""
    workflow_id = "test-workflow-123"
    issue_id = 123

    # Create ArtifactStore with temp directory
    store = ArtifactStore(workflow_id=workflow_id, base_path=tmp_path)

    # Pre-populate required artifacts
    fetch_artifact = FetchIssueArtifact(
        workflow_id=workflow_id,
        issue=Issue(id=issue_id, description="Test issue"),
    )
    store.write_artifact(fetch_artifact)

    # Create context with store
    return WorkflowContext(
        workflow_id=workflow_id,
        adw_id=workflow_id,
        issue_id=issue_id,
        artifact_store=store,
    )

def test_classify_step(workflow_context: WorkflowContext) -> None:
    """Test ClassifyStep reads fetch-issue and writes classify artifact."""
    step = ClassifyStep()

    # Run step
    result = step.run(workflow_context)

    # Verify success
    assert result.success

    # Verify output artifact was written
    assert workflow_context.artifact_store.artifact_exists("classify")

    # Verify artifact content
    classify_artifact = workflow_context.artifact_store.read_artifact(
        "classify", ClassifyArtifact
    )
    assert classify_artifact.classify_data is not None
```

## Dependency Kind Summary

| Kind | Registry Declaration | Loading Pattern | Missing Artifact Behavior |
|------|---------------------|-----------------|---------------------------|
| **Required** (default) | No `dependency_kinds` entry | `context.load_required_artifact()` | Raises `RuntimeError` |
| **Optional** | `{"artifact": "optional"}` | `context.load_optional_artifact()` | Returns `None` |
| **Ordering-only** | `{"artifact": "ordering-only"}` | No loading call | Not applicable (not loaded) |

## Practical Examples

### Example 1: Required Dependency (classify <- fetch-issue)

ClassifyStep requires the fetch-issue artifact to perform classification.

**Registry Declaration**:
```python
registry.register(
    ClassifyStep,
    slug="classify",
    dependencies=["fetch-issue"],  # Required dependency
    outputs=["classify"],
)
```

**Step Implementation**:
```python
def run(self, context: WorkflowContext) -> StepResult:
    # Load required artifact - fails if missing
    issue = context.load_required_artifact(
        "fetch-issue", FetchIssueArtifact, lambda a: a.issue
    )

    # Classify using issue data
    classify_data = self._classify_issue(issue, context.adw_id)

    # Write output before returning
    artifact = ClassifyArtifact(
        workflow_id=context.adw_id,
        classify_data=classify_data.data,
    )
    context.artifact_store.write_artifact(artifact)
    return StepResult.ok(classify_data.data)
```

### Example 2: Optional Dependency (gh-pull-request <- compose-request)

GhPullRequestStep prefers to use compose-request for PR metadata, but can skip PR creation if unavailable.

**Registry Declaration**:
```python
registry.register(
    GhPullRequestStep,
    slug="gh-pull-request",
    dependencies=["compose-request"],  # Declared as dependency
    outputs=["gh-pull-request"],
    dependency_kinds={"compose-request": "optional"},  # But optional
)
```

**Step Implementation**:
```python
def run(self, context: WorkflowContext) -> StepResult:
    # Load optional artifact - returns None if missing
    pr_details = context.load_optional_artifact(
        "compose-request",
        ComposeRequestArtifact,
        lambda a: {"title": a.title, "summary": a.summary},
    )

    if pr_details is None:
        # Gracefully handle missing artifact
        logger.info("PR creation skipped: no PR details available")
        return StepResult.ok(None)

    # Create PR using details
    pr_url = self._create_pull_request(pr_details["title"], pr_details["summary"])

    # Write output artifact
    artifact = GhPullRequestArtifact(
        workflow_id=context.adw_id,
        url=pr_url,
    )
    context.artifact_store.write_artifact(artifact)
    return StepResult.ok(None)
```

### Example 3: Ordering-Only Dependency (code-quality <- implement)

CodeQualityStep needs implementation to complete before running checks, but doesn't read the implement artifact - it runs quality tools directly on repository files.

**Registry Declaration**:
```python
registry.register(
    CodeQualityStep,
    slug="code-quality",
    dependencies=["implement"],  # Declared as dependency
    outputs=["code-quality"],
    dependency_kinds={"implement": "ordering-only"},  # But ordering-only
)
```

**Step Implementation**:
```python
def run(self, context: WorkflowContext) -> StepResult:
    # Does NOT load implement artifact - just needs execution order

    # Run quality checks on repository files
    request = ClaudeAgentTemplateRequest(
        agent_name=AGENT_CODE_QUALITY_CHECKER,
        slash_command="/adw-code-quality",
        args=[],
        adw_id=context.adw_id,
        issue_id=context.issue_id,
    )
    response = execute_template(request)

    # Parse results and write artifact
    quality_data = parse_and_validate_json(response.output, ...)
    artifact = CodeQualityArtifact(
        workflow_id=context.adw_id,
        output=response.output,
        tools=quality_data["tools"],
    )
    context.artifact_store.write_artifact(artifact)
    return StepResult.ok(None)
```

## Further Reading

- **Artifact Schemas**: See `src/rouge/core/workflow/artifacts.py` for all artifact type definitions
- **Step Registry**: See `src/rouge/core/workflow/step_registry.py` for registry API and validation
- **Step Base Class**: See `src/rouge/core/workflow/step_base.py` for `WorkflowStep` and `WorkflowContext` APIs
- **Testing Patterns**: See `tests/` for example test fixtures and artifact setup patterns
