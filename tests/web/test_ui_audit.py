import re
from datetime import UTC, datetime

import pytest
from _paths import record_url

from pwedepa import build_label
from pwedepa.auth import (
  Role,
  assign_role,
  list_audit_events,
  list_roles,
  record_audit,
  sessions,
  users,
)
from pwedepa.core import Issue, Request, RequestStatus, Visibility
from pwedepa.data import db as data_db
from pwedepa.data import issues as issues_data
from pwedepa.data import notifications as notifications_data
from pwedepa.data import requests as requests_data
from pwedepa.data import sharing
from pwedepa.web import SESSION_COOKIE, create_app

AT = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)


@pytest.fixture
def app(tmp_path):
  return create_app(
    {
      "DATABASE": str(tmp_path / "test.db"),
      "WEBAUTHN_RP_ID": "example.com",
      "WEBAUTHN_RP_NAME": "PwedePa",
      "WEBAUTHN_ORIGIN": "https://example.com",
      "SESSION_COOKIE_SECURE": True,
    }
  )


@pytest.fixture
def db(app):
  connection = data_db.connect(app.config["DATABASE"])
  yield connection
  connection.close()


def _client(app, db, name, display, roles=()):
  person = users.create_user(db, name, display, at=AT)
  for role in roles:
    assign_role(db, person.id, role, at=AT)
  token = sessions.create_session(db, person.id, at=AT).token
  client = app.test_client()
  client.set_cookie(SESSION_COOKIE, token)
  return client


def test_requester_leaves_workspace_for_requests(app, db):
  client = _client(app, db, "Mara", "Mara Reyes", roles=(Role.REQUESTER,))
  response = client.get("/")
  assert response.status_code == 302
  assert "/requests" in response.headers["Location"]


def test_the_requests_list_answers_at_requests(app, db):
  client = _client(app, db, "Mara", "Mara Reyes", roles=(Role.REQUESTER,))
  assert client.get("/requests").status_code == 200
  assert client.get("/my").status_code == 404


def test_assignee_keeps_workspace(app, db):
  client = _client(app, db, "Sam", "Sam Cruz", roles=(Role.ASSIGNEE,))
  assert client.get("/").status_code == 200


def _nav_tabs(html: str) -> list[str]:
  block = re.search(r'<nav class="tabs".*?</nav>', html, re.DOTALL)
  assert block, "the top bar carries no tab strip"
  return re.findall(r"</svg>([^<]+)</a>", block.group(0))


def test_staff_hold_no_top_tabs(app, db):
  client = _client(app, db, "Sam", "Sam Cruz", roles=(Role.ASSIGNEE,))
  assert '<nav class="tabs"' not in client.get("/").get_data(as_text=True), (
    "the brand alone leads back to the workspace"
  )


def test_the_top_tabs_mark_the_current_page(app, db):
  client = _client(app, db, "Mara", "Mara Reyes", roles=(Role.REQUESTER,))

  def tab(body: str, label: str) -> str:
    found = re.search(r"<a [^>]*>(?:(?!</a>).)*?" + label + r"</a>", body, re.DOTALL)
    assert found, f"no {label} tab"
    return found.group(0)

  for path, current, other in (
    ("/requests", "Requests", "Issues"),
    ("/issues", "Issues", "Requests"),
  ):
    body = client.get(path).get_data(as_text=True)
    assert 'aria-current="page"' in tab(body, current), (
      f"{current} is not marked current"
    )
    assert "aria-current" not in tab(body, other), f"{other} claims the current page"


def test_admins_hold_no_top_tabs(app, db):
  client = _client(app, db, "Ana", "Ana Lim", roles=(Role.ADMIN,))
  assert '<nav class="tabs"' not in client.get("/").get_data(as_text=True)


def test_the_phone_reserves_no_room_for_a_staff_bar(app, db):
  staff = _client(app, db, "Sam", "Sam Cruz", roles=(Role.ASSIGNEE,))
  staff_page = staff.get("/").get_data(as_text=True)
  assert '<body class="is-staff">' in staff_page
  css = staff.get("/static/app.css").data.decode()
  blocks = re.findall(r"@media \(max-width: 899px\) \{(.*?)\n\}", css, re.DOTALL)
  assert blocks, "the phone blocks hold the bottom bar rules"
  padding = [re.search(r"body\.is-staff \{([^}]*)\}", block) for block in blocks]
  assert any(match and "padding-bottom: 0" in match.group(1) for match in padding), (
    "no bar leaves no room"
  )
  client = _client(app, db, "Mara", "Mara Reyes", roles=(Role.REQUESTER,))
  assert '<body class="is-staff">' not in client.get("/requests").get_data(as_text=True)


def test_the_phone_workspace_folds_its_filters(app, db):
  """On a phone the filters sit above the list, and one row opens them."""
  client = _client(app, db, "Sam", "Sam Cruz", roles=(Role.ASSIGNEE,))
  page = client.get("/").get_data(as_text=True)
  rail = page[
    page.index('class="panel filters"') : page.index('class="panel inspector"')
  ]
  assert 'class="filters-toggle"' in rail, "one control folds the rail"
  assert 'for="filters-toggle"' in rail, "the row toggles it"
  assert 'class="filters-body"' in rail, "the rail content folds into one body"
  css = client.get("/static/app.css").data.decode()
  phone_at = css.index("@media (max-width: 899px)")
  assert ".filters-toggle, .filters-row { display: none; }" in css[:phone_at], (
    "wide screens hide the row"
  )
  phone = css[phone_at:]
  assert ".filters-toggle:not(:checked) ~ .filters-body { display: none; }" in phone
  assert (
    ".filters-toggle { display: block; position: absolute; width: 1px; height: 1px;"
    in phone
  ), "a phone keeps the toggle in the tab order"
  assert ".filters-toggle:focus-visible ~ .filters-row" in phone, (
    "the fold shows the ring when the box takes focus"
  )
  orders = dict(re.findall(r"\.workspace-grid \.([\w-]+) \{\s*order: (\d)", phone))
  list_orders = re.findall(
    r"\.workspace-grid \.records > \.([\w-]+) \{\s*order: (\d)", phone
  )
  assert int(orders["list-toolbar"]) < int(orders["filters"]), (
    "the filters sit above the list"
  )
  assert int(orders["filters"]) < min(int(order) for _, order in list_orders), (
    "the filters sit above the list"
  )


THEMES = (":root,", ':root[data-theme="dark"]')
STATUS_NAMES = (
  "open",
  "pending",
  "delayed",
  "blocked",
  "resolved",
  "closed",
  "raised",
  "rejected",
  "fulfilled",
  "revoked",
)


def _theme_block(css: str, selector: str) -> str:
  start = css.index(selector)
  return css[start : css.index("}", start)]


def _token(block: str, name: str) -> str:
  found = re.search(rf"--{name}: (#[0-9A-Fa-f]{{6}}|rgba\([^)]*\))", block)
  assert found, f"the theme misses --{name}"
  return found.group(1)


def _rgb(value: str) -> tuple[int, int, int]:
  if value.startswith("#"):
    return tuple(int(value[index : index + 2], 16) for index in (1, 3, 5))
  parts = re.fullmatch(r"rgba\(([^)]*)\)", value).group(1).split(",")
  return tuple(int(part) for part in parts[:3])


def _alpha(value: str) -> float:
  if value.startswith("#"):
    return 1.0
  parts = re.fullmatch(r"rgba\(([^)]*)\)", value).group(1).split(",")
  return float(parts[3])


def _over(top: tuple[int, int, int], alpha: float, bottom: tuple[int, int, int]):
  return tuple(
    round(a * alpha + b * (1 - alpha)) for a, b in zip(top, bottom, strict=True)
  )


def _channel(value: float) -> float:
  value /= 255
  return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4


def _luminance(rgb: tuple[int, int, int]) -> float:
  red, green, blue = (_channel(value) for value in rgb)
  return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _contrast(fore: tuple[int, int, int], back: tuple[int, int, int]) -> float:
  first, second = _luminance(fore), _luminance(back)
  return (max(first, second) + 0.05) / (min(first, second) + 0.05)


def test_every_status_pill_passes_contrast(app):
  """A 12 px pill needs 4.5:1, in both themes and for every state."""
  css = app.test_client().get("/static/tokens.css").data.decode()
  for selector in THEMES:
    block = _theme_block(css, selector)
    surface = _rgb(_token(block, "surface"))
    for status in STATUS_NAMES:
      fore = _rgb(_token(block, f"st-{status}"))
      tint = _token(block, f"st-{status}-bg")
      back = (
        _rgb(tint) if _alpha(tint) == 1 else _over(_rgb(tint), _alpha(tint), surface)
      )
      ratio = _contrast(fore, back)
      assert ratio >= 4.5, f"{selector} the {status} pill reads at {ratio:.2f}:1"


def test_the_badge_and_seat_switch_pass_contrast(app):
  """A white label on the raw accent reads at 2.4:1 in dark, so both use the deep fill."""
  css = app.test_client().get("/static/tokens.css").data.decode()
  for selector in THEMES:
    block = _theme_block(css, selector)
    ratio = _contrast(_rgb(_token(block, "pip-ink")), _rgb(_token(block, "pip-bg")))
    assert ratio >= 4.5, f"{selector} the count badge reads at {ratio:.2f}:1"
    ratio = _contrast(
      _rgb(_token(block, "on-accent")), _rgb(_token(block, "accent-fill"))
    )
    assert ratio >= 4.5, f"{selector} the seat switch reads at {ratio:.2f}:1"
  app_css = app.test_client().get("/static/app.css").data.decode()
  pip = app_css[app_css.index(".pip {") :].split("}", 1)[0]
  assert "background: var(--pip-bg)" in pip, "the badge takes its own pair"
  assert "color: var(--pip-ink)" in pip
  seat = app_css[app_css.index(".demo-switch a.on {") :].split("}", 1)[0]
  assert "background: var(--accent-fill)" in seat, "the picked seat takes the deep fill"
  assert "color: var(--on-accent)" in seat


