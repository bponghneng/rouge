"""Prepare the git workspace by delegating to the appropriate git step.

This step inspects ``context.issue.branch`` to decide how to set up the
repository:

* **Branch is set** -- delegate to :class:`GitCheckoutStep` which checks out
  the existing branch and pulls latest changes.
* **Branch is unset** (``None`` or whitespace-only) -- delegate to
  :class:`GitBranchStep` which creates a fresh feature branch from the
  default branch.

The delegate's :class:`StepResult` (and its artifact) are returned directly.
"""

from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.steps.git_branch_step import GitBranchStep
from rouge.core.workflow.steps.git_checkout_step import GitCheckoutStep
from rouge.core.workflow.types import StepResult


class GitPrepareStep(WorkflowStep):
    """Route to GitBranchStep or GitCheckoutStep based on issue branch state.

    Produces either a ``git-branch`` or ``git-checkout`` artifact depending on
    which delegate is invoked.
    """

    @property
    def name(self) -> str:
        return "Preparing git workspace"

    @property
    def is_critical(self) -> bool:
        return True

    def run(self, context: WorkflowContext) -> StepResult:
        """Delegate to the appropriate git step.

        Args:
            context: Workflow context containing the issue with optional branch

        Returns:
            StepResult from the delegate step
        """
        branch = context.issue.branch if context.issue else None
        if branch and branch.strip():
            return GitCheckoutStep().run(context)
        return GitBranchStep().run(context)
