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
from pwedepa.core import Issue, Request, RequestStatus
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
  """On a phone the list leads, and one row opens the rail."""
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
  orders = dict(re.findall(r"\.workspace-grid \.(\w+) \{ order: (\d)", phone))
  assert int(orders["records"]) < int(orders["filters"]), "the list leads on a phone"


def test_the_stylesheet_holds_one_phone_block(app):
  css = app.test_client().get("/static/app.css").data.decode()
  assert ".workspace-grid.is-main" in css, "the wide card needs its own grid rule"
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


def test_workspace_puts_the_reading_pane_right_of_the_list(app, db):
  """The list comes first, and the record card reads on its right."""
  client = _client(app, db, "Sam", "Sam Cruz", roles=(Role.ASSIGNEE,))
  body = client.get("/").data
  assert body.index(b"panel records") < body.index(b"panel inspector")
  assert b"<th>Requester</th>" not in body
  assert b"<th>Domain</th>" not in body
  assert b'class="client-dash"' not in body


def test_the_workspace_list_carries_one_toolbar(app, db):
  """One row over the list holds the title, the status filter, and the action."""
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
  assert "New request" in toolbar, "the action sits in the row"
  assert 'class="btn primary"' not in toolbar, "a staff page does not lead with it"
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
  assert "max-width" in grid.group(1) and "margin" in grid.group(1), (
    "the page stays a centered column"
  )


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