def test_the_phone_keeps_a_44_pixel_tap_target(app):
  """A finger needs 44 px on the top bar and on every button."""
  css = app.test_client().get("/static/app.css").data.decode()
  phone = css[css.index("@media (max-width: 899px)") :]

  assert ".brand, .bell, .avatar-btn { min-height: 44px; }" in phone
  assert ".bell, .avatar-btn { min-width: 44px; justify-content: center; }" in phone
  grow = re.search(r"\.btn,[^{]*\{ min-height: 44px; \}", phone)
  assert grow and ".set-row .btn" in grow.group(0), "the row buttons grow with the rest"
  assert ".list-toolbar .btn, .list-toolbar .filter-form select," in phone, (
    "the toolbar steps and selects grow too"
  )
  assert ".mail-link { display: inline-block; padding-block: 12px;" in phone, (
    "the row link reaches 44 px without a gap"
  )


def test_the_stylesheet_holds_one_phone_block(app):
  css = app.test_client().get("/static/app.css").data.decode()
  assert ".workspace-grid.is-picked .inspector" in css, (
    "the picked card needs its own rule"
  )
  assert len(re.findall(r"@media \(max-width: 899px\)", css)) == 1, (
    "phones read in one place"
  )


def test_the_phone_list_reads_as_three_line_rows(app):
  """A phone row keeps the Gmail lines: who and when, the title, the preview."""
  css = app.test_client().get("/static/app.css").data.decode()
  phone = css[css.index("@media (max-width: 639px)") :]
  assert ".mail-table tr.mail-row {" in phone, "a phone row is its own grid"
  assert 'grid-template-areas: "from time" "title title" "snippet status"' in phone, (
    "the row reads in three lines"
  )
  assert ".mail-table .mail-title { display: contents; }" in phone, (
    "the title cell feeds the row grid"
  )
  assert "grid-area: time;" in phone and "grid-area: status;" in phone


def test_the_brand_tile_holds_the_bare_face(app):
  """The owner dropped the chip, so the face fills its tile on the bar."""
  css = app.test_client().get("/static/app.css").data.decode()
  tile = re.search(r"\.app-icon \{(.*?)\}", css, re.DOTALL)
  assert tile is not None, "the brand tile has a rule"
  assert "background" not in tile.group(1), "no chip behind the face"
  assert "border" not in tile.group(1), "no border around the face"
  image = re.search(r"\.app-icon img \{(.*?)\}", css, re.DOTALL)
  assert image is not None, "the face image has a rule"
  assert "inset: 0" in image.group(1), "the face fills the tile"
  assert "calc(" not in image.group(1), "nothing shrinks the face"


def test_the_brand_swap_never_fades_through_the_page(app):
  """A crossfade lets the bar show through, so the swap flips at once."""
  css = app.test_client().get("/static/app.css").data.decode()

  image = re.search(r"\.app-icon img \{(.*?)\}", css, re.DOTALL)
  assert image is not None, "the face image has a rule"
  assert "transition" not in image.group(1), "a fade would show the bar between faces"
  assert ".app-icon .icon-animated { visibility: hidden; }" in css
  assert ".app-icon:hover.is-ready .icon-static { visibility: hidden; }" in css
  assert ".app-icon:hover.is-ready .icon-animated { visibility: visible; }" in css


def test_the_row_link_reaches_the_card_handler(app, db):
  """The centre card opens in place, so a row link must match the handler."""
  owner = users.create_user(db, "owner", "Owner", at=AT)
  requests_data.save(
    db,
    Request(
      id=1,
      title="A row",
      description="",
      requester_id=owner.id,
      domains=("Gym",),
      created_at=AT,
      updated_at=AT,
    ),
  )
  client = _client(app, db, "Admin", "Admin", roles=(Role.ADMIN,))
  page = client.get("/").get_data(as_text=True)
  assert re.search(r'href="[^"]*selected=1', page), "the row link carries the id"
  js = client.get("/static/app.js").get_data(as_text=True)
  assert "a[href*='selected='" in js, "the handler binds the live row link"
  assert "a[href*='/record/']" in js, "the handler binds the frozen row link"


def test_requesters_keep_their_own_tabs(app, db):
  client = _client(app, db, "Mara", "Mara Reyes", roles=(Role.REQUESTER,))
  tabs = _nav_tabs(client.get("/requests").get_data(as_text=True))
  assert tabs == ["Requests", "Issues"]


def test_unknown_path_renders_styled_404(app):
  response = app.test_client().get("/no-such-page")
  assert response.status_code == 404
  assert b"app.css" in response.data


@pytest.fixture
def demo_app(tmp_path):
  return create_app(
    {
      "DATABASE": str(tmp_path / "demo.db"),
      "WEBAUTHN_RP_ID": "example.com",
      "WEBAUTHN_RP_NAME": "PwedePa",
      "WEBAUTHN_ORIGIN": "https://example.com",
      "SESSION_COOKIE_SECURE": True,
      "DEMO_MODE": True,
    }
  )


def test_demo_service_worker_retires_itself(demo_app):
  body = demo_app.test_client().get("/sw.js").data
  assert b"unregister" in body


def test_demo_responses_forbid_storage(demo_app):
  response = demo_app.test_client().get("/login")
  assert "no-store" in response.headers.get("Cache-Control", "")


def test_a_dev_run_can_forbid_storage_without_demo_mode(app, tmp_path):
  """A preview run sets no-store, and a normal run leaves the default alone."""
  plain = app.test_client().get("/login")
  assert "no-store" not in plain.headers.get("Cache-Control", "")

  preview = create_app(
    {
      "DATABASE": str(tmp_path / "preview.db"),
      "WEBAUTHN_RP_ID": "example.com",
      "WEBAUTHN_RP_NAME": "PwedePa",
      "WEBAUTHN_ORIGIN": "https://example.com",
      "SESSION_COOKIE_SECURE": True,
      "NO_STORE": True,
    }
  )
  client = preview.test_client()
  assert "no-store" in client.get("/login").headers.get("Cache-Control", "")
  asset = client.get("/static/app.css")
  assert "no-store" not in asset.headers.get("Cache-Control", "")
  assert "no-cache" in asset.headers.get("Cache-Control", "")


def test_demo_keeps_pages_fresh_and_lets_assets_revalidate(demo_app):
  client = demo_app.test_client()
  page = client.get("/login")
  assert "no-store" in page.headers.get("Cache-Control", "")
  asset = client.get("/static/app.css")
  assert "no-store" not in asset.headers.get("Cache-Control", "")
  assert "no-cache" in asset.headers.get("Cache-Control", "")


def test_the_header_defers_the_animated_icon(app, db):
  client = _client(app, db, "Ada", "Ada Lovelace", roles=(Role.REQUESTER,))
  body = client.get("/requests").data
  assert b'class="icon-animated" data-src="/static/icons/icon-animated.webp"' in body
  assert b'class="icon-animated" src=' not in body
  assert b"dataset.src" in client.get("/static/app.js").data


def test_the_header_names_the_build(app, db):
  client = _client(app, db, "Ada", "Ada Lovelace", roles=(Role.REQUESTER,))
  page = client.get("/requests").data.decode()
  assert f'<span class="brand-version">{build_label()}</span>' in page


def test_an_image_stamp_names_its_build(monkeypatch, tmp_path):
  import pwedepa

  stamp = tmp_path / "_version.txt"
  stamp.write_text("dev-a1b2c3d\n", encoding="utf-8")
  monkeypatch.setattr(pwedepa, "STAMP", stamp)
  pwedepa.build_label.cache_clear()
  try:
    assert pwedepa.build_label() == "a1b2c3d"
  finally:
    pwedepa.build_label.cache_clear()


def test_the_header_leaves_the_scrolled_layer(app):
  """A sticky bar snaps to the device grid while the page scrolls, so its text jitters."""
  css = app.test_client().get("/static/app.css").data.decode()
  pairs = re.findall(r"([^{}]+)\{([^{}]*)\}", css)
  bar_rules = [body for sel, body in pairs if sel.strip() == ".topbar"]
  assert bar_rules, "the top bar keeps its own rule"
  assert any("position: fixed" in body for body in bar_rules), (
    "the bar must not sit in the scrolled layer"
  )
  assert all("position: sticky" not in body for body in bar_rules), (
    "a sticky bar repaints off the device grid while scrolling"
  )
  body_rules = [body for sel, body in pairs if sel.strip() == "body"]
  assert any("padding-top: 56px" in body for body in body_rules), (
    "the page must keep the room the fixed bar used to hold"
  )


def test_page_switches_do_not_animate_the_whole_page(app):
  css = app.test_client().get("/static/app.css").data.decode()
  rules = {sel.strip(): body for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css)}
  groups = [
    selectors
    for selectors in rules
    if "::view-transition-old(root)" in selectors
    or "::view-transition-new(root)" in selectors
    or "::view-transition-old(topbar)" in selectors
    or "::view-transition-new(topbar)" in selectors
  ]
  assert groups, "each transition group needs a rule"
  for selectors in groups:
    assert "animation: none" in rules[selectors], (
      f"{selectors} still animates the switch"
    )
  assert "view-transition-name: filters" not in css, (
    "a named panel group ghosts the old page over the new one"
  )
  assert "view-transition-name: records" not in css, (
    "a named panel group ghosts the old page over the new one"
  )


def test_a_page_switch_swaps_the_shell_in_place(app):
  """The top bar stays put, and the content area takes the new page."""
  client = app.test_client()
  js = client.get("/static/app.js").data.decode()
  assert "window.pwedepaBoot" in js, "the script boots again after a swap"
  assert "window.pwedepaLifecycle?.abort()" in js, "a second boot drops the first"
  assert 'querySelector("main.wrap")' in js, "the swap owns the content area"
  assert "history.pushState" in js, "a swapped page keeps its own url"
  assert 'addEventListener("popstate"' in js, "the back button swaps too"
  css = client.get("/static/app.css").data.decode()
  assert "main.wrap:focus { outline: none; }" in css, (
    "the focused content must not draw a ring around the page"
  )


