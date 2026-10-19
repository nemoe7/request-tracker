# Changelog

This file lists all notable changes to this project.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `frontend-design` and `taste-skill` join the vendored skills, and both apply
  to every front-end change.

### Fixed

- Notification switches now bind at page load. They save on flip, and the
  fallback Save row hides without a theme click.

### Changed

- `PWEDEPA_NO_STORE=1` sends `Cache-Control: no-store` on every page, so a dev
  preview never serves an old page.
- Settings carry no Save row when the script runs. The name field saves on a
  change, and text size hides its row once the script binds.

## [0.1.0] - 2026-10-16

### Added

- Passkey sign-in and enrollment, with admin user management and an audit trail.
- Requests as intake and issues as accepted work. A request raises into a new
  issue, and both take status moves, edits, comments, and archives.
- Share links with expiry, permissions, and revoke.
- Notifications with per-category settings.
- Domains from `config.yml`, each with a slug and a description, and an import
  from Admin. Every request and issue URL starts with its Domain, and the old URLs
  answer 404.
- Domains live in the app. The config file fills the list on a first start, and an
  admin adds, renames, or removes a Domain in Admin, Domain config. A rename holds
  the old URL on a redirect, and a remove drops the Domain's records after a
  counted confirm.
- A checkout reads `config.dev.yml` in place of `config.yml`, with no variable in
  play. That file carries the Domains, and it can seed a demo set of requests and
  issues on a first start.
- Domain announcements, with the author and the publish and edit times. Staff
  remove one from a page that asks first.
- A Domain subscription toggle. A follower hears about each new announcement in
  the inbox, and the activity switch silences it.
- A staff workspace that reads as an inbox, with a read list per staff member.
- A client mini dashboard on the Requests page, and a wide card for one item.
- The base URL is the app. A guest signs in there, and a signed-in person opens
  their own work at once. `/home` and `/workspace` forward to it.
- The header names the running build. A checkout shows its short hash, and an
  image shows its tag or hash.
- A client view switch for staff, with request and issue pages read only.
- A theme choice on the account.
- A frozen demo on GitHub Pages, built from the app.
- `compose.yml` with a Tailscale sidecar, `compose.dev.yml` for a local build,
  and `.env.example` with every variable.
- The app through uvicorn, with one adapter in front of Flask.
- The passkey ID follows the public origin, unless `PWEDEPA_RP_ID` sets it.
- The Docker workflow publishes `dev` from a passing CI run on `main`, and an
  approved release publishes the version and `latest`.
