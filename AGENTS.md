# AGENTS.md

## Project

PwedePa is a self-hosted issue and request tracker for small trusted groups and personal projects.

- Requests are intake. Issues are accepted work. A Request can be raised into a new Issue, and both stay separate records.
- Status: design phase. The first build is a working v1, not a prototype.
- Stack: Python, SQLite, one service, and a served responsive PWA. Real WebAuthn passkeys from the start.
- Deployment target: one instance behind Tailscale Funnel.
- License: see `LICENSE.md`.

## Layout

One root `AGENTS.md` only. Do not add nested `AGENTS.md` files unless a package needs rules that differ from this file.

Planned layout, created with the first scaffold:

- `app/` for the application, split into subpackages by job: auth, users, permissions, requests, issues, comments, attachments, notifications, domains, sharing, activity, audit, admin, and db.
- `scripts/` for repository gates and tools, adapted from daedalus `scripts/` and clankers `maintenance/`.
- `tests/` for pytest tests.
- `.github/workflows/` for CI. Six early workflows land with the scaffold: CI, CodeQL, secret scan, workflow security, dependency review, and PR check. Container scans land with the first Dockerfile.

## Build rules

- Read the task and the code it touches first. Trace the flow end to end, then make the smallest change that fully works.
- Reuse first: an existing helper, then the standard library, then a native platform feature, then an installed dependency. Add a dependency only when it is widely adopted and fits the exact need.
- SOLID, KISS, YAGNI, and DRY all apply. Fewest files, deletion over addition, boring over clever.
- Guard clauses and early returns. One reason to change per unit. Small interfaces.
- Never simplify away trust-boundary validation, data-loss error handling, security, or accessibility.
- State lives behind a persistence layer. Domain logic must not depend on SQLite-only behavior.
- After each completed feature, run a ponytail-review and publish it as a fielded report in the steering preview.

## Style

- 2-space indent in all files, including Python and YAML.
- Python: Ruff defaults plus this repo's `ruff.toml` when it lands. Gates are `ruff check` and `ruff format --check`, with no CLI overrides.
- Markdown: markdownlint defaults, MD013 off, MD060 on.
- Human-facing text follows ASD-STE100: short sentences, one meaning per sentence, no filler.
- Add a code comment only when the method is complex enough to need one.

## Testing

- Run the repo gate before every push: Ruff, pytest, and markdownlint over changed files.
- New non-trivial logic (a branch, a loop, a parser, a money or security path) leaves one small runnable test. Reuse pytest and the repo fixtures.
- Ported gates keep their tests: `scripts/pr_snapshot.py`, `scripts/check_pr.py`, and `scripts/gate_workflows.py` land with the scaffold.
- UI changes need a screenshot check in a real browser before they count as landed.
- Never weaken or drop a test to make a run pass.

## Commits and pull requests

- Commit subjects use Conventional Commits: `<type>[optional scope]: <description>`, one line, at most 72 characters, lowercase start, no final period, and no body. The commit-msg hook enforces this.
- One logical change per commit. Stage only files for that change.
- PR bodies use these headings, in order: Summary, Changes, Validation, Breaking Changes, and Related. The last two may stay out when they hold nothing.
- Keep the branch pushed and its PR open. Never merge a PR from an agent session.

## Skills

Vendored skills live in `.agents/skills/`. Each imported skill carries an `UPSTREAM.md` with its source repository, pinned revision, and version.

- `arena-skill`: steering inbox, reports, and the gate.
- `humanizer`, `asd-ste100`: prose rules for human-facing text.
- `ponytail`, `ponytail-review`, `ponytail-audit`: smallest-change build and review discipline. Only these three ponytail skills are imported.

## Settings UI

Settings pages follow the Apple Settings pattern: a sidebar on desktop, grouped inset cards, and rows with a label plus a value, chevron, toggle, select, or slider. Lists elsewhere stay clean and utilitarian, with plain status and priority badges.

## ARENA.md

`ARENA.md` also governs agent work in this repository. On a collision, `ARENA.md` wins over this file.