def test_client_rows_open_the_record_from_the_title(app, db):
  client = _client(app, db, "mara", "Mara Reyes", roles=(Role.REQUESTER,))
  record = Request(
    id=1,
    title="Broken projector",
    description="The projector in Room 4 is dead.",
    requester_id=users.get_user_by_username(db, "mara").id,
    created_at=AT,
    updated_at=AT,
  )
  requests_data.save(db, record)

  body = client.get("/requests").data.decode()
  assert f'href="{record_url(record.id)}"' in body
  assert 'class="record-row"' in body, "the client list reads as dense rows"

  css = app.test_client().get("/static/app.css").data.decode()
  rules = {sel.strip(): body for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css)}
  card = rules.get(".card.is-linked", "")
  assert "position: relative" in card, ".card.is-linked must anchor the stretched link"
  link = rules.get(".card.is-linked h2 a::after", "")
  assert "position: absolute" in link and "inset: 0" in link, (
    ".card.is-linked h2 a::after must cover the whole card"
  )


def test_facts_rows_never_squeeze_their_value(app):
  css = app.test_client().get("/static/app.css").data.decode()
  grid = re.search(
    r"\.facts \{[^}]*grid-template-columns: repeat\(auto-fit, minmax\((\d+)px, 1fr\)\)",
    css,
  )
  assert grid, ".facts must fall back to one column when a panel is narrow"
  assert int(grid.group(1)) >= 200, "a facts track must fit a label and its value"


def test_the_bell_pip_clears_the_bell(app):
  css = app.test_client().get("/static/app.css").data.decode()
  rules = {sel.strip(): body for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css)}
  pip = rules.get(".bell .pip", "")
  assert pip, "the bell pip needs its own placement rule"
  top = int(re.search(r"top: (-?\d+)px", pip).group(1))
  right = int(re.search(r"right: (-?\d+)px", pip).group(1))
  assert top <= -6 and right <= -8, "the pip must sit clear of the bell glyph"
  assert "margin-right" in rules.get(".bell", ""), (
    "the bell must keep room before the avatar"
  )


def test_the_scrollbar_matches_the_theme(app):
  client = app.test_client()
  css = client.get("/static/app.css").data.decode()
  tokens = client.get("/static/tokens.css").data.decode()
  assert tokens.count("--scroll-thumb:") >= 3, "every theme needs a scrollbar colour"
  assert "scrollbar-color: var(--scroll-thumb) transparent" in css
  assert "color-mix(in srgb, var(--muted) 45%" not in css, (
    "the scrollbar must not depend on color-mix"
  )
  root = re.search(r"\nhtml \{([^}]*)\}", css)
  assert root and "background: var(--bg)" in root.group(1), (
    "the root must paint the page background, so no white gutter shows"
  )


def test_no_blank_band_waits_for_a_scrollbar(app):
  """A reserved gutter shows as an empty strip, because the bar cannot paint it."""
  css = app.test_client().get("/static/app.css").data.decode()
  root = re.search(r"\nhtml \{([^}]*)\}", css)
  assert root and "scrollbar-gutter" not in root.group(1), (
    "the root must not hold a strip open when no scrollbar shows"
  )


def test_normal_service_worker_keeps_its_cache(app):
  body = app.test_client().get("/sw.js").data
  assert b"pwedepa-v4" in body


def test_the_worker_caches_the_static_files_only(app):
  """A shared browser must not keep a private page after a sign-out."""
  worker = app.test_client().get("/sw.js").data.decode("utf-8")
  handler = worker.split('self.addEventListener("fetch"', 1)[1]
  assert "response.ok && " in handler, "the worker must decide before it caches"
  assert "url.origin === self.location.origin" in handler, (
    "another origin may not fill our cache"
  )
  assert 'startsWith("/static/")' in handler, "only a static file may enter the cache"
  assets = worker.split("const ASSETS", 1)[1].split("];", 1)[0]
  assert '"/",' not in assets, "the root page is not a static file"


def test_motion_stays_fluid(app):
  client = app.test_client()
  css = client.get("/static/app.css").data + client.get("/static/tokens.css").data
  assert b"cubic-bezier(0.22, 1, 0.36, 1)" in css
  assert b"scale(1.04)" not in css
  assert b"scale(0.96)" not in css
  assert b"#tagline-marks" in css
  assert b"@view-transition" in css
  assert b"page-in" not in css


def test_display_name_keeps_its_alignment_on_focus(app):
  css = app.test_client().get("/static/app.css").data
  assert b".set-input:focus { outline: none; text-align: left; }" not in css


def _statements(css: str) -> list[str]:
  """Return the top-level stylesheet text between comments, blocks, and strings."""
  without_comments = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
  statements: list[str] = []
  current: list[str] = []
  depth = 0
  quote: str | None = None
  for character in without_comments:
    if quote:
      current.append(character)
      if character == quote:
        quote = None
      continue
    if character in "\"'":
      quote = character
      current.append(character)
      continue
    if character == "{":
      depth += 1
      statements.append("".join(current).strip() + " {")
      current = []
      continue
    if character == "}":
      depth -= 1
      statements.append("".join(current).strip() + "}" if depth < 0 else "")
      current = []
      continue
    if character == ";" and depth == 0:
      statements.append("".join(current).strip() + ";")
      current = []
      continue
    if depth == 0:
      current.append(character)
  statements.append("".join(current).strip())
  return [statement for statement in statements if statement]


def _stylesheet_errors(css: str) -> list[str]:
  """Name every top-level statement that is not an at-rule or a rule block."""
  errors = []
  for statement in _statements(css):
    if statement.endswith("}"):
      errors.append(f"a closing brace without an opening brace: {statement}")
    elif statement.endswith(";"):
      if not statement.startswith("@"):
        errors.append(f"a top-level statement ends with a semicolon: {statement}")
    elif not statement.endswith("{"):
      errors.append(f"a top-level statement opens no block: {statement}")
  return errors


def test_stylesheets_hold_no_stray_statements(app):
  client = app.test_client()
  for name in ("app.css", "tokens.css"):
    css = client.get(f"/static/{name}").data.decode()
    assert _stylesheet_errors(css) == []


def test_every_control_keeps_a_keyboard_focus_ring(app):
  css = app.test_client().get("/static/app.css").data.decode()
  ringed = [
    selector
    for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css)
    if "outline: 2px solid var(--accent)" in body
  ]
  assert ringed, "no rule draws the shared focus ring"
  for control in ("input", "select", "textarea", ".set-input", "main.wrap"):
    assert any(f"{control}:focus-visible" in selector for selector in ringed), (
      f"{control} loses its focus ring"
    )
  quiet = css.index(".set-input:focus {")
  visible = css.index(".set-input:focus-visible")
  assert quiet < visible, "the quiet rule must come first, so the ring wins"


def test_scrollbar_buttons_are_hidden(app):
  """Nuu scrollbar recipe hides arrow buttons and styles corner."""
  css = app.test_client().get("/static/app.css").data.decode()
  assert "::-webkit-scrollbar-button { display: none;" in css
  assert "::-webkit-scrollbar-corner { background: var(--bg);" in css


def test_settings_rail_carries_icon_rows_and_a_phone_list(app, db):
  client = _client(app, db, "Ada", "Ada Admin", roles=(Role.ADMIN,))
  body = client.get("/settings").data.decode()
  rail = body[body.index("settings-rail") : body.index("settings-main")]
  assert rail.count("set-chip") >= 4
  assert rail.count("chevron-right") >= 4
  css = client.get("/static/app.css").data.decode()
  assert ".settings-nav { display: none; }" not in css
  phone = css[
    css.index("@media (max-width: 639px)", css.index("@media (min-width: 640px)")) :
  ]
  assert ".settings-nav { background: var(--surface)" in phone
  assert ".settings-nav .chev { display: block; }" in phone


def test_wide_screens_stretch_the_shell(app):
  css = app.test_client().get("/static/app.css").data.decode()
  block = css[css.index(".wrap {") :]
  block = block[: block.index("}") + 1]
  assert "max-width: 1280px" in block, "the shell keeps one column"
  assert "padding: 32px" in block, "the column keeps a gutter"
  assert "@media (min-width: 1200px) { .wrap { max-width:" not in css


def test_workspace_puts_the_reading_pane_right_of_the_list(app, db):
  """The list comes first, and the record card reads on its right."""
  client = _client(app, db, "Sam", "Sam Cruz", roles=(Role.ASSIGNEE,))
  body = client.get("/").data
  assert body.index(b"panel records") < body.index(b"panel inspector")
  assert b"<th>Requester</th>" not in body
  assert b"<th>Domain</th>" not in body
  assert b'class="client-dash"' not in body


def test_the_workspace_list_carries_one_toolbar(app, db):
  """One row over the list holds the title and the status filter."""
  client = _client(app, db, "sam", "Sam Cruz", roles=(Role.ASSIGNEE,))
  requests_data.save(
    db,
    Request(
      id=1,
      title="Broken projector",
      description="The projector in Room 4 is dead.",
      requester_id=users.get_user_by_username(db, "sam").id,
      created_at=AT,
      updated_at=AT,
    ),
  )
  page = client.get("/").get_data(as_text=True)
  assert '<div class="page-head">' not in page, "the list owns its one row"
  toolbar = page[page.index('class="list-toolbar"') : page.index("<table")]
  assert "<h1>Workspace</h1>" in toolbar
  assert 'id="status-filter"' in toolbar, "the status filter sits in the row"
  assert "New request" not in toolbar, "staff triage keeps the client action out"
  top = page[page.index('class="top-actions"') : page.index("</header>")]
  assert 'aria-label="New request"' in top, "the top bar carries the action"
  assert page.index('class="list-toolbar"') < page.index(
    '<table class="record-table mail-table"'
  )
  rail = page[page.index('class="panel filters"') : page.index('class="panel records"')]
  assert 'id="status-filter"' not in rail, "the rail keeps no second filter row"


def test_the_status_filter_applies_on_the_pick(app, db):
  """A picked status sends at once, and the field reads as a select."""
  client = _client(app, db, "sam", "Sam Cruz", roles=(Role.ASSIGNEE,))

  page = client.get("/").get_data(as_text=True)
  opening = page.index('class="list-toolbar"')
  toolbar = page[opening : page.index("</div>", opening)]
  form = toolbar[toolbar.index('class="filter-form"') :]
  form = form[: form.index("</form>")]
  assert "data-auto-submit" in form, "a changed pick sends the form"
  assert 'id="status-filter"' in form
  assert form.index("<noscript>") < form.index("Apply status"), (
    "the button waits for a reader without JavaScript"
  )

  script = client.get("/static/app.js").data.decode()
  assert "form[data-auto-submit]" in script, "the script sends on a change"
  assert "requestSubmit" in script, "the send keeps the form's own rules"

  css = client.get("/static/app.css").data.decode()
  toolbar_rule = css[css.index(".list-toolbar .filter-form select {") :].split("}", 1)[
    0
  ]
  assert "padding: 6px 32px 6px 10px" in toolbar_rule, "the chevron clears the text"
  base = css[css.index("\n.filter-form select {") :].split("}", 1)[0]
  assert "background-color: var(--surface)" in base, "a shorthand would drop the arrow"


