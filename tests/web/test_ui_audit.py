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


def test_normal_service_worker_keeps_its_cache(app):
  body = app.test_client().get("/sw.js").data
  assert b"pwedepa-v3" in body


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
