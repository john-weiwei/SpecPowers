"""spec-kit adapter — constitution generation and task decomposition.

Note: spec-kit's constitution generation and task decomposition depend on LLM interaction.
This adapter only does:
1. Pre-flight validation (directory exists, git repo)
2. Trigger intent recording
3. Error handling

The actual generation is executed by the agent in the cognitive layer.
"""

import os
from pathlib import Path


def gen_constitution(root: Path, force: bool = False) -> None:
    """Validate prerequisites for constitution generation.

    The agent actually generates constitution.md via /speckit.constitution.
    This function validates that the environment is ready.

    Args:
        root: Project root.
        force: If True, skip existence check.
    """
    # Check constitution.md
    constitution_path = root / "constitution.md"
    if constitution_path.exists() and not force:
        print("constitution.md already exists. Use --force to regenerate.")
        return

    # Validate project is a git repo
    from bridge.core.git_util import is_git_repo
    if not is_git_repo(root):
        raise ValueError(f"'{root}' is not a git repository. Cannot generate constitution.")

    print("constitution generation ready. Agent should now call /speckit.constitution.")
    print(f"Target: {constitution_path}")
    print("Focus areas: quality, testing, UX, performance (4 categories only)")


def gen_tasks(spec_path: str) -> str:
    """Generate task decomposition template for plan.md.

    The agent merges spec-kit tasks into plan.md.
    This function returns a template the agent can fill in.

    Args:
        spec_path: Path to spec.md (for context).

    Returns:
        Task template text for plan.md.
    """
    return """## Tasks

<!-- Generated from spec-kit task decomposition, merged into plan.md -->
<!-- Each task: description, scenario pointer, acceptance criteria, dependencies, test-first flag, capability requirement -->

1. **TBD** — Define implementation tasks based on spec.md
   - Scenario: see spec.md
   - Acceptance: TBD
   - Dependencies: none
   - Test-first: no
   - Capability: conductor

> Agent: fill in tasks from /speckit.plan output, merging into this single plan.md file.
"""