def test_the_workspace_reads_as_one_mail_table(app, db):
  """Gmail shows one list. Unread stays bold, the open row keeps one edge."""
  client = _client(app, db, "sam", "Sam Cruz", roles=(Role.ASSIGNEE,))
  requester_id = users.get_user_by_username(db, "sam").id
  for number, title in ((1, "Broken projector"), (2, "Ladder audit")):
    requests_data.save(
      db,
      Request(
        id=number,
        title=title,
        description="The projector in Room 4 is dead.",
        requester_id=requester_id,
        created_at=AT,
        updated_at=AT,
      ),
    )

  page = client.get("/?selected=1").get_data(as_text=True)

  assert page.count('<table class="record-table mail-table">') == 1, "one list"
  assert 'class="group-title"' not in page, "no group headings"
  assert "Issue strip" not in page, "the strip is gone"
  assert 'class="mail-from"' in page and 'class="mail-title"' in page
  assert 'class="mail-status"' in page and 'class="mail-time"' in page
  assert "The projector in Room 4 is dead." in page, "the row carries a snippet"
  assert 'class="is-unread' in page or " is-unread" in page, "unread rows read bold"
  assert "is-selected" in page, "the open row keeps its marker"

  css = client.get("/static/app.css").data.decode()
  row = re.search(r"\.record-table td \{([^}]*)\}", css)
  assert row and "padding: 5px 8px" in row.group(1), "the row keeps one dense height"
  table = re.search(r"\.record-table \{([^}]*)\}", css)
  assert table and "14px * var(--font-scale)" in table.group(1), (
    "table text clears 13.5px"
  )
  item = re.search(r"\.queue-item \{([^}]*)\}", css)
  assert item and "min-height: 40px" in item.group(1), (
    "the queue row meets the 40px ramp"
  )
  assert ".mail-table tr.is-unread .mail-title a { font-weight: 700; }" in css
  selected = re.search(r"\.record-table tr\.is-selected td \{([^}]*)\}", css)
  assert selected and "box-shadow" not in selected.group(1), (
    "the edge cannot repeat on every column"
  )
  first = re.search(r"\.record-table tr\.is-selected td:first-child \{([^}]*)\}", css)
  assert first and "inset 3px 0 0 var(--accent)" in first.group(1), (
    "only the first column holds the edge"
  )

  grid = re.search(r"\.workspace-grid \{([^}]*)\}", css)
  assert grid and "240px minmax(0, 1fr) 0" in grid.group(1), (
    "the closed list takes the free track"
  )
  assert "max-width" not in grid.group(1), "the shell column sets the width"
  assert "padding-inline" not in grid.group(1), "the shell gutter sets the sides"
  wrap = re.search(r"\.wrap \{([^}]*)\}", css)
  assert wrap and "margin: 0 auto" in wrap.group(1), "the shell stays a centered column"
  assert "0.85fr" not in css and "1.15fr" not in css, "one grid rule, no dead override"
  card = re.search(r"\.workspace-grid\.is-picked \.inspector \{([^}]*)\}", css)
  assert card and "grid-column: 2 / -1" in card.group(1), (
    "the picked card takes the free width"
  )


def test_a_clipped_workspace_row_keeps_its_full_text(app, db):
  """A cell that ends in an ellipsis must still offer the whole line."""
  client = _client(app, db, "sam", "Sam Cruz", roles=(Role.ASSIGNEE,))
  person = users.get_user_by_username(db, "sam")
  long_title = "The kitchen tap keeps dripping after the washer was changed twice"
  requests_data.save(
    db,
    Request(
      id=1,
      title=long_title,
      description="It started on Monday, and the washer looks worn.",
      requester_id=person.id,
      created_at=AT,
      updated_at=AT,
    ),
  )

  page = client.get("/").data.decode()

  assert f'title="{long_title}"' in page, "the clipped title keeps its full text"
  assert 'class="mail-snippet" title="It started on Monday' in page, (
    "the clipped line keeps its full text"
  )


def test_the_admin_saves_read_as_words(app, db):
  """An action button says what it does. Only the sheet button may drop its words."""
  client = _client(app, db, "Ada", "Ada Admin", roles=(Role.ADMIN,))

  for path, label in (("/admin/site", "Save message"), ("/admin/config", ">Save<")):
    page = client.get(path).data.decode()
    button = re.search(r'<button class="btn[^"]*" type="submit">([^<]*)', page)
    assert button, f"{path} keeps a submit button"
    assert label in page and "icon-only" not in button.group(0), path


def test_the_admin_config_file_field_looks_like_the_other_fields(app):
  """The native picker keeps its button, styled to the form."""
  css = app.test_client().get("/static/app.css").data.decode()

  rule = re.search(r'\.field input\[type="file"\] \{[^}]*\}', css)
  assert rule and "border-radius: 8px" in rule.group(0)
  assert "::file-selector-button" in css


def test_the_audit_log_reads_in_words(app, db):
  """The log names what happened, so the reader never sees a raw key."""
  client = _client(app, db, "Ada", "Ada Admin", roles=(Role.ADMIN,))
  person = users.get_user_by_username(db, "Ada")
  record_audit(db, "user.created", at=AT, actor_id=person.id, object_type="user")

  page = client.get("/admin/audit").data.decode()

  assert "<h2>User created</h2>" in page
  assert "user.created" not in page


def test_the_workspace_pane_carries_the_request_view(app, db):
  """The reading pane is the request page, controls and all."""
  client = _client(app, db, "sam", "Sam Cruz", roles=(Role.ASSIGNEE,))
  requester_id = users.get_user_by_username(db, "sam").id
  requests_data.save(
    db,
    Request(
      id=1,
      title="Broken projector",
      description="The projector in Room 4 is dead.",
      requester_id=requester_id,
      created_at=AT,
      updated_at=AT,
    ),
  )

  page = client.get("/?selected=1").get_data(as_text=True)
  pane = page[page.index('class="panel inspector') :]

  assert 'class="issue-head"' in pane, "the pane leads with the record header"
  assert "#1" in pane and "Broken projector" in pane
  assert 'class="timeline"' in pane, "the pane holds the timeline"
  assert 'class="issue-side"' in pane, "the pane holds the facts sidebar"
  assert 'class="actions"' in pane, "the pane holds the state controls"
  assert 'class="comment-form"' in pane, "the pane holds the comment box"
  assert 'name="next"' in pane, "a control returns to the pane"
  assert "selected=1" in pane


def test_a_form_can_return_to_the_pane(app, db):
  """A control sends its own page back only when the path is local."""
  client = _client(app, db, "sam", "Sam Cruz", roles=(Role.ASSIGNEE,))
  requester_id = users.get_user_by_username(db, "sam").id
  requests_data.save(
    db,
    Request(
      id=1,
      title="Broken projector",
      description="The projector in Room 4 is dead.",
      requester_id=requester_id,
      created_at=AT,
      updated_at=AT,
    ),
  )

  back = "/?queue=triage&selected=1"
  answer = client.post(
    "/requests/1/transition",
    data={"target": "PENDING", "next": back},
    follow_redirects=False,
  )
  assert answer.headers["Location"] == back

  away = client.post(
    "/requests/1/transition",
    data={"target": "DELAYED", "next": "//evil.example/x"},
    follow_redirects=False,
  )
  assert "evil.example" not in away.headers["Location"]


def test_a_move_keeps_the_request_open_in_the_pane(app, db):
  """A status change that filters the row out still leaves its view open."""
  _client(app, db, "sam", "Sam Cruz")
  client = _client(app, db, "Ada", "Ada Admin", roles=(Role.ADMIN,))
  requester_id = users.get_user_by_username(db, "sam").id
  requests_data.save(
    db,
    Request(
      id=1,
      title="Broken projector",
      description="The projector in Room 4 is dead.",
      requester_id=requester_id,
      created_at=AT,
      updated_at=AT,
    ),
  )

  page = client.post(
    "/requests/1/transition",
    data={"target": "PENDING", "next": "/?queue=triage&selected=1"},
    follow_redirects=True,
  ).get_data(as_text=True)
  assert requests_data.get(db, 1).status is RequestStatus.PENDING, "the move lands"
  assert 'class="issue-page is-pane"' in page, "the moved request keeps its pane"
  assert "Broken projector" in page, "the pane still names the request"


def test_the_record_pages_read_like_a_github_issue(app, db):
  """A number and state lead the title, and the facts sit in a right sidebar."""
  client = _client(app, db, "sam", "Sam Cruz", roles=(Role.ASSIGNEE,))
  requester_id = users.get_user_by_username(db, "sam").id
  requests_data.save(
    db,
    Request(
      id=1,
      title="Broken projector",
      description="The projector in Room 4 is dead.",
      requester_id=requester_id,
      created_at=AT,
      updated_at=AT,
    ),
  )
  issues_data.save(
    db,
    Issue(
      id=1,
      title="Projector repair plan",
      description="Replace the lamp and test it.",
      requester_id=requester_id,
      created_at=AT,
      updated_at=AT,
    ),
  )

  for path, heading in (
    (record_url(1), "Broken projector"),
    (record_url(1, "issues"), "Projector repair plan"),
  ):
    page = client.get(path).get_data(as_text=True)
    assert 'class="issue-layout"' in page, f"{path} holds one issue grid"
    assert page.index('class="issue-main"') < page.index('class="issue-side"')
    title = re.search(r"<h1[^>]*>(.*?)</h1>", page, re.DOTALL)
    assert title and "#1" in title.group(1) and heading in title.group(1)
    assert 'class="issue-head"' in page
    assert "<h2>Activity</h2>" not in page and "<h2>Comments</h2>" not in page
    assert '<ol class="timeline">' in page, "one timeline holds the comments"
    assert 'class="timeline-comment' in page
    side = page[page.index('class="issue-side"') :]
    people = "Requester" if "requests" in path else "Assignee"
    for label in (people, "Labels", "Priority", "Details"):
      assert f"<h2>{label}</h2>" in side, f"{path} misses {label} in its sidebar"


