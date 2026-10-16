# Changelog

This file records all notable changes to this project.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-10-16

### Added

- Passkey sign-in and enrollment, with admin user management and an audit trail.
- Requests as intake and issues as accepted work. A request raises into a new issue.
- Status moves, field edits, comments, and archives on both record types.
- Share links with expiry, permissions, and revoke.
- Retained notifications, with per-category settings.
- Starter Domains from `domains.json`, editable without a code change.
- A frozen demo build that the Pages workflow publishes.
- A Tailscale sidecar in `compose.yml`, with named containers: `pwedepa-app` and `pwedepa-tailscale`.
- `.env.example`, and a session secret that compose demands before it starts.
- The passkey ID follows the public origin, unless a deploy sets `PWEDEPA_RP_ID`.
- The Docker workflow publishes the dev image from a passing CI run on `main`, and both platform legs land behind one tag.
- An approved release draft publishes the version tag and `latest`, through the approved tag in that run's log.

### Changed

- `compose.yml` runs the published image, and `compose.dev.yml` builds the checkout for local runs.

### Fixed

- The share rule lives in one place, so the page and the endpoint answer the same.
- One guard runs before every admin route.
- The service worker keeps only its own origin in the cache.
- The database prepares its schema once for each file.
- A session stamps its use at most once an hour.
- The workspace reads its three preference rows in one query.

### Removed

- The unused Alembic dependency, and a helper for terminal states with no caller.
