# Changelog

This file records all notable changes to this project.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- A Tailscale sidecar in `compose.yml`, with named containers: `pwedepa-app` and `pwedepa-tailscale`.
- `.env.example`, and a session secret that compose demands before it starts.
- The passkey ID follows the public origin, unless a deploy sets `PWEDEPA_RP_ID`.
- The app image builds as `pwedepa`, and a Docker workflow publishes the dev image from `main`.
- The gemini release workflow drafts a version and its notes. An approved tag builds the release image.

## [0.1.0] - 2026-10-16

### Added in 0.1.0

- Passkey sign-in and enrollment, with admin user management and an audit trail.
- Requests as intake and issues as accepted work. A request raises into a new issue.
- Status moves, field edits, comments, and archives on both record types.
- Share links with expiry, permissions, and revoke.
- Retained notifications, with per-category settings.
- Starter Domains from `domains.json`, editable without a code change.
- A frozen demo build that the Pages workflow publishes.