def test_a_staff_request_link_opens_in_the_workspace(app, db):
  """A staff page keeps the workspace around an opened request."""
  _client(app, db, "sam", "Sam Cruz")
  client = _client(app, db, "Ada", "Ada Admin", roles=(Role.ADMIN,))
  requester_id = users.get_user_by_username(db, "sam").id
  requests_data.save(
    db,
    Request(
      id=1,
      title="Broken projector",
      description="The projector in Room 4 is dead.",
      requester_id=requester_id,
      visibility=Visibility.PUBLIC,
      created_at=AT,
      updated_at=AT,
    ),
  )

  page = client.get("/requests").get_data(as_text=True)
  assert page.count("selected=1") >= 1, "the row opens the card in the workspace"
  assert 'class="record-row-side"' not in page, "a row offers one door, not two"


def test_reject_asks_for_a_reason_in_a_modal(app, db):
  """The reject trigger opens a custom modal, and the form carries a reason."""
  client = _client(app, db, "Ada", "Ada Admin", roles=(Role.ADMIN,))
  requests_data.save(
    db,
    Request(
      id=1,
      title="Broken projector",
      description="The projector in Room 4 is dead.",
      requester_id=users.get_user_by_username(db, "Ada").id,
      created_at=AT,
      updated_at=AT,
    ),
  )

  client.post("/records/request/1/share", data={"permission": "VIEW"})
  page = client.get("/?selected=1").get_data(as_text=True)
  assert 'data-modal-open="reject-request-1"' in page
  assert 'id="reject-request-1"' in page
  assert 'role="dialog"' in page
  assert 'name="reason"' in page
  assert "<noscript>" in page, "a browser without JS keeps a reason field"
  assert re.search(r'data-modal-open="revoke-share-\d+"', page), (
    "a share link uses the same modal"
  )
  assert re.search(r'id="revoke-share-\d+"', page)
  css = client.get("/static/app.css").data.decode()
  assert ".modal .modal-card h2" in css, "the dialog title keeps its own top margin"

  loaded = client.get("/").get_data(as_text=True)
  assert "reject-request-1" in loaded, "a load fills the pane, so its modal rides along"


def test_prose_in_the_workspace_renders_safe_html(app, db):
  """A description reads as markdown, and a script never reaches the page."""
  client = _client(app, db, "Ada", "Ada Admin", roles=(Role.ADMIN,))
  requests_data.save(
    db,
    Request(
      id=1,
      title="Broken projector",
      description="**Dead** bulb <script>alert(1)</script>",
      requester_id=users.get_user_by_username(db, "Ada").id,
      created_at=AT,
      updated_at=AT,
    ),
  )

  page = client.get("/?selected=1").get_data(as_text=True)
  assert "<strong>Dead</strong>" in page
  assert "<script>alert(1)</script>" not in page


def test_the_workspace_keeps_the_rail_when_a_request_opens(app, db):
  client = _client(app, db, "sam", "Sam Cruz", roles=(Role.ASSIGNEE,))
  record = Request(
    id=1,
    title="Broken projector",
    description="The projector in Room 4 is dead.",
    requester_id=users.get_user_by_username(db, "sam").id,
    created_at=AT,
    updated_at=AT,
  )
  requests_data.save(db, record)

  loaded = client.get("/").data.decode()
  assert 'class="workspace-grid is-open"' in loaded, "a load fills the pane"
  assert 'class="workspace-grid is-open is-picked"' not in loaded, (
    "a default read is not a pick"
  )
  assert f"selected={record.id}" in loaded, "a row keeps a real link to its card"

  opened = client.get(f"/?selected={record.id}").data.decode()
  assert 'class="workspace-grid is-open is-picked"' in opened
  assert "Back to the list" in opened, "a way back to the table"

  css = app.test_client().get("/static/app.css").data.decode()
  grid = css[css.index(".workspace-grid {") :].split("}", 1)[0]
  assert "240px minmax(0, 1fr) 0" in grid, "the closed grid collapses the pane"
  assert "transition: grid-template-columns" in grid
  assert ".workspace-grid:not(.is-open) .inspector {" in css, (
    "the closed card leaves the row"
  )
  assert re.search(
    r"\.workspace-grid\.is-open \{[^}]*grid-template-columns: 240px minmax\(0, 1fr\) 360px",
    css,
  ), "a wide screen keeps the list beside the open request"
  assert ".workspace-grid.is-open .records { display: none; }" not in css, (
    "a wide screen never drops the list"
  )
  assert re.search(
    r"@media \(max-width: 1199px\) \{[^@]*\.workspace-grid\.is-picked \.records \{ display: none;",
    css,
  ), "below 1200 px the picked request takes the column"
  assert (
    ".workspace-grid.is-picked .records, .workspace-grid.is-picked .filters" in css
  ), "a phone hides the list and the folded rail"
  assert ".workspace-grid.is-picked .inspector {" in css, (
    "the picked request drops the card frame"
  )

  assert ".workspace-grid .inspector { scroll-margin-top" in css, (
    "on a phone the card must land below the top bar"
  )

  js = app.test_client().get("/static/app.js").data.decode()
  assert "history.pushState" in js, "an opened card keeps a shareable url"
  assert "prefers-reduced-motion" in js, (
    "the card reveal respects the motion preference"
  )


def test_the_record_card_fades_and_slides(app):
  """The card moves with one short reveal, and the close reverses it."""
  client = app.test_client()
  css = client.get("/static/app.css").data.decode()
  entering = re.search(r"@keyframes card-in \{(.*?)\n\}", css, re.DOTALL)
  assert entering and "opacity: 0" in entering.group(1), "the card fades in"
  assert entering and "translateX" in entering.group(1), "the card slides in"
  leaving = re.search(r"@keyframes card-out \{(.*?)\n\}", css, re.DOTALL)
  assert leaving and "opacity: 0" in leaving.group(1), "the card fades out"
  assert leaving and "translateX" in leaving.group(1), "the card slides out"
  assert ".inspector.is-entering { animation: card-in" in css
  assert ".inspector.is-leaving { animation: card-out" in css
  script = client.get("/static/app.js").data.decode()
  assert 'classList.add("is-entering")' in script, "a row adds the reveal class"
  assert 'classList.add("is-leaving")' in script, "a close plays the leave class"


def test_fact_rows_share_one_baseline(app):
  css = app.test_client().get("/static/app.css").data.decode()
  rules = {sel.strip(): body for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css)}
  assert "align-items: baseline" in rules.get(".facts div", ""), (
    "the label and its value sit on one line"
  )
  assert rules.get(".facts dd", "").strip().startswith("margin: 0"), (
    "a stray top margin drops the value below the label"
  )


def test_the_share_row_gives_every_control_one_height(app):
  css = app.test_client().get("/static/app.css").data.decode()
  rules = {sel.strip(): body for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css)}
  assert "min-height: var(--control-h)" in rules.get(".share-form .field select", ""), (
    "the Access select must match the Expires input"
  )
  button = rules.get(".share-form .btn", "")
  assert "min-height: var(--control-h)" in button, "Create link must match the fields"
  assert "font-size: calc(14px * var(--font-scale))" in button, (
    "Create link must match the field text"
  )


def test_settings_rows_share_grouped_lists(app, db):
  client = _client(app, db, "Ada", "Ada Admin", roles=(Role.ADMIN,))
  body = client.get("/settings").data
  assert body.count(b'class="set-list"') >= 3


def test_notification_categories_keep_their_own_cards(app, db):
  """One list holds every category under a plain head, and one save row."""
  client = _client(app, db, "Ada", "Ada Admin", roles=(Role.ADMIN,))
  body = client.get("/settings").data
  main = body[body.index(b"settings-main") :]
  start = main.index(b'aria-label="Notifications"')
  notifications = main[start : main.index(b"<section", start)]
  assert b"<fieldset" not in notifications, "a category is a head, not a card"
  assert notifications.count(b'class="set-head"') >= 2, "each category names itself"
  assert notifications.count(b'class="set-row set-action"') == 1, "one save row"
  assert notifications.index(b'class="set-row set-action"') > notifications.rindex(
    b'class="set-head"'
  ), "the button follows the rows it saves"
  css = client.get("/static/app.css").data
  assert b".set-head {" in css
  assert b".set-head + .set-row {" in css


def test_the_passkey_block_hides_an_empty_row(app, db):
  """An empty passkey list shows one row: the button that adds one."""
  client = _client(app, db, "Ada", "Ada Admin", roles=(Role.ADMIN,))
  body = client.get("/settings").data
  assert b"data-revoke-passkey" not in body
  assert b'id="add-passkey"' in body


def test_the_switch_takes_its_on_color_from_a_token(app):
  css = app.test_client().get("/static/app.css").data.decode()
  rule = css[css.index(".switch:checked {") :].split("}", 1)[0]
  assert "var(--accent" in rule
  assert "#" not in rule


def test_header_controls_live_in_the_user_menu(app, db):
  client = _client(app, db, "Sam", "Sam Cruz", roles=(Role.ASSIGNEE,))
  body = client.get("/").data
  assert b"user-menu" in body
  assert b"theme-toggle" not in body
  assert b'aria-label="Notifications"' in body


def test_the_admin_user_page_caps_its_width(app, db):
  """The cards must not stretch the width of a wide desktop."""
  client = _client(app, db, "Ada", "Ada Admin", roles=(Role.ADMIN,))
  body = client.get("/admin/users").data
  assert b'class="admin-page"' in body
  css = client.get("/static/app.css").data.decode()
  rule = css[css.index(".admin-page {") :].split("}", 1)[0]
  assert "max-width" in rule


def test_the_four_admin_pages_share_one_width(app, db):
  """A page left out of the wrapper would stretch wider than its neighbours."""
  client = _client(app, db, "Ada", "Ada Admin", roles=(Role.ADMIN,))
  for path in ("/admin/site", "/admin/users", "/admin/shares", "/admin/audit"):
    body = client.get(path).data
    assert b'class="admin-page"' in body, path


