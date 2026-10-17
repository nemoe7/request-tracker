# PwedePa

PwedePa is a self-hosted tracker for requests and issues. A small trusted group
files requests, raises them into issues, and shares one record with a link.

## Stack

- Python and Flask, with SQLite for storage.
- Passkey sign-in through WebAuthn. No passwords.
- A responsive PWA: one manifest, one service worker, and one stylesheet.

## Run it

```sh
uv sync --locked
uv run python -m pwedepa.web
```

The app answers on `http://127.0.0.1:5000` and prints one admin sign-up token on
the first start.

To clear the requests and issues and keep the accounts, run
`uv run python scripts/reset_records.py pwedepa.db`. It prints what it removed,
and every passkey still signs in.

## Images

The **Docker** workflow publishes `ghcr.io/nemoe7/pwedepa` for linux/amd64 and
linux/arm64. A passing CI run on `main` tags the image `dev`, and an approved
release draft tags the version and `latest`. `compose.yml` runs the published
image, and `compose.dev.yml` builds this checkout.

## Checks

CI runs `ruff`, `pytest`, `scripts/lint_prose.py`, and `markdownlint-cli2`.

## Docs

- `docs/deploy.md` — how to run the app for real.
- `docs/design.md` — the settled UI decisions.
- `docs/schema.dbml` — the database shape. `scripts/render_schema.py` writes
  `docs/schema.md` from it.
- `CHANGELOG.md` — what changed, per version.
- `AGENTS.md` — the rules this repository follows.

## License

The [nemoe7 Noncommercial and Public-Interest License 1.2.0](LICENSE.md) covers
this project. Read it before you use the code.
