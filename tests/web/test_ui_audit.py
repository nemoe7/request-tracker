import re
from datetime import UTC, datetime

import pytest

from pwedepa.auth import Role, assign_role, sessions, users
from pwedepa.core import Request
from pwedepa.data import db as data_db
from pwedepa.data import requests as requests_data
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
  response = client.get("/workspace")
  assert response.status_code == 302
  assert "/requests" in response.headers["Location"]


def test_the_requests_list_answers_at_requests(app, db):
  client = _client(app, db, "Mara", "Mara Reyes", roles=(Role.REQUESTER,))
  assert client.get("/requests").status_code == 200
  assert client.get("/my").status_code == 404


def test_assignee_keeps_workspace(app, db):
  client = _client(app, db, "Sam", "Sam Cruz", roles=(Role.ASSIGNEE,))
  assert client.get("/workspace").status_code == 200


def _nav_tabs(html: str) -> list[str]:
  block = re.search(r'<nav class="tabs".*?</nav>', html, re.DOTALL)
  assert block, "the top bar carries no tab strip"
  return re.findall(r"</svg>([^<]+)</a>", block.group(0))


def test_staff_see_the_workspace_alone(app, db):
  client = _client(app, db, "Sam", "Sam Cruz", roles=(Role.ASSIGNEE,))
  tabs = _nav_tabs(client.get("/workspace").get_data(as_text=True))
  assert tabs == ["Workspace"]


def test_admins_see_the_workspace_alone(app, db):
  client = _client(app, db, "Ana", "Ana Lim", roles=(Role.ADMIN,))
  tabs = _nav_tabs(client.get("/workspace").get_data(as_text=True))
  assert tabs == ["Workspace"]


def test_the_phone_drops_a_single_stop_nav(app, db):
  staff = _client(app, db, "Sam", "Sam Cruz", roles=(Role.ASSIGNEE,))
  staff_page = staff.get("/workspace").get_data(as_text=True)
  assert '<body class="is-staff">' in staff_page
  css = staff.get("/static/app.css").data.decode()
  blocks = re.findall(r"@media \(max-width: 899px\) \{(.*?)\n\}", css, re.DOTALL)
  assert blocks, "the phone blocks hold the bottom bar rules"
  hidden = [re.search(r"body\.is-staff \.tabs \{([^}]*)\}", block) for block in blocks]
  assert any(match and "display: none" in match.group(1) for match in hidden), (
    "one stop needs no bar"
  )
  client = _client(app, db, "Mara", "Mara Reyes", roles=(Role.REQUESTER,))
  assert '<body class="is-staff">' not in client.get("/requests").get_data(as_text=True)


def test_the_phone_workspace_folds_its_filters(app, db):
  """On a phone the list leads, and one row opens the rail."""
  client = _client(app, db, "Sam", "Sam Cruz", roles=(Role.ASSIGNEE,))
  page = client.get("/workspace").get_data(as_text=True)
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
  orders = dict(re.findall(r"\.workspace-grid \.(\w+) \{ order: (\d)", phone))
  assert int(orders["records"]) < int(orders["filters"]), "the list leads on a phone"


def test_the_stylesheet_holds_one_phone_block(app):
  css = app.test_client().get("/static/app.css").data.decode()
  assert len(re.findall(r"@media \(max-width: 899px\)", css)) == 1, (
    "phones read in one place"
  )


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
  page = client.get("/workspace").get_data(as_text=True)
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


def test_demo_keeps_pages_fresh_and_lets_assets_revalidate(demo_app):
  client = demo_app.test_client()
  page = client.get("/login")
  assert "no-store" in page.headers.get("Cache-Control", "")
  asset = client.get("/static/app.css")
  assert "no-store" not in asset.headers.get("Cache-Control", "")
  assert "no-cache" in asset.headers.get("Cache-Control", "")


def test_the_header_defers_the_animated_icon(app):
  client = app.test_client()
  body = client.get("/").data
  assert b'class="icon-animated" data-src="/static/icons/icon-animated.webp"' in body
  assert b'class="icon-animated" src=' not in body
  assert b"dataset.src" in client.get("/static/app.js").data


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


def test_client_cards_open_the_record_from_anywhere(app, db):
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
  assert f'href="/requests/{record.id}"' in body
  assert 'class="card is-linked"' in body, "a client card only opens from its title"

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
  assert b".ios-input:focus { outline: none; text-align: left; }" not in css


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
  for control in ("input", "select", "textarea", ".ios-input"):
    assert any(f"{control}:focus-visible" in selector for selector in ringed), (
      f"{control} loses its focus ring"
    )
  quiet = css.index(".ios-input:focus {")
  visible = css.index(".ios-input:focus-visible")
  assert quiet < visible, "the quiet rule must come first, so the ring wins"