def test_each_settings_pane_carries_a_head(app, db):
  """A pane leads with its group name and one line, and no icon tile."""
  client = _client(app, db, "Ada", "Ada Admin", roles=(Role.ADMIN,))
  body = client.get("/settings").data.decode()
  heads = re.findall(r'<header class="pane-head">.*?</header>', body, re.DOTALL)
  sections = re.findall(r'<section class="set-group" id="([\w-]+)"', body)
  assert len(heads) == len(sections) >= 5, "every pane needs one head"
  for head in heads:
    assert "pane-icon" not in head, "the tile is gone"
    assert "<h2>" in head and "<p>" in head, "the head carries a name and one line"
  css = client.get("/static/app.css").data.decode()
  assert ".pane-head > .pane-icon" not in css, "no tile rule is left over"
  assert ".set-group form:not(.modal-form)" in css, "a modal form is not a group card"
  assert ".pane-head > p { display: none; }" not in css, "the phone keeps the one line"
  wide = css[
    css.index("@media (min-width: 640px)") : css.index(
      "@media (max-width: 639px)", css.index("@media (min-width: 640px)")
    )
  ]
  assert ".settings-main > .set-group > .pane-head" not in wide, (
    "the wide head is no card"
  )
  assert ".set-group > .pane-head > h2" not in wide, "one label size at every width"
  assert (
    '.settings-shell:not(:has(.set-group:target)) .settings-nav a[data-pane="profile"]'
    in wide
  ), "the first pane opens with its row marked"
  for pane in ("profile", "appearance", "notifications", "passkeys", "admin"):
    assert f'.settings-nav a[data-pane="{pane}"]' in wide, "each pane marks its own row"
  assert "background: var(--accent-fill)" in wide, "the picked row takes the accent"
  assert ".settings-main > .set-group:target { animation: fade-in 160ms" in wide, (
    "a picked pane fades in, so the swap reads as one move"
  )


def test_the_settings_pane_takes_the_whole_width(app, db):
  """The pane and its rail match the wide layout of the rest of the app."""
  client = _client(app, db, "Ada", "Ada Admin", roles=(Role.ADMIN,))
  css = client.get("/static/app.css").data.decode()
  shell = css[css.index(".settings-shell {") :].split("}", 1)[0]
  assert "minmax(0, 1fr)" in shell, "the pane grows into the free width"
  assert "720px" not in shell, "no cap leaves a wide margin"
  rail = css[css.index(".settings-nav a {") :].split("}", 1)[0]
  assert "padding: 6px 12px" in rail, "a rail row stays a compact target"
  assert "calc(14px * var(--font-scale))" in rail, "the rail reads at body size"
  head = css[css.index(".pane-head {") :].split("}", 1)[0]
  assert "grid-template-columns: minmax(0, 1fr)" in head, "the name takes the line"
  assert "auto 1fr" not in head, "no tile sits beside the name"
  name = css[css.index(".set-group > .pane-head > h2 {") :].split("}", 1)[0]
  assert "calc(20px * var(--font-scale))" in name, "the pane name is a heading"
  body = client.get("/settings").data.decode()
  heads = re.findall(r'<header class="pane-head">(.*?)</header>', body, re.DOTALL)
  assert heads and not any("set-chip" in head for head in heads), (
    "a group head leads with its plain name"
  )


def test_the_phone_opens_one_settings_page_at_a_time(app, db):
  """The phone lists the sections first, then pushes one section page."""
  client = _client(app, db, "Ada", "Ada Admin", roles=(Role.ADMIN,))
  body = client.get("/settings").data.decode()
  assert 'class="pane-back"' in body, "a pushed page needs its way back"
  css = client.get("/static/app.css").data.decode()
  phone = css[
    css.index("@media (max-width: 639px)", css.index("@media (min-width: 640px)")) :
  ]
  assert ".settings-main > .set-group { display: none; }" in phone
  assert ".settings-main > .set-group:target { display: block; }" in phone
  assert (
    ".settings-shell:has(.set-group:target) .settings-rail { display: none; }" in phone
  )
  assert ".settings-main > .pane-back" in phone, "the back row shows on a phone"
  assert "chevron-left" in body, "the back row carries the left chevron"


def test_wide_screens_show_one_settings_pane(app, db):
  """A wide screen shows one pane. The phone keeps every group stacked."""
  client = _client(app, db, "Ada", "Ada Admin", roles=(Role.ADMIN,))
  body = client.get("/settings").data.decode()
  rail = body[body.index("settings-rail") : body.index("settings-main")]
  for pane in ("profile", "appearance", "notifications", "passkeys", "admin"):
    assert f'href="#{pane}"' in rail
    assert f'id="{pane}"' in body
  css = client.get("/static/app.css").data.decode()
  wide = css.index("@media (min-width: 640px)")
  hide = css.index(".settings-main > .set-group { display: none; }")
  phone = css.index("@media (max-width: 639px)", wide)
  assert wide < hide < phone, "the pane switch belongs to the wide screen only"
  assert ".settings-main > .set-group:target { display: block; }" in css
  assert ".settings-main > .set-group#profile," in css


def test_a_wide_rail_holds_the_page_where_it_was(app):
  """A rail row picks a pane in place, so the browser must not scroll to it."""
  script = app.test_client().get("/static/app.js").data.decode()
  assert 'document.querySelector(".settings-nav")' in script, (
    "the script finds the rail"
  )
  assert 'window.matchMedia("(min-width: 640px)")' in script, (
    "a narrow desktop keeps the rail and swaps panes in place"
  )
  assert 'a[href^="#"]' in script, "each rail row is a hash link"
  assert "location.replace(" in script, "a row replaces the hash it came from"
  assert "window.scrollTo(0, y)" in script, (
    "the page returns to the reader's place after the swap"
  )


def test_the_workspace_filters_swap_without_a_load(app, db):
  """A filter narrows one list, so both panels swap in place."""
  script = app.test_client().get("/static/app.js").data.decode()
  assert "panel.filters" in script and "panel.records" in script, (
    "the swap covers both panels"
  )
  assert 'history.pushState(null, "", url)' in script, "the URL keeps up without a load"
  assert 'fetch(url, { headers: { Accept: "text/html" } })' in script, (
    "the filter reads the next page once"
  )
  assert "keepSeg(" in script, "the picked row slides instead of jumping"
  css = app.test_client().get("/static/app.css").data.decode()
  assert ".seg-pill" in css, "one pill marks the pick"
  assert "transition: transform 220ms var(--ease)" in css, "the pill slides"
  assert ".panel.filters.is-swapping" in css, "the swap fades in"


def test_a_new_request_opens_in_the_pane(app, db):
  """The bar action fills the records pane, and no new tab opens."""
  script = app.test_client().get("/static/app.js").data.decode()
  assert 'a[href$="/requests/new"]' in script, "the bar action is the opener"
  assert 'page.querySelector(".narrow")' in script, "a form page feeds the pane"


def test_the_text_size_row_keeps_one_value(app):
  """The saved note waits for a failure, so the row shows the value once."""
  script = app.test_client().get("/static/app.js").data.decode()
  saved = script[script.index("const fontForm") :]
  saved = saved[: saved.index('range.addEventListener("change", settle);')]
  assert "Text size ${value}%" not in saved, "the row never repeats its value"
  assert 'note.textContent = ""' in saved, "a saved size clears the note"


def test_admin_row_buttons_match_their_fields(app):
  """A row with a picker and a button shows one control height."""
  css = app.test_client().get("/static/app.css").data.decode()
  field = css[css.index(".inline-form input") :].split("}", 1)[0]
  button = css[css.index(".inline-form .btn") :].split("}", 1)[0]
  assert "min-height: var(--control-h)" in field
  assert "min-height: var(--control-h)" in button, "the button must not stand shorter"
  tokens = app.test_client().get("/static/tokens.css").data.decode()
  assert "--control-h: 44px" in tokens
  assert "font-size: calc(14px * var(--font-scale))" in field
  assert "font-size: calc(14px * var(--font-scale))" in button


def test_the_role_forms_offer_only_sensible_roles(app, db):
  """Assign lists what is missing. Revoke lists what the person holds."""
  client = _client(app, db, "Ada", "Ada Admin", roles=(Role.ADMIN,))
  listing = client.get("/admin/users").data.decode()
  card = listing[listing.index("admin-user-list") :]
  opening = card.index('aria-label="Role to assign"')
  assign = card[opening : card.index("</select>", opening)]
  assert 'value="ADMIN"' not in assign, "a held role has nothing to assign"
  assert 'value="REQUESTER"' in assign
  assert 'aria-label="Role to revoke"' not in card, "own Admin stays held"


def test_an_admin_cannot_take_their_own_admin_role(app, db):
  person = users.create_user(db, "Ada", "Ada Admin", at=AT)
  assign_role(db, person.id, Role.ADMIN, at=AT)
  token = sessions.create_session(db, person.id, at=AT).token
  client = app.test_client()
  client.set_cookie(SESSION_COOKIE, token)
  answer = client.post(
    f"/admin/users/{person.id}/roles",
    data={"role": "ADMIN", "action": "revoke"},
    follow_redirects=True,
  )
  assert Role.ADMIN in list_roles(db, person.id)
  assert b"Ask another admin to remove your Admin role" in answer.data


def test_admin_rows_draw_the_rule_above(app):
  """One rule sits above each row, so a lone row ends at the card edge."""
  css = app.test_client().get("/static/app.css").data.decode()
  rule = css[css.index(".admin-user .compact-list li {") :].split("}", 1)[0]
  assert "border-top: 1px solid var(--line)" in rule
  assert "border-bottom: 0" in rule


def test_the_script_opens_the_card_as_wide_as_a_reload(app):
  """A click must land on the same classes the server writes."""
  script = app.test_client().get("/static/app.js").data.decode()
  assert 'workspaceGrid.classList.add("is-open", "is-main", "is-picked")' in script
  assert 'inspector.classList.add("is-main")' in script
  assert 'workspaceGrid.classList.remove("is-open", "is-main", "is-picked")' in script


def test_titles_lead_with_the_product(app, db):
  client = _client(app, db, "Ada", "Ada Admin", roles=(Role.ADMIN,))
  for path in ("/settings", "/admin/users", "/"):
    body = client.get(path).data.decode()
    title = re.search(r"<title>(.*?)</title>", body).group(1)
    assert title.startswith("PwedePa | "), title


