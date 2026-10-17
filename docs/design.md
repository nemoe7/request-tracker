# PwedePa design decisions

This file records the settled design calls. When a pick changes, update this file in the same change. The owner approves design changes from rendered screens, not prose. Each change here traces to a screenshot review.

## Product shape

- Staff screens use the dense work-queue shape: top bar, queue filters, item list, inspector, and an issue strip. No sidebar.
- A client sees a mini dashboard at the top of the Requests page. It counts what the client can see now: their own requests and the public board. A selected item opens as the wide card, with the same shape as the staff card. On a phone the opened item fills the page.
- The staff workspace is the one staff page, and it reads as an inbox. The items a staff member has not opened come first, then the opened ones. Each staff member keeps their own read list, and a new event on an item returns it to the unread group. The opened item is the wide middle card, and the list moves to the right. On a phone the opened item fills the page, with a Back to the list link.
- The client (requester) surface stays separate and simple: My requests, the public board, and one New request action, in a single 720 px column.
- Settings pages follow the Apple Settings pattern: grouped rows, label on the left, control on the right. A chevron appears only when a row navigates. The pattern stays inside Settings.

## Domains

- The Domain list comes from `domains.yaml` at the project root. Each entry holds a name and a description. The URL slug comes from the name: lowercase, with each run of other characters folded to `-`. An entry may set `slug:` to hold its URL when the name changes.
- An admin imports the file in Admin, Domain config. The page reads a mounted file first, then a picked file. The import writes a copy beside the database, and the app reads that copy first.
- A request lives at `/<slug>/requests/<id>`, and an issue at `/<slug>/issues/<id>`, under each Domain it belongs to. The old `/requests/<id>` and `/issues/<id>` pages answer 404. Both forms offer the configured Domains as checkboxes.
- The Domain page at `/<slug>` shows the description and the requests and issues that carry the Domain.
- Staff publish announcements on a Domain page. Each one holds a title, a body, the author, the publish time, and the edit time. The Domain page lists them newest first. The Domain slug is the stored key, so a rename keeps every announcement and every follower, and a pinned slug keeps the URL too.
- A person follows a Domain from a toggle on its page. A new announcement then lands in the follower's inbox as an activity notice, and the existing activity switch silences it. The author gets no notice for their own announcement. The frozen demo hides the toggle.

## Color

Scheme 2, Slate and blue. Components use tokens from `pwedepa/web/static/tokens.css` and never raw hex.

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

- Status colors stay constant across schemes: Open blue, Pending amber, Delayed violet, Blocked red, Resolved green, Closed gray.
- A status pill always pairs a dot with a word. Color never carries the meaning alone.
- Dark pills use a 15 percent tint behind a lightened label and must pass 4.5:1 contrast. Body text passes 4.5:1, large text 3:1, and every interactive element shows a 2 px focus ring.

## Type

- Inter, self-hosted woff2 in 400, 600, and 800 under the SIL Open Font License 1.1. The license ships beside the fonts. The fallback stack is the system stack. The face swaps in when it arrives, so a refresh never strands a page on the fallback.
- IDs, counts, and ages use the ui-monospace stack with tabular figures.
- Scale: 11 px uppercase eyebrows, 12 px meta, 15 px body, 20 px panel titles, 28 px page titles. Headings use 600 or 800 weight with -0.02 em tracking.

## Icons

- UI icons come from Lucide, as one self-hosted SVG sprite at 18 px in the current text color. The ISC license ships beside the sprite. Add an icon to the sprite instead of drawing one.
- The app icon is a stub: the Google Noto Emoji pleading face (U+1F97A). The static image resources carry Apache 2.0. The animated assets carry CC BY 4.0 with attribution. The icon files and their `NOTICE.md` live in `pwedepa/web/static/icons/`. The static face shows by default, and the animated face plays on hover. The brand shows the bare face, with no chip behind it. The two maskable files hold the face inside the 72 percent safe zone on a solid background, for the OS install icon alone.

## Layout

- The top bar is 56 px and holds the brand, section tabs, theme control, and one primary action.
- The top bar stays fixed, outside the scrolled layer, and the body holds its 56 px of room. A sticky bar snaps its text between two device rows on a fractional scroll offset. Fixing the bar keeps it on one row. Owner pick from a recorded clip.
- The section tabs follow the role. Staff see the Workspace tab alone, because the workspace covers all management. Clients keep the Requests and Issues tabs.
- A staff member can switch the whole session to the client view from Settings. It shows what a client sees and drops the write controls on requests and issues. The server refuses those writes that still arrive. Account settings stay writable, and the same row leaves the view again.
- At 1200 px and up the staff grid runs filters 240 px, list fluid, inspector 360 px. Spacing follows an 8 px scale. Record rows are 40 px on desktop, panels get 10 px radius, and panels never carry shadows.
- Breakpoints sit at 1200, 900, and 640 px. Below 900 px the tabs move to a bottom nav and carry the same stops as the top bar. The inspector turns into a full-screen sheet, and filters fold into one disclosure row.
- Touch targets run at least 44 px. Tables never squeeze on a phone. They stack into cards, one fact per line. Text never drops below 12 px.

## Components

- One primary action per view. Primary buttons use the accent fill. Danger stays ghost style with red text.
- Forms put the label above the field, help text in 12 px muted, and errors in danger text that names the fix.
- Empty states use the pleading-face mark, one plain sentence, and one action.
- Screens build only from the adopted component sheet. A new pattern earns a sheet entry and a screenshot before it ships.

## Theme and motion

- The theme control cycles System, Light, Dark. System is the default and reads the device. The choice lives on the account, so it follows the person to another device. Signed-out pages and the frozen demo keep a browser copy instead. An inline head script sets the theme before the first paint.
- One easing curve drives every hover, press, switch, and page transition. The curve is `cubic-bezier(0.22, 1, 0.36, 1)`, and the runs last 160 to 220 ms. Cross-document view transitions keep the top bar steady during navigation. `prefers-reduced-motion` turns animation off. The animated icon face crossfades on hover. It also plays on the landing hero.
- The landing tagline asks "pwede pa" with rotating `.`, `..`, `...`, `...?` marks while the page loads, then answers "pwede na!".

## Decisions log

- Structure: B work queue over A sidebar. Owner pick from rendered prototypes.
- Palette: Scheme 2, Slate and blue. Owner pick from rendered screens.
- Font: Inter self-hosted. Owner pick from rendered screens.
- Component sheet: adopted as rendered, light, dark, and phone.
- Icons: Lucide. Owner call.
- Tagline: "pwede pa...?" while loading, "pwede na!" when done. Owner call.
