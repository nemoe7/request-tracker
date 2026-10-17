# Changelog

This file records all notable changes to this project.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-10-16

### Added

- Passkey sign-in and enrollment, with admin user management and an audit trail.
- Requests as intake and issues as accepted work. A request raises into a new issue.
- Status moves, field edits, comments, and archives on both record types.
- Share links with expiry, permissions, and revoke. The page and the endpoint read one rule.
- One guard in front of every admin route.
- Retained notifications, with per-category settings.
- Starter Domains from `domains.json`, editable without a code change.
- A frozen demo build that the Pages workflow publishes. Every rail filter, the status filter included, opens from a link and a page of its own. A card swap keeps every link on a real page. The demo ships no worker file, and the build refuses a script that still names one.
- The app serves through uvicorn, a production server, with one adapter in front of Flask.
- A staff member can switch to a read-only client view from the account menu. It shows the page a client sees, and the server refuses every write.
- A Tailscale sidecar in `compose.yml`, with named containers: `pwedepa-app` and `pwedepa-tailscale`.
- `.env.example`, and a session secret that compose demands before it starts.
- The passkey ID follows the public origin, unless a deploy sets `PWEDEPA_RP_ID`.
- The Docker workflow publishes the dev image from a passing CI run on `main`, and both platform legs land behind one tag. Each pushed image starts once before the tags merge.
- An approved release draft publishes the version tag and `latest`, through the approved tag in that run's log.
- `compose.yml` runs the published image, and `compose.dev.yml` builds the checkout for local runs.
- The workspace inspector and the admin audit page read only the rows they show.
- The workspace reads its three preference rows in one query, and a session stamps its use at most once an hour.
- The schema prepares once for each database file, and the service worker keeps only its own origin in the cache.
- The share form reads every day count the number field allows. A submitted value the page cannot send returns a sentence, and an edit keeps the field it cannot read.