def test_the_issues_page_lists_the_work_in_status_groups(app, db):
  client = _client(app, db, "sam", "Sam Cruz", roles=(Role.ASSIGNEE,))
  person = users.get_user_by_username(db, "sam")
  issues_data.save(
    db,
    Issue(
      id=1,
      title="Projector repair plan",
      description="Replace the lamp and test it.",
      requester_id=person.id,
      created_at=AT,
      updated_at=AT,
    ),
  )

  page = client.get("/issues").data.decode()

  assert 'class="board-col"' not in page, "the page is a list, not a board"
  board = page[page.index('class="narrow"') :]
  assert 'class="issue-groups"' in board, "the list sits in the one column"
  assert 'class="issue-group"' in page, "each status keeps its own group"
  assert 'class="issue-row"' in page, "an issue reads as one row"
  assert "Nothing here." not in page, "an empty status stays out of the list"
  assert record_url(1, "issues") in page
  assert "Projector repair plan" in page


def test_the_admin_home_is_a_settings_group(app, db):
  """The hub moved into Settings, so /admin hands over to the group."""
  client = _client(app, db, "Ada", "Ada Admin", roles=(Role.ADMIN,))

  response = client.get("/admin")
  assert response.status_code == 302
  assert response.headers["Location"].endswith("/settings#admin")

  page = client.get("/settings").data.decode()
  group = page[page.index('id="admin"') :]
  for path in (
    "/admin/users",
    "/admin/shares",
    "/admin/audit",
    "/admin/config",
    "/admin/site",
  ):
    assert f'href="{path}"' in group, f"the group misses {path}"


def test_the_admin_lists_read_as_dense_rows(app, db):
  """Each admin list keeps one row per item, so the page scans like a queue."""
  client = _client(app, db, "Ada", "Ada Admin", roles=(Role.ADMIN,))
  person = users.get_user_by_username(db, "Ada")
  sharing.create(db, "request", 1, ("VIEW",), person.id, at=AT)
  record_audit(
    db, "request.viewed", at=AT, actor_id=person.id, object_type="request", object_id=1
  )

  users_page = client.get("/admin/users").data.decode()
  assert 'class="admin-user-list"' in users_page
  assert users_page.count('class="admin-user"') == 1, "one row per person"
  assert 'class="admin-user-row"' in users_page, "the row holds the name and roles"
  assert 'class="admin-user-body"' in users_page, "the controls wait under the row"

  shares_page = client.get("/admin/shares").data.decode()
  assert 'class="record-list"' in shares_page, "shares read as rows"
  assert shares_page.count('class="record-row"') == 1
  assert "Request #1" in shares_page
  assert "Active" in shares_page
  assert 'class="record-table"' not in shares_page

  audit_page = client.get("/admin/audit").data.decode()
  assert 'class="record-list"' in audit_page
  assert audit_page.count('class="record-row"') == len(list_audit_events(db)), (
    "one row per event"
  )
  assert "Request viewed" in audit_page
  assert 'class="record-table"' not in audit_page


def test_the_inbox_reads_as_one_list_of_rows(app, db):
  """The inbox behaves like a mail list: one line per notice, one dismiss button."""
  client = _client(app, db, "Mara", "Mara Reyes", roles=(Role.REQUESTER,))
  person = users.get_user_by_username(db, "Mara")
  for message in ("Request #1 moved to Pending.", "Ada replied to Request #1."):
    notifications_data.notify(
      db, person.id, "activity", message, at=AT, object_type="request", object_id=1
    )

  inbox = client.get("/notifications").data.decode()

  assert 'class="notice-list"' in inbox
  assert inbox.count('class="notice"') == 2, "each notice keeps one row"
  assert 'class="notice-top"' not in inbox, "the row holds its own dismiss control"
  assert "Request #1 moved to Pending." in inbox
  assert 'aria-label="Dismiss notification"' in inbox


def test_the_settings_page_sets_a_text_size(app, db):
  from pwedepa.data import preferences

  person = users.create_user(db, "Ada", "Ada Admin", at=AT)
  token = sessions.create_session(db, person.id, at=AT).token
  client = app.test_client()
  client.set_cookie(SESSION_COOKIE, token)

  body = client.get("/settings").data
  assert b"data-font-size-form" in body
  assert b'min="85" max="130"' in body

  response = client.post("/settings/font-size", data={"font_size": "130"})
  assert response.status_code == 302
  assert preferences.get_font_size(db, person.id) == 130

  client.post("/settings/font-size", data={"font_size": "84"})
  assert preferences.get_font_size(db, person.id) == 130


def test_the_meta_line_keeps_mono_only_for_an_id(app):
  """A mono face on the whole meta line set prose in typewriter type."""
  css = app.test_client().get("/static/app.css").data.decode()
  block = css[css.index(".meta {") :].split("}", 1)[0]
  assert "monospace" not in block, "the meta line reads in the page face"
  ident = css[css.index(".meta .id {") :].split("}", 1)[0]
  assert "monospace" in ident, "an ID keeps its mono face"


def test_a_closed_pane_leaves_no_hole_under_the_list(app):
  """Two rows left 840 px of empty card, so a closed pane starts at its content."""
  css = app.test_client().get("/static/app.css").data.decode()
  grid = css[css.index(".workspace-grid { align-items: start; }") :].split("}", 1)[0]
  assert grid, "a closed pane aligns to the start"
  assert ".workspace-grid.is-open { align-items: stretch; }" in css, (
    "an open pane shares the row height"
  )


def test_every_control_and_its_summary_take_the_focus_ring(app):
  css = app.test_client().get("/static/app.css").data.decode()
  rule = css[css.index(".btn:focus-visible") :].split("{", 1)[0]
  for control in ("button:focus-visible", "summary:focus-visible"):
    assert control in rule, f"{control} falls back to the browser ring"


def test_the_form_controls_take_the_page_face(app):
  """A checkbox and a range once fell back to Arial, 13.33 px."""
  css = app.test_client().get("/static/app.css").data.decode()
  assert "input, select, textarea { font-family: inherit; }" in css


def test_the_workspace_headers_name_their_column(app, db):
  client = _client(app, db, "Sam", "Sam Cruz", roles=(Role.ASSIGNEE,))
  requests_data.save(
    db,
    Request(
      id=1,
      title="Broken projector",
      description="The projector in Room 4 is dead.",
      requester_id=users.get_user_by_username(db, "Sam").id,
      created_at=AT,
      updated_at=AT,
    ),
  )
  body = client.get("/").data.decode()
  head = body[body.index("<thead>") : body.index("</thead>")]
  assert head.count('scope="col"') == 4, "each header names its column"


def test_the_active_tab_draws_a_border_not_a_shadow(app):
  """An inset shadow on a 38 px link read as a glowing button."""
  css = app.test_client().get("/static/app.css").data.decode()
  active = css[css.index(".tabs a.is-active {") :].split("}", 1)[0]
  assert "border-color: var(--line)" in active
  assert "box-shadow" not in active, "the tab carries no shadow"


def test_the_filter_swap_announces_the_new_row_count(app, db):
  """Two panels repaint in place, so a screen reader needs the count in words."""
  client = _client(app, db, "Sam", "Sam Cruz", roles=(Role.ASSIGNEE,))
  body = client.get("/").data.decode()
  assert 'role="status" data-filter-status' in body, "the workspace carries a live line"
  script = client.get("/static/app.js").data.decode()
  assert 'grid.querySelector("[data-filter-status]")' in script
  assert "rows shown." in script


def test_the_pane_reports_a_load_and_names_a_failed_one(app, db):
  client = _client(app, db, "Sam", "Sam Cruz", roles=(Role.ASSIGNEE,))
  script = client.get("/static/app.js").data.decode()
  assert 'inspector.setAttribute("aria-busy", "true")' in script, "a load is not silent"
  assert "This record did not load." in script, "a failure names itself"
  assert "Open it as a page" in script, "a failure keeps one door open"


def test_a_phone_icon_button_reaches_a_tap_target(app):
  css = app.test_client().get("/static/app.css").data.decode()
  phone = css[css.index("@media (max-width: 899px)") :]
  assert ".mini, .icon-btn { min-height: 44px; }" in phone
  assert ".icon-btn { min-width: 44px; height: 44px; }" in phone


def test_a_phone_settings_list_keeps_its_title(app):
  """The h1 was hidden below 640 px, so the list opened with no page name."""
  css = app.test_client().get("/static/app.css").data.decode()
  phone = css[
    css.index("@media (max-width: 639px)", css.index("@media (min-width: 640px)")) :
  ]
  assert ".settings-main > h1 { font-size: calc(20px * var(--font-scale));" in phone
  assert ".settings-main > .pane-back { display: none; }" in phone
  assert (
    ".settings-shell:has(.set-group:target) .settings-main > h1 { display: none; }"
    in phone
  ), "an open pane names itself in its own heading"


def test_the_icon_tints_come_from_tokens(app):
  """A component carried six raw hex values against the token rule."""
  css = app.test_client().get("/static/app.css").data.decode()
  for tint in ("blue", "indigo", "green", "red", "amber", "gray"):
    assert f".chip-{tint} {{ background: var(--chip-{tint}); }}" in css
  assert "#4F46E5" not in css, "no component keeps a raw chip hex"


def test_the_type_scale_keeps_six_steps(app):
  """A screen that carries ten sizes reads as ten voices."""
  css = app.test_client().get("/static/app.css").data.decode()
  steps = {float(size) for size in re.findall(r"font-size: calc\(([\d.]+)px", css)}
  assert steps == {11.0, 12.0, 13.0, 14.0, 15.0, 20.0, 28.0}, sorted(steps)


def test_one_caps_treatment_remains(app):
  """Only the page eyebrow sets caps, so no label needs a second voice."""
  css = app.test_client().get("/static/app.css").data.decode()
  assert css.count("text-transform: uppercase") == 1
  eyebrow = css[css.index(".eyebrow {") :].split("}", 1)[0]
  assert "uppercase" in eyebrow
  assert "letter-spacing: 0.08em" in eyebrow


def test_the_page_title_runs_at_six_hundred(app):
  css = app.test_client().get("/static/app.css").data.decode()
  rule = css[css.index("h1 {") :].split("}", 1)[0]
  assert "28px" in rule and "font-weight: 600" in rule


