AI-Driven Development with Claude Code
=======================================

.. index:: ai-development, claude-code, workflow, planning, worktrees

This guide documents an AI-driven development workflow using `Claude Code <https://claude.ai/code>`_, Anthropic's CLI for Claude. The approach emphasizes planning, quality gates, and parallel development to ship faster while maintaining code quality.

Why Claude Code for Development
-------------------------------

Claude Code excels at research and planning compared to other AI development tools. While tools like Cursor are catching up, Claude Code provides superior capabilities for:

- **Understanding codebases**: Deep exploration across files and dependencies
- **Research and discovery**: Using tools to investigate problems thoroughly
- **Producing accurate plans**: Detailed implementation strategies that need minimal adjustment
- **Iterative refinement**: Conversations that build understanding over time

This workflow separates **planning and discovery** from **implementation**. By treating these as distinct phases, you gain flexibility: plan on mobile, implement on your laptop, or queue up work for later.

The Planning Workflow
---------------------

Starting a Feature
~~~~~~~~~~~~~~~~~~

Begin with a prompt that describes the problem you're solving. Use **plan mode** with **ultrathink** for best results::

    claude --plan --ultrathink

In plan mode, Claude will:

1. Explore the codebase to understand existing patterns
2. Research the problem space
3. Draft an implementation plan
4. Iterate based on your feedback

Iterating on Plans
~~~~~~~~~~~~~~~~~~

Plans rarely emerge perfect on the first attempt. Iterate by:

- Asking clarifying questions
- Requesting alternatives
- Adjusting scope
- Adding constraints

Once satisfied, you have two options for preserving the plan:

**Option 1: Write to disk**

For immediate implementation, save the plan as markdown::

    # Ask Claude to save the plan
    "Please write this plan to docs/plans/feature-name.md"

**Option 2: Create a GitHub issue**

For deferred work or team visibility::

    # Ask Claude to create an issue
    "Please create a GitHub issue for this feature using the gh CLI"

