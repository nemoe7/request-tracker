# PwedePa design decisions

This file records the settled design calls. When a pick changes, update this file in the same change. The owner approves design changes from rendered screens, not prose. Each change here traces to a screenshot review.

## Product shape

- Staff screens use the dense work-queue shape: top bar, queue filters, record list, inspector, and an issue strip. No sidebar.
- The client (requester) surface stays separate and simple: My requests, the public board, and one New request action, in a single 720 px column.
- Settings pages follow the Apple Settings pattern: grouped rows, label on the left, control on the right. A chevron appears only when a row navigates. The pattern stays inside Settings.

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

- Inter, self-hosted woff2 in 400, 600, and 800 under the SIL Open Font License 1.1. The license ships beside the fonts. The fallback stack is the system stack.
- IDs, counts, and ages use the ui-monospace stack with tabular figures.
- Scale: 11 px uppercase eyebrows, 12 px meta, 15 px body, 20 px panel titles, 28 px page titles. Headings use 600 or 800 weight with -0.02 em tracking.

## Icons

- UI icons come from Lucide, as one self-hosted SVG sprite at 18 px in the current text color. The ISC license ships beside the sprite. Add an icon to the sprite instead of drawing one.
- The app icon is a stub: the Google Noto Emoji pleading face (U+1F97A). The static image resources carry Apache 2.0. The animated assets carry CC BY 4.0 with attribution. The icon files and their `NOTICE.md` live in `pwedepa/web/static/icons/`. The static face shows by default, and the animated face plays on hover. The face sits inside the 72 percent maskable safe zone on a solid background.

## Layout

- The top bar is 56 px and holds the brand, section tabs, theme control, and one primary action.
- At 1200 px and up the staff grid runs filters 240 px, list fluid, inspector 360 px. Spacing follows an 8 px scale. Record rows are 40 px on desktop, panels get 10 px radius, and panels never carry shadows.
- Breakpoints sit at 1200, 900, and 640 px. Below 900 px the tabs move to a bottom nav with five stops. The inspector turns into a full-screen sheet, and filters fold into one disclosure row.
- Touch targets run at least 44 px. Tables never squeeze on a phone. They stack into cards, one fact per line. Text never drops below 12 px.

## Components

- One primary action per view. Primary buttons use the accent fill. Danger stays ghost style with red text.
- Forms put the label above the field, help text in 12 px muted, and errors in danger text that names the fix.
- Empty states use the pleading-face mark, one plain sentence, and one action.
- Screens build only from the adopted component sheet. A new pattern earns a sheet entry and a screenshot before it ships.

## Theme and motion

- The theme control cycles System, Light, Dark. System is the default, reads the device, and persists per device. An inline head script sets the theme before the first paint.
- One easing curve drives every hover, press, switch, and page transition. The curve is `cubic-bezier(0.22, 1, 0.36, 1)`, and the runs last 160 to 220 ms. Cross-document view transitions keep the top bar steady during navigation. `prefers-reduced-motion` turns animation off. The animated icon face crossfades on hover. It also plays on the landing hero.
- The landing tagline asks "pwede pa" with rotating `.`, `..`, `...`, `...?` marks while the page loads, then answers "pwede na!".

## Decisions log

- Structure: B work queue over A sidebar. Owner pick from rendered prototypes.
- Palette: Scheme 2, Slate and blue. Owner pick from rendered screens.
- Font: Inter self-hosted. Owner pick from rendered screens.
- Component sheet: adopted as rendered, light, dark, and phone.
- Icons: Lucide. Owner call.
- Tagline: "pwede pa...?" while loading, "pwede na!" when done. Owner call.