def test_the_record_title_line_holds_the_state(app, db):
  """GitHub puts the state beside the title, and the author under it."""
  from datetime import timedelta

  client = _client(app, db, "Ada", "Ada Admin", roles=(Role.ADMIN,))
  person = users.get_user_by_username(db, "Ada")
  created = datetime.now(UTC) - timedelta(days=2)
  requests_data.save(
    db,
    Request(
      id=1,
      title="Broken projector",
      description="The projector in Room 4 is dead.",
      requester_id=person.id,
      created_at=created,
      updated_at=created,
    ),
  )

  page = client.get("/?selected=1").data.decode()
  line = page[
    page.index('class="issue-title-line"') : page.index(
      "</div>", page.index('class="issue-title-line"')
    )
  ]
  assert "<h1>" in line, "the title leads the line"
  assert 'class="pill st-' in line, "the state sits beside the title"

  byline = page[page.index('class="byline"') :].split("</p>", 1)[0]
  assert "Ada Admin" in byline, "the author sits under the title"
  assert "2d ago" in byline, "the age sits with the author"
  assert "opened by" not in page, "the old kicker is gone"


def test_a_comment_carries_a_rule_not_a_card(app):
  """One joined timeline reads down the page, so no comment draws a box."""
  css = app.test_client().get("/static/app.css").data.decode()
  rule = css[css.index(".timeline-comment {") :].split("}", 1)[0]
  assert "border-bottom: 1px solid var(--line)" in rule
  assert "border-radius" not in rule
  assert "background: none" in rule


def test_profile_leads_with_the_account_facts(app, db):
  from pwedepa.data import preferences

  person = users.create_user(db, "Ada", "Ada Admin", at=AT)
  assign_role(db, person.id, Role.ADMIN, at=AT)
  token = sessions.create_session(db, person.id, at=AT).token
  client = app.test_client()
  client.set_cookie(SESSION_COOKIE, token)
  preferences.set_clock(db, person.id, "24")

  body = client.get("/settings").data.decode()
  facts = body[body.index('class="set-list set-facts"') :].split("</dl>", 1)[0]
  assert "Member since" in facts and "Oct 2026" in facts
  assert "Admin" in facts
  assert "Last sign-in" in facts
  assert "just now" in facts, "the live session fills the row"
  assert body.index("set-facts") < body.index('action="/settings/profile"')


def test_the_client_list_carries_a_last_reply_line(app, db):
  from pwedepa.core import Event
  from pwedepa.data import events as events_data

  person = users.create_user(db, "Mara", "Mara Reyes", at=AT)
  token = sessions.create_session(db, person.id, at=AT).token
  client = app.test_client()
  client.set_cookie(SESSION_COOKIE, token)
  for number, title in ((1, "Broken projector"), (2, "Ladder audit")):
    requests_data.save(
      db,
      Request(
        id=number,
        title=title,
        description="A line.",
        requester_id=person.id,
        created_at=AT,
        updated_at=AT,
      ),
    )
  events_data.append(
    db,
    "request",
    1,
    Event(
      event_type="request.comment",
      actor_id=person.id,
      at=AT,
      data={"text": "A new bulb is on order."},
    ),
  )

  body = client.get("/requests").data.decode()
  assert "Mara Reyes replied ·" in body, "the row names the last reply"
  assert "No replies yet" in body, "a quiet row says so"


def test_a_row_side_cell_meets_the_row_edge(app):
  """A status pill and a stamp once sat 433 px short of the right edge."""
  css = app.test_client().get("/static/app.css").data.decode()
  rule = css[css.index(".record-row-main {") :].split("}", 1)[0]
  assert "flex: 1" in rule and "min-width: 0" in rule


def test_the_settings_rail_marks_its_row_by_pane_name(app, db):
  """The frozen demo rewrites a hash link, so the mark keys off the pane name."""
  client = _client(app, db, "Ada", "Ada Admin", roles=(Role.ADMIN,))
  body = client.get("/settings").data.decode()
  rail = body[body.index('class="settings-nav"') : body.index("</nav>")]
  assert 'data-pane="profile"' in rail
  assert 'data-pane="appearance"' in rail
  css = client.get("/static/app.css").data.decode()
  assert '.settings-nav a[data-pane="profile"]' in css
  assert '.settings-nav a[href="#profile"]' not in css, (
    "the mark no longer keys on the link"
  )


def test_a_phone_section_action_shares_the_heading_line(app, db):
  client = _client(app, db, "Ada", "Ada Admin", roles=(Role.ADMIN,))
  body = client.get("/3d-print-model").data.decode()
  heads = re.findall(r'<div class="section-head">.*?</div>', body, re.DOTALL)
  assert len(heads) == 3, "one head per section"
  requests_head = next(head for head in heads if ">Requests<" in head)
  assert "section-actions" in requests_head, "the action sits in the head"
  assert "New request" in requests_head, "the action shares the heading line"
  css = client.get("/static/app.css").data.decode()
  rule = css[css.index(".section-head {") :].split("}", 1)[0]
  assert "display: flex" in rule


def test_the_phone_pane_back_arrow_takes_the_floor(app):
  css = app.test_client().get("/static/app.css").data.decode()
  phone = css[css.index("@media (max-width: 899px)") :]
  assert ".back-to-list { display: inline-flex; min-width: 44px; height: 44px;" in phone


def test_the_phone_text_size_row_stacks_its_control(app, db):
  client = _client(app, db, "Ada", "Ada Admin", roles=(Role.ADMIN,))
  body = client.get("/settings").data.decode()
  assert body.count('class="set-row set-row-stack"') == 2, (
    "the clock and the text row name themselves"
  )
  css = client.get("/static/app.css").data.decode()
  phone = css[css.index("@media (max-width: 899px)") :]
  assert ".set-row-stack { display: grid;" in phone
  assert "grid-column: 1 / -1; justify-self: end;" in phone


def test_an_empty_admin_list_sits_in_a_panel(app, db):
  client = _client(app, db, "Ada", "Ada Admin", roles=(Role.ADMIN,))
  shares = client.get("/admin/shares").data.decode()
  assert '<div class="empty panel"><p>No share links yet.</p></div>' in shares
  db.exec_driver_sql("DELETE FROM audit_events")
  db.commit()
  audit = client.get("/admin/audit").data.decode()
  assert '<div class="empty panel"><p>No audit events yet.</p></div>' in audit


def test_a_phone_workspace_keeps_one_column_with_a_record_open(app):
  """A three-column grid at 390 pushed the list table off the screen."""
  css = app.test_client().get("/static/app.css").data.decode()
  phone = css[css.index("@media (max-width: 899px)") :]
  assert ".workspace-grid.is-open:not(.is-picked)," in phone
  assert "grid-template-columns: minmax(0, 1fr);" in phone
  wide = css[
    css.index("@media (max-width: 1199px)") : css.index("@media (min-width: 900px)")
  ]
  assert "240px minmax(0, 1fr) 0" in wide, "the narrow desktop still keeps its rail"


def test_a_settings_pane_name_starts_at_its_card_edge(app, db):
  """The name sat 16 px inside the card that its rows fill."""
  client = _client(app, db, "Ada", "Ada Admin", roles=(Role.ADMIN,))
  css = client.get("/static/app.css").data.decode()
  head = css[css.index(".pane-head {") :].split("}", 1)[0]
  assert "margin: 0 0 14px;" in head, "the name takes the card edge"
  assert "margin-left: 0" not in css.split(".pane-head {")[1].split("}")[0]
  assert ">.pane-head { margin-left: 0; }" not in css, "the phone copy is gone"


def test_the_phone_settings_controls_take_the_floor(app):
  """A theme tile was 40x32, a time button 95x32, and the slider 20 px tall."""
  css = app.test_client().get("/static/app.css").data.decode()
  phone = css[css.index("@media (max-width: 899px)") :]
  assert ".seg-control button { min-width: 44px; min-height: 44px; }" in phone
  assert ".set-row .font-size-control .slider { height: 44px; }" in phone
  assert ".font-size-control .number { min-height: 44px; }" in phone


def test_the_chooser_can_fill_the_records_pane(app, db):
  """The bar action opens the chooser in the pane, so it never comes up empty."""
  client = _client(app, db, "Mara", "Mara Reyes", roles=(Role.REQUESTER,))
  page = client.get("/requests/new").get_data(as_text=True)
  assert 'class="list-page narrow"' in page, "the pane reads the chooser"


def test_a_picked_row_carries_no_cell_tint_below_the_pane(app, db):
  staff = _client(app, db, "Sam", "Sam Cruz", roles=(Role.ASSIGNEE,))
  css = staff.get("/static/app.css").data.decode()
  phone = css[css.rindex("@media (max-width: 1199px)") :]
  rule = phone[phone.index("tr.is-selected td") :].split("}", 1)[0]
  assert "background: transparent" in rule, "no row reads as picked without the pane"


def test_a_typed_token_url_lands_on_the_users_page(app, db):
  admin = _client(app, db, "Ada", "Ada Admin", roles=(Role.ADMIN,))
  answer = admin.get("/admin/tokens")
  assert answer.status_code == 302
  assert answer.headers["Location"].endswith("/admin/users")


def test_nuu_recipes_are_integrated(app):
  """Verify adopted nuu recipes in stylesheets and client scripts."""
  client = app.test_client()
  css = client.get("/static/app.css").data.decode()
  js = client.get("/static/app.js").data.decode()

  # Live dot recipe
  assert ".dot { width: 6px; height: 6px;" in css
  assert "animation: pulse 1.4s" in css

  # Scroll-edge fade recipe
  assert "--edge-fade: 12px;" in css
  assert "--edge-ramp: 192px;" in css
  assert "animation-timeline: scroll(self)" in css

  # Table to cards recipe
  assert "@media (max-width: 75em)" in css
  assert ".table-cards { display: block;" in css

  # Loading bar recipe
  assert "animation: nuu-edge-loading" in css

  # Anti-clipping recipe
  assert '[role="tooltip"]' in css

  # Client-side relative timestamps recipe
  assert "window.relativeTime = function relativeTime" in js

  # Page memory recipe
  assert "pageMemory = new Map()" in js