def test_settings_rail_carries_icon_rows_and_a_phone_list(app, db):
  client = _client(app, db, "Ada", "Ada Admin", roles=(Role.ADMIN,))
  body = client.get("/settings").data.decode()
  rail = body[body.index("settings-rail") : body.index("settings-main")]
  assert rail.count("ios-chip") >= 4
  assert rail.count("chevron-right") >= 4
  css = client.get("/static/app.css").data.decode()
  assert ".settings-nav { display: none; }" not in css
  phone = css[css.index("@media (max-width: 899px)") :]
  assert ".settings-nav { background: var(--surface)" in phone
  assert ".settings-nav .chev { display: block; }" in phone


def test_wide_screens_stretch_the_shell(app):
  css = app.test_client().get("/static/app.css").data.decode()
  block = css[css.index("@media (min-width: 1200px)") :]
  block = block[: block.index("}") + 1]
  assert ".wrap { max-width:" in block
  assert "1100px" not in block


def test_workspace_centers_the_inspector(app, db):
  client = _client(app, db, "Sam", "Sam Cruz", roles=(Role.ASSIGNEE,))
  body = client.get("/workspace").data
  assert body.index(b"panel inspector") < body.index(b"panel records")
  assert b"<th>Requester</th>" not in body
  assert b"<th>Domain</th>" not in body
  assert b"Open the board" not in body


def test_workspace_opens_two_cards_then_swaps_the_centre_one(app, db):
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

  closed = client.get("/workspace").data.decode()
  assert 'class="workspace-grid"' in closed, "the list opens alone, with no card"
  assert 'class="workspace-grid is-open"' not in closed
  assert f"selected={record.id}" in closed, "a row keeps a real link to its card"

  opened = client.get(f"/workspace?selected={record.id}").data.decode()
  assert 'class="workspace-grid is-open"' in opened

  css = app.test_client().get("/static/app.css").data.decode()
  grid = css[css.index(".workspace-grid {") :].split("}", 1)[0]
  assert "240px 0" in grid, "the closed grid collapses the centre track"
  assert "transition: grid-template-columns" in grid
  assert ".workspace-grid:not(.is-open) .inspector {" in css, (
    "the closed card leaves the row"
  )
  wide = css[css.index("@media (min-width: 1200px)") :]
  assert re.search(r"\.workspace-grid\.is-open \{[^}]*240px 360px", wide), (
    "the design doc holds the inspector at 360px"
  )

  assert ".workspace-grid .inspector { scroll-margin-top" in css, (
    "on a phone the card must land below the top bar"
  )

  js = app.test_client().get("/static/app.js").data.decode()
  assert "history.pushState" in js, "an opened card keeps a shareable url"
  assert "prefers-reduced-motion" in js, (
    "the card reveal respects the motion preference"
  )


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
  assert "min-height: 44px" in rules.get(".share-form .field select", ""), (
    "the Access select must match the Expires input"
  )
  button = rules.get(".share-form .btn", "")
  assert "min-height: 44px" in button, "Create link must match the fields"
  assert "font-size: 14px" in button, "Create link must match the field text"


def test_settings_rows_share_grouped_lists(app, db):
  client = _client(app, db, "Ada", "Ada Admin", roles=(Role.ADMIN,))
  body = client.get("/settings").data
  assert body.count(b'class="ios-list"') >= 3


def test_notification_categories_keep_their_own_cards(app, db):
  """Each category is a card. The save row belongs to the card it saves."""
  client = _client(app, db, "Ada", "Ada Admin", roles=(Role.ADMIN,))
  body = client.get("/settings").data
  assert b'class="ios-split"' in body
  assert body.count(b"<fieldset") == body.count(b"</fieldset>") >= 2
  card = body[body.rindex(b"<fieldset") : body.rindex(b"</fieldset>")]
  assert b"<legend>" in card
  assert b"Save notifications" in card, "a stray card for the button is the bug"
  css = client.get("/static/app.css").data
  split = css[css.index(b".ios-split") :]
  assert b".ios-split .ios-fieldset {" in split
  assert b"border-radius: 16px" in split[:400]
  assert b".ios-split > .ios-action {" not in css, "the button needs no card of its own"


def test_the_passkey_block_hides_an_empty_row(app, db):
  """With no passkey, one row is left: the button that adds one."""
  client = _client(app, db, "Ada", "Ada Admin", roles=(Role.ADMIN,))
  body = client.get("/settings").data
  assert b"No passkeys yet." not in body
  assert b"Add a passkey" in body


def test_the_switch_takes_its_on_color_from_a_token(app):
  css = app.test_client().get("/static/app.css").data.decode()
  rule = css[css.index(".switch:checked {") :].split("}", 1)[0]
  assert "var(--accent" in rule
  assert "#" not in rule


def test_header_controls_live_in_the_user_menu(app, db):
  client = _client(app, db, "Sam", "Sam Cruz", roles=(Role.ASSIGNEE,))
  body = client.get("/workspace").data
  assert b"user-menu" in body
  assert b"theme-toggle" not in body
  assert b'aria-label="Notifications"' in body
