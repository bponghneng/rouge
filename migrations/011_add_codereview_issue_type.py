"""
Add 'codereview' to issues.type constraint.

Updates the CHECK constraint on issues.type to allow 'codereview' in addition
to the existing 'main' and 'patch' types.
"""

from yoyo import step

__depends__ = {"010_align_issue_statuses_with_worker"}

step(
    """
    ALTER TABLE issues DROP CONSTRAINT IF EXISTS issues_type_check;
    ALTER TABLE issues ADD CONSTRAINT issues_type_check
        CHECK (type IN ('main', 'patch', 'codereview'));
    """,
    """
    ALTER TABLE issues DROP CONSTRAINT IF EXISTS issues_type_check;
    ALTER TABLE issues ADD CONSTRAINT issues_type_check
        CHECK (type IN ('main', 'patch'));
    """,
)
