# Changelog

This file lists all notable changes to this project.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0]

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
- `frontend-design` and `taste-skill` join the vendored skills, and both apply
  to every front-end change.
- Profile offers Change username. A modal asks for the new name, and a name
  another account holds keeps the modal open with its reason.

### Fixed

- Notification switches now bind at page load. They save on flip, and the
  fallback Save row hides without a theme click.
- A seeded request carries a dummy requester, so the Requests page names an
  owner instead of a dash.
- A dev image builds for the whole push range, not just the tip commit. A docs
  commit over code no longer skips the build.
- The dev build starts at the newest shipped dev image, not at the last CI run.
  A docs run can no longer hide code below it.
- Status pills read at 4.5:1 or better in the light theme.
- Phone taps stay at 44 px on the top bar and the buttons, and the Admin config
  file field takes the form style.
- A clipped workspace row shows its full title and line on hover.
- A count badge and the picked demo seat take their own colour pair, so both read
  in dark. The active tab draws a border, not a shadow.
- The meta line reads in the page face, and only an ID keeps the mono face.
  Summary and button controls take the focus ring.
- A phone settings list keeps its page title, and a phone icon button takes a
  44 px tap target. The filters row is reachable from the keyboard.
- A closed reading pane leaves no empty card. A record that fails to load names
  its own page, and a filter change says how many rows show.
- Form controls take the page face, so a checkbox and a slider match the field.
- A workspace header names its column for a screen reader.

### Changed

- CI runs its tests on 3.13, the image runtime, and on 3.11, the declared floor.
  The contract job needs only plain Python, and the container scan reuses a layer
  cache.
- Every workflow job shows a plain name in the run view.
- CI skips the tests on a docs-only change, pins uv on Pages, and installs
  PyYAML alone for the workflow gate.
- `PWEDEPA_NO_STORE=1` sends `Cache-Control: no-store` on every page, so a dev
  preview never serves an old page.
- Settings carry no Save row when the script runs. The name field saves on a
  change, and text size hides its row once the script binds.
- A settings group leads with its plain name and one line over the rows. The
  icon tile and the centred banner are gone.
- The workspace fills a wide screen, and the Issues page keeps one narrow column.
- The type scale runs six steps. A page title reads at 600, and one caps
  treatment remains, for the page eyebrow.
- A record leads with its number, title, and state, then the author and the age.
  The workspace pane reads the same.
- Comments and events share one timeline. A comment carries a rule, not a card.
- At 1200 px and up the workspace keeps its reading pane open beside the list.
  A pick takes the whole column below that width.
- Profile leads with member since, role, and last sign-in. A client row carries
  its last reply.
- The audit log names each event in words, and the Admin save buttons carry their
  words.
- A local run reads the Markdown linter from `package-lock.json`.
- Form, modal, share, settings, admin, and timeline copy uses shorter sentences
  with plain verbs.
