import re
from datetime import UTC, datetime

import pytest

from pwedepa.auth import Role, assign_role, sessions, users
from pwedepa.data import db as data_db
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


def test_requester_leaves_workspace_for_my_requests(app, db):
  client = _client(app, db, "Mara", "Mara Reyes", roles=(Role.REQUESTER,))
  response = client.get("/workspace")
  assert response.status_code == 302
  assert "/my" in response.headers["Location"]


def test_assignee_keeps_workspace(app, db):
  client = _client(app, db, "Sam", "Sam Cruz", roles=(Role.ASSIGNEE,))
  assert client.get("/workspace").status_code == 200


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


def test_normal_service_worker_keeps_its_cache(app):
  body = app.test_client().get("/sw.js").data
  assert b"pwedepa-v3" in body


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


def test_workspace_centers_the_inspector(app, db):
  client = _client(app, db, "Sam", "Sam Cruz", roles=(Role.ASSIGNEE,))
  body = client.get("/workspace").data
  assert body.index(b"panel inspector") < body.index(b"panel records")
  assert b"<th>Requester</th>" not in body
  assert b"<th>Domain</th>" not in body
  assert b"Open the board" not in body


def test_settings_rows_share_grouped_lists(app, db):
  client = _client(app, db, "Ada", "Ada Admin", roles=(Role.ADMIN,))
  body = client.get("/settings").data
  assert body.count(b'class="ios-list"') >= 3


def test_header_controls_live_in_the_user_menu(app, db):
  client = _client(app, db, "Sam", "Sam Cruz", roles=(Role.ASSIGNEE,))
  body = client.get("/workspace").data
  assert b"user-menu" in body
  assert b"theme-toggle" not in body
  assert b'aria-label="Notifications"' in body
