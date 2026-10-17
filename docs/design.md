# PwedePa design decisions

This file holds the settled calls. Update it in the same change that changes a
pick.

## Product shape

- Staff screens use the dense work-queue shape: top bar, queue filters, item list,
  inspector, and an issue strip. No sidebar.
- The staff workspace is the one staff page. Unread items come first, then the
  opened ones. Each staff member keeps their own read list, and new activity returns
  an item to the unread group. One toolbar over the list holds the title, the status
  filter, and the new-request action. Rows stay dense, unread titles are bold, and
  the open row carries an accent edge. The opened item reads on the right. On a
  phone the item fills the page, with a Back to the list link.
- Request and issue pages follow the GitHub issue shape. The title carries the
  number and the state. One comment timeline holds the description and the
  comments. A right sidebar holds the people, labels, priority, and details.
- The public share page keeps that shape. It holds one timeline and a facts
  sidebar, and no write control.
- The Issues page groups issues by state. A row shows the number, title, priority, and
  assignee, and an empty state group stays out of the list.
- A client sees a mini dashboard at the top of the Requests page. Their own requests
  and the public board read as dense rows, each with its state and a card link. A
  selected item opens as the wide card, and a phone shows it alone. The client
  surface stays one 720 px column.
- Settings follow the Apple Settings pattern: grouped rows, label left, control
  right, and a chevron only when the row navigates. The pattern stays inside Settings.
  A wide screen works like the Mac pane: the rail picks one group and only that
  group shows. A phone stacks every group, as iOS does. A switch saves the moment
  it flips, so a group of switches carries no Save button.

## Domains

- `config.yml` seeds the Domains once. After that the app owns the list, and an
  admin adds, renames, or removes a Domain in Admin, Domain config. A rename keeps
  the records, and the old slug answers with a redirect. A remove drops the
  Domain's records behind a confirm that counts them.
- An admin imports a picked file in Admin, Domain config. The app reads that copy
  before the config file in force.
- A request lives at `/<slug>/requests/<id>` and an issue at `/<slug>/issues/<id>`.
  The old `/<id>` pages answer 404, and both forms offer the configured Domains.
- The Domain page shows the description, its requests and issues, and its
  announcements newest first. An announcement holds a title, a body, the author,
  the publish time, and the edit time.
- The slug keys an announcement and a subscription, so a rename keeps both. A pinned
  slug keeps the URL too.
- A person follows a Domain from a toggle on its page. A new announcement notifies
  each follower except the author, and the activity switch silences it.
- Staff remove an announcement from a page that asks first.

## Settings file

- `config.yml` is a template, and a deploy mounts the real file over it. It holds
  the Domains and three short keys: `database`, `origin`, and `rp_id`. The dev file
  adds `seed`. A key in the file wins over its environment variable.
- `config.dev.yml` sits beside `config.yml`, and the app reads it whole in place of
  that file. No variable turns it on, and the released image ships without it.
- A `seed:` list fills the requests and issues tables once, on a first start, and
  only while both are empty.

## Color

Scheme 2, Slate and blue. Components use tokens from
`pwedepa/web/static/tokens.css` and never raw hex.

| Token | Light | Dark |
| --- | --- | --- |
| bg | `#F4F6F8` | `#0C1118` |
| surface | `#FFFFFF` | `#131B26` |
| surface-2 | `#F8FAFC` | `#182233` |
| line | `#DCE3EA` | `#243144` |
| text | `#17222E` | `#E4EBF3` |
| muted | `#5B6B7B` | `#93A5B8` |
| accent | `#2563EB` | `#6EA8FE` |
| accent-fill | `#2563EB` | `#1D4ED8` |
| danger | `#DC2626` | `#FF9C94` |
| warn | `#B45309` | `#F5B04C` |
| ok | `#15803D` | `#6FD598` |

- Status colors stay constant across schemes: Open blue, Pending amber, Delayed
  violet, Blocked red, Resolved green, Closed gray.
- A status pill pairs a dot with a word, so color never carries the meaning alone.
- Body text passes 4.5:1 contrast, large text 3:1, and every interactive element
  shows a 2 px focus ring.

## Type

- Inter, self-hosted woff2 in 400, 600, and 800, under the SIL Open Font License 1.1.
- IDs, counts, and ages use the ui-monospace stack with tabular figures.
- Scale: 11 px uppercase eyebrows, 12 px meta, 15 px body, 20 px panel titles, and
  28 px page titles.

## Icons

- Lucide, as one self-hosted SVG sprite at 18 px in the current text color.
- The app icon is the Google Noto Emoji pleading face. The licenses ship beside both
  assets, and the icon files and their `NOTICE.md` live in
  `pwedepa/web/static/icons/`.

## Layout

- The top bar is 56 px, fixed outside the scrolled layer, and the body holds its room.
- Tabs follow the role. Staff hold no tabs, and the brand opens the workspace.
  Clients keep Requests and Issues.
- A staff member can switch the whole session to the client view from Settings.
  Request and issue pages lose the write controls, and the server refuses a
  request or issue write that still arrives. Account settings stay writable.
- At 1200 px and up the staff grid runs filters 240 px, list fluid, inspector 360 px.
  Spacing follows an 8 px scale, rows are 40 px, panels get 10 px radius, and panels
  carry no shadow.
- Breakpoints sit at 1200, 900, and 640 px. Below 900 px the tabs move to a bottom
  bar, the opened item fills the page, and the filters fold into one row.
- Touch targets run at least 44 px, and tables stack into cards on a phone.

## Components

- One primary action per view. Primary buttons use the accent fill, and danger stays
  ghost style with red text.
- Forms put the label above the field, help text in 12 px muted, and errors in danger
  text that names the fix.
- Empty states use the pleading-face mark, one sentence, and one action.
- A new pattern needs a sheet entry and a screenshot before it ships.

## Theme and motion

- The theme control cycles System, Light, and Dark, and System reads the device. The
  choice lives on the account. Signed-out pages and the frozen demo keep a browser
  copy. An inline head script sets the theme before the first paint.
- One easing curve, `cubic-bezier(0.22, 1, 0.36, 1)`, runs 160 to 220 ms. Reduced
  motion turns animation off.
- The sign-in page holds one card and no header. The card offers a passkey button and an enroll link.