def test_the_workspace_centers_the_open_request(app, db):
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

  closed = client.get("/").data.decode()
  assert 'class="workspace-grid"' in closed, "the list opens alone, with no card"
  assert 'class="workspace-grid is-open"' not in closed
  assert f"selected={record.id}" in closed, "a row keeps a real link to its card"

  opened = client.get(f"/?selected={record.id}").data.decode()
  assert 'class="workspace-grid is-open is-main"' in opened
  assert "Back to the list" in opened, "a way back to the table"

  css = app.test_client().get("/static/app.css").data.decode()
  grid = css[css.index(".workspace-grid {") :].split("}", 1)[0]
  assert "240px minmax(0, 1fr) 0" in grid, "the closed grid collapses the pane"
  assert "transition: grid-template-columns" in grid
  assert ".workspace-grid:not(.is-open) .inspector {" in css, (
    "the closed card leaves the row"
  )
  assert re.search(
    r"\.workspace-grid\.is-open \{[^}]*grid-template-columns: minmax\(0, 1fr\)"
    r"[^}]*max-width: 1100px",
    css,
  ), "the open request holds one centered column"
  assert re.search(
    r"\.workspace-grid\.is-open \.filters, \.workspace-grid\.is-open \.records "
    r"\{ display: none;",
    css,
  ), "the table steps aside"
  assert ".workspace-grid.is-open.is-main .inspector {" in css, (
    "the open request drops the card frame"
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
  assert b'class="ios-row ios-action"' in card, "a stray card for the button is the bug"
  css = client.get("/static/app.css").data
  split = css[css.index(b".ios-split") :]
  assert b".ios-split .ios-fieldset {" in split
  assert b"border-radius: 16px" in split[:400]
  assert b".ios-split > .ios-action {" not in css, "the button needs no card of its own"


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
  for path in ("/admin", "/admin/users", "/admin/shares", "/admin/audit"):
    body = client.get(path).data
    assert b'class="admin-page"' in body, path


def test_each_settings_pane_carries_a_head(app, db):
  """Mac Settings leads each pane with its icon, name, and one line."""
  client = _client(app, db, "Ada", "Ada Admin", roles=(Role.ADMIN,))
  body = client.get("/settings").data.decode()
  heads = re.findall(r'<header class="pane-head">.*?</header>', body, re.DOTALL)
  sections = re.findall(r'<section class="ios-group" id="([\w-]+)"', body)
  assert len(heads) == len(sections) >= 5, "every pane needs one head"
  for head in heads:
    assert 'class="pane-icon' in head, "the head carries its icon tile"
    assert "<h2>" in head and "<p>" in head, "the head carries a name and one line"
  css = client.get("/static/app.css").data.decode()
  assert ".pane-head > .pane-icon, .pane-head > p { display: none; }" in css, (
    "the phone keeps the small label"
  )
  wide = css[
    css.index("@media (min-width: 900px)") : css.index("@media (max-width: 899px)")
  ]
  assert ".settings-main > .ios-group > .pane-head" in wide, (
    "the wide head carries the card"
  )
  assert "display: flex; flex-direction: column" in wide
  assert ".ios-group > .pane-head > h2" in wide, "the head carries the title"
  assert (
    '.settings-shell:not(:has(.ios-group:target)) .settings-nav a[href="#profile"]'
    in wide
  ), "the first pane opens with its row marked"
  for pane in ("profile", "appearance", "notifications", "passkeys", "admin"):
    assert f'.settings-nav a[href="#{pane}"]' in wide, "each pane marks its own row"
  assert "background: var(--accent-fill)" in wide, "the picked row takes the accent"


def test_the_phone_opens_one_settings_page_at_a_time(app, db):
  """The phone lists the sections first, then pushes one section page."""
  client = _client(app, db, "Ada", "Ada Admin", roles=(Role.ADMIN,))
  body = client.get("/settings").data.decode()
  assert 'class="pane-back"' in body, "a pushed page needs its way back"
  css = client.get("/static/app.css").data.decode()
  phone = css[css.index("@media (max-width: 899px)") :]
  assert ".settings-main > .ios-group { display: none; }" in phone
  assert ".settings-main > .ios-group:target { display: block; }" in phone
  assert (
    ".settings-shell:has(.ios-group:target) .settings-rail { display: none; }" in phone
  )
  assert ".settings-main > .pane-back" in phone, "the back row shows on a phone"
  assert "chevron-left" in body, "the back row carries the left chevron"


def test_wide_screens_show_one_settings_pane(app, db):
  """Mac Settings shows one pane. The phone keeps every group stacked."""
  client = _client(app, db, "Ada", "Ada Admin", roles=(Role.ADMIN,))
  body = client.get("/settings").data.decode()
  rail = body[body.index("settings-rail") : body.index("settings-main")]
  for pane in ("profile", "appearance", "notifications", "passkeys", "admin"):
    assert f'href="#{pane}"' in rail
    assert f'id="{pane}"' in body
  css = client.get("/static/app.css").data.decode()
  wide = css.index("@media (min-width: 900px)")
  hide = css.index(".settings-main > .ios-group { display: none; }")
  phone = css.index("@media (max-width: 899px)")
  assert wide < hide < phone, "the pane switch belongs to the wide screen only"
  assert ".settings-main > .ios-group:target { display: block; }" in css
  assert ".settings-main > .ios-group#profile," in css


def test_admin_row_buttons_match_their_fields(app):
  """A row with a picker and a button shows one control height."""
  css = app.test_client().get("/static/app.css").data.decode()
  field = css[css.index(".inline-form input") :].split("}", 1)[0]
  button = css[css.index(".inline-form .btn") :].split("}", 1)[0]
  assert "min-height: var(--control-h)" in field
  assert "min-height: var(--control-h)" in button, "the button must not stand shorter"
  tokens = app.test_client().get("/static/tokens.css").data.decode()
  assert "--control-h: 44px" in tokens
  assert "font-size: 14px" in field
  assert "font-size: 14px" in button


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
  assert b"You cannot remove your own Admin role" in answer.data


def test_admin_rows_draw_the_rule_above(app):
  """One rule sits above each row, so a lone row ends at the card edge."""
  css = app.test_client().get("/static/app.css").data.decode()
  rule = css[css.index(".admin-user .compact-list li {") :].split("}", 1)[0]
  assert "border-top: 1px solid var(--line)" in rule
  assert "border-bottom: 0" in rule


def test_the_script_opens_the_card_as_wide_as_a_reload(app):
  """A click must land on the same classes the server writes."""
  script = app.test_client().get("/static/app.js").data.decode()
  assert 'workspaceGrid.classList.add("is-open", "is-main")' in script
  assert 'inspector.classList.add("is-main")' in script
  assert 'workspaceGrid.classList.remove("is-open", "is-main")' in script


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
  assert 'class="issue-group"' in page, "each status keeps its own group"
  assert 'class="issue-row"' in page, "an issue reads as one row"
  assert "Nothing here." not in page, "an empty status stays out of the list"
  assert record_url(1, "issues") in page
  assert "Projector repair plan" in page


def test_the_admin_home_lists_its_sections_as_rows(app, db):
  """Four equal cards waste the width a dense list uses."""
  client = _client(app, db, "Ada", "Ada Admin", roles=(Role.ADMIN,))

  page = client.get("/admin").data.decode()

  assert 'class="admin-links"' in page, "the sections read as one list"
  assert page.count('class="admin-link"') == 4, "each section keeps one row"
  assert 'class="cards"' not in page
  for path in ("/admin/users", "/admin/shares", "/admin/audit", "/admin/config"):
    assert f'href="{path}"' in page, f"the list misses {path}"


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
  assert "request.viewed" in audit_page
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
