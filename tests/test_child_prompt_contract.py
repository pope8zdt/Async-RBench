"""P1-16 child prompt contract guard.

The Child system prompt is a single mode-free constant shared by the Linear and
Async arms, so it may only describe the participant-visible work contract and
the public self-check tool.  These tests pin the exact public vocabulary the
prompt is allowed to carry and the exact words it may never use (either arm's
execution vocabulary, or any evaluator-private concept such as a hidden
validator or private rule set).

Only the field-list wording lives inside a code path that was previously wrong
("exactly the listed fields" claimed the child must reproduce precisely the
listed fields); the contract is now "at least the listed fields".
"""

from __future__ import annotations

import pytest

from async_rbench.profiles.reference_scaffold_api.runtime import CHILD_SYSTEM_PROMPT


def test_report_artifact_fields_are_at_least_the_listed_fields() -> None:
    # The child must be told that its report artifact carries AT LEAST the
    # listed fields equal to the submitted evidence --- never that it must
    # reproduce exactly those fields and nothing else (a report may legitimately
    # contain extra structure).
    assert "at least the listed fields" in CHILD_SYSTEM_PROMPT
    assert "exactly the listed fields" not in CHILD_SYSTEM_PROMPT


def test_child_told_to_write_only_declared_paths() -> None:
    # Writing is confined to the paths the main agent declared; the child must
    # not fabricate sibling paths or claim files it did not produce.
    assert "at the declared path" in CHILD_SYSTEM_PROMPT
    assert "Only report files you actually produced at the declared paths" in CHILD_SYSTEM_PROMPT


def test_child_told_to_run_validate_result_before_submit() -> None:
    # The public self-check tool must be run before submit_result seals the
    # submission (Task 3: the child dry-runs the same public accept rule).
    assert "validate_result" in CHILD_SYSTEM_PROMPT
    assert "validate_result before submit_result" in CHILD_SYSTEM_PROMPT


@pytest.mark.parametrize(
    "token",
    [
        # Either arm's execution vocabulary.
        "linear",
        "async",
        "bundle",
        "leaderboard",
        "occurrence",
        # Evaluator-private concepts: a hidden validator and private rules must
        # never surface in a participant-visible prompt.
        "hidden validator",
        "private",
    ],
)
def test_prompt_does_not_mention_arm_or_evaluator_private_vocabulary(token: str) -> None:
    assert token not in CHILD_SYSTEM_PROMPT.lower()