The GitHub issue approach provides a powerful decoupling point — you can plan from anywhere (even mobile via GitHub's interface) and implement later.

Asynchronous Planning via GitHub
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

GitHub issues enable planning conversations without being at your terminal:

1. Create an issue describing a problem
2. Discuss approaches in comments (Claude can respond via GitHub Actions)
3. Refine until the plan is solid
4. Pick up the issue for implementation when ready

This allows multiple planning threads to run simultaneously while you focus implementation time on execution.

Quality Gates as AI Guardrails
------------------------------

Pre-commit hooks are the **moat around your software castle**. They ensure AI-generated code meets your standards before it enters the repository.

The Critical Rule
~~~~~~~~~~~~~~~~~

**Never allow Claude to bypass git hooks.** Configure Claude Code to prevent the ``--no-verify`` flag:

.. code-block:: json

    // .claude/settings.local.json
    {
      "permissions": {
        "deny": [
          "Bash(git commit:*--no-verify*)",
          "Bash(git push:*--no-verify*)"
        ]
      }
    }

For detailed Claude Code settings configuration, see the `official documentation <https://docs.anthropic.com/en/docs/claude-code>`_.

Why This Matters
~~~~~~~~~~~~~~~~

When Claude implements a feature and attempts to commit:

1. Pre-commit hooks run (linting, formatting, type checking, tests)
2. If hooks fail, Claude must fix the issues
3. This creates a feedback loop where Claude corrects its own mistakes
4. You spend less time pointing out problems

This is where AI significantly reduces your workload — instead of reviewing and requesting fixes, the hooks enforce standards automatically.

What to Include in Pre-Commit Hooks
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Build a fast feedback loop. Every check should run quickly enough that Claude (and you) aren't waiting:

- **Linting** — Ruff for Python, ESLint for JavaScript/TypeScript
- **Formatting** — Ruff format, Prettier
- **Type checking** — mypy, TypeScript
- **Fast tests** — Unit tests, not integration tests
- **Security checks** — Detect secrets, validate syntax

.. seealso::

   :doc:`../4-guides/code-quality` covers the full Lefthook configuration for this project.

The goal: **shippable code by the time pre-commit succeeds**. This means finding ways to run critical checks fast enough to include in hooks.

Parallel Development with Worktrees
-----------------------------------

The Problem
~~~~~~~~~~~

Running multiple Claude sessions on the same codebase creates conflicts:

- File changes collide
- Git state becomes confused
- Context switches between features become painful

The Solution: Git Worktrees
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Git worktrees allow multiple working directories from a single repository. Each worktree has its own branch and working state, completely isolated from others.

This project includes helper scripts in ``bin/``:

**Creating a new worktree**::

    # From your main repo directory
    . bin/worktree-new feature-branch

This script:

1. Creates a worktree at ``../project-name--feature-branch/``
2. Copies configuration files (``.env``, ``.envrc``, ``.claude/settings.local.json``)
3. Installs dependencies
4. Changes to the new directory

**Removing a worktree**::

    # From within the worktree
    . bin/worktree-remove

This script:

1. Checks for uncommitted changes (prevents accidental data loss)
2. Displays local Claude settings (in case you want to preserve permissions)
3. Removes the worktree and deletes the branch

Understanding Serial vs. Parallel Work
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Not all work can be parallelized. Consider:

**Parallel-safe:**

- Independent features
- Bug fixes in unrelated areas
- Documentation updates
- Test additions

**Requires serial work:**

- Changes to shared infrastructure
- Database migrations that conflict
- Core API changes affecting multiple features

Familiarity with your codebase helps identify what can run in parallel. When in doubt, work serially.

Alternative: Claude Squad
~~~~~~~~~~~~~~~~~~~~~~~~~

For more sophisticated parallel session management, consider `Claude Squad <https://github.com/smol-ai/claude-squad>`_. It combines tmux with worktrees to manage multiple Claude sessions with:

- Terminal multiplexing
- Session persistence
- Visual status tracking

GitHub Integration
------------------

The Complete Loop
~~~~~~~~~~~~~~~~~

A mature workflow connects planning, implementation, and review:

1. **Planning terminals** — Claude sessions creating GitHub issues
2. **Implementation terminals** — Claude sessions reading issues and writing code
3. **Review automation** — Claude Code GitHub Action reviewing PRs

Creating Issues with Claude
~~~~~~~~~~~~~~~~~~~~~~~~~~~

When planning produces actionable work::

    "Create a GitHub issue for this feature with the implementation plan"

Claude will use ``gh issue create`` with:

- Clear title
- Problem description
- Implementation steps
- Acceptance criteria

PR Review with Claude Code
~~~~~~~~~~~~~~~~~~~~~~~~~~

Claude Code offers a GitHub Action for automated PR reviews. This provides:

- Code review comments
- Suggestions for improvements
- Identification of potential issues

For setup instructions, see the `Claude Code GitHub Action documentation <https://docs.anthropic.com/en/docs/claude-code>`_.

Putting It Together
-------------------

The Complete Workflow
~~~~~~~~~~~~~~~~~~~~~

1. **Plan** — Start Claude in plan mode with ultrathink, describe the problem
2. **Iterate** — Refine the plan until it's solid
3. **Capture** — Create a GitHub issue or save to disk
4. **Isolate** — Create a worktree for the feature
5. **Implement** — Point Claude at the issue, let it work
6. **Gate** — Pre-commit hooks enforce quality
7. **Ship** — Push branch, create PR, automated review

The Operator Mindset
~~~~~~~~~~~~~~~~~~~~

With this workflow, you become an **operator** orchestrating AI activity rather than writing every line yourself:

- Set up strong guarantees (hooks, tests, types)
- Let AI meet those requirements
- Don't tell Claude what's wrong — let the tools tell it
- Focus on architecture and direction

Multiple terminals can run simultaneously:

- 2-3 creating GitHub issues from planning conversations
- 2-3 implementing issues in separate worktrees
- Background: PR reviews running automatically

The bottleneck shifts from "writing code" to "understanding what can be parallelized" — a much more leveraged use of your time.

Building Your Moat
~~~~~~~~~~~~~~~~~~

The stronger your quality gates, the more you can trust AI output:

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Investment
     - Payoff
   * - Fast test suite
     - Catch bugs before commit
   * - Strict type checking
     - Eliminate type errors automatically
   * - Comprehensive linting
     - Consistent code style, no bike-shedding
   * - Security checks
     - Prevent secrets and vulnerabilities
   * - Pre-commit enforcement
     - AI fixes its own issues

Each investment compounds. A 2-minute pre-commit that catches 80% of issues saves hours of review time across hundreds of commits.

Quick Reference
---------------

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Task
     - Command
   * - Start planning session
     - ``claude --plan --ultrathink``
   * - Create worktree
     - ``. bin/worktree-new branch-name``
   * - Remove worktree
     - ``. bin/worktree-remove``
   * - Create GitHub issue
     - ``gh issue create --title "..." --body "..."``
   * - Run pre-commit manually
     - ``lefthook run pre-commit``
   * - List worktrees
     - ``git worktree list``
