# AGENTS.md

## Project

PwedePa is a self-hosted issue and request tracker for small trusted groups and personal projects.

- Requests are intake. Issues are accepted work. A Request can be raised into a new Issue, and both stay separate records.
- Status: design phase. The first build is a working v1, not a prototype.
- The stack, package name, and Python floor are set in `pyproject.toml`. One service serves the responsive PWA, backed by SQLite.
- Real WebAuthn passkeys from the start. Deployment target: one instance behind Tailscale Funnel.
- License: see `LICENSE.md`.

## Layout

One root `AGENTS.md` only. Do not add nested `AGENTS.md` files unless a package needs rules that differ from this file.

- The application package is `pwedepa/`. Split it into subpackages by job as features land.
- The web shell lives in `pwedepa/web/`: Flask routes in `routes/`, Jinja templates in `templates/`, and PWA files in `static/`. Its tests live in `tests/web/`. Run it with `python -m pwedepa.web`.
- Request and Issue pages live in `routes/records.py`. Every record write routes through `pwedepa.core`.
- Sharing, notifications, settings, admin, and demo entry live in named modules under `routes/`.
- Share access uses a share-scoped actor. A link never widens a signed-in user's ordinary record access.
- Settled design decisions live in `docs/design.md`. Update it in the same change that changes a design pick.
- Repository gates and tools live in `scripts/`. Their tests live in `tests/scripts/`.
- The workflow set lives in `.github/workflows/`. The set contract is `scripts/gate_workflows.py`.
- Update this file in the same change that changes the layout it points to.

## Build rules

- Read the task and the code it touches first. Trace the flow end to end, then make the smallest change that fully works.
- Reuse first: an existing helper, then the standard library, then a native platform feature, then an installed dependency. Add a dependency only when it is widely adopted and fits the exact need.
- SOLID, KISS, YAGNI, and DRY all apply. Fewest files, deletion over addition, boring over clever.
- Guard clauses and early returns. One reason to change per unit. Small interfaces.
- Never simplify away trust-boundary validation, data-loss error handling, security, or accessibility.
- State lives behind a persistence layer. Core logic must not depend on SQLite-only behavior.
- Name things by convention and by what they are. Package names follow PEP 8: short, lowercase, plain words.
- After each completed feature, run a ponytail-review and publish it as a fielded report in the steering preview.

## Style

- Indent width, lint rules, and format rules are set in `ruff.toml`. Run the gates from `.github/workflows/ci.yml`, with no CLI overrides.
- Markdown rules are set in `.markdownlint-cli2.jsonc`.
- All human-facing prose gets two passes before it ships: the STE pass in `scripts/lint_prose.py`, and a humanizer pass. Keep sentences short, with one meaning each.
- Add a code comment only when the method is complex enough to need one.

## Testing

- The pull request gate is `.github/workflows/ci.yml`. Run the same steps locally before every push.
- Tests run in parallel by default (`pytest-xdist`, `-n auto` in `pyproject.toml`). Pass `-n 0` to run serially while debugging. Keep tests parallel-safe: no shared files, ports, or global state.
- New non-trivial logic (a branch, a loop, a parser, a money or security path) leaves one small runnable test. Reuse pytest and the repo fixtures.
- Ported gates keep their tests. Do not weaken or drop a test to make a run pass.
- UI changes need a screenshot check in a real browser before they count as landed.

## Commits and pull requests

- Commit subject rules are enforced by the commit-msg hook and `scripts/check_pr.py`. Follow the rules as coded there, not a copy in this file.
- One logical change per commit. Stage only files for that change.
- PR body headings are likewise checked by `scripts/check_pr.py`.
- Keep the branch pushed and its PR open. Never merge a PR from an agent session.

## Skills

Vendored skills live in `.agents/skills/`. Each imported skill carries an `UPSTREAM.md` with its source repository, pinned revision, and version. The imported set is the folders in that directory, and no others.

## Settings UI

Settings pages follow the Apple Settings pattern: a sidebar on desktop, grouped inset cards, and rows with a label plus a value, chevron, toggle, select, or slider. Lists elsewhere stay clean and utilitarian, with plain status and priority badges.
