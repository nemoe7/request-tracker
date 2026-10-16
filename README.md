# PwedePa

PwedePa is a self-hosted tracker for requests and issues. A small trusted group uses it to file requests, raise them into issues, and share one record with a link.

## Stack

- Python and Flask, with SQLite for storage. The Python floor, the package name, and the version live in `pyproject.toml`.
- Real WebAuthn passkeys for sign-in. No passwords.
- A responsive PWA: one manifest, one service worker, and one stylesheet.
- `ruff` and `pytest` hold the code in shape.

## Run it

```sh
python -m venv .venv
.venv/bin/pip install -e .
.venv/bin/python -m pwedepa.web
```

The app answers on `http://127.0.0.1:5000`. Demo mode asks for the seat in code, so a preview needs no environment variable.

Deployment runs two containers behind Tailscale Funnel. The steps live in `docs/deploy.md`.

## Gates

`.github/workflows/ci.yml` runs the project gate:

```sh
uv run --no-sync ruff check
uv run --no-sync ruff format --check
uv run --no-sync pytest
uv run --no-sync python scripts/lint_prose.py
```

Markdown gets one more check: `markdownlint-cli2`, with the rules in `.markdownlint-cli2.jsonc`.

## Images

The Docker workflow publishes the dev image from `main` as `ghcr.io/nemoe7/pwedepa:dev`, with a second tag that names the commit: `dev-<7-char sha>`.

`compose.yml` runs the published image. `compose.dev.yml` builds this checkout for a local run.

A release goes through the **Gemini Release Draft** workflow. It reads the commits since the last release, proposes the next semver version and the notes, and waits. Approve the proposal from the Actions tab, and the workflow creates the tag. The Docker release workflow then builds that tag as `ghcr.io/nemoe7/pwedepa:<version>` and moves `latest`.

The draft needs one repository secret: `GEMINI_API_KEY`. The proposal and the approval both run by hand, and nothing else touches the release path.

## Docs

- `docs/deploy.md` — how to run the app for real.
- `docs/design.md` — the settled UI decisions.
- `docs/schema.dbml` and `docs/schema.svg` — the database shape.
- `CHANGELOG.md` — what changed, per version.
- `AGENTS.md` — the rules this repository follows.
