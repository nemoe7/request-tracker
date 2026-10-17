"""The workspace inbox: unread items sit above the opened ones."""

from datetime import UTC, datetime

import pytest

from pwedepa.auth import Role, assign_role, sessions, users
from pwedepa.core import Request
from pwedepa.data import db as data_db
from pwedepa.data import requests as requests_data
from pwedepa.web import SESSION_COOKIE, create_app

AT = datetime(2026, 10, 17, 9, 0, tzinfo=UTC)


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


def _client(app, db, name, roles=()):
  person = users.create_user(db, name, name.title(), at=AT)
  for role in roles:
    assign_role(db, person.id, role, at=AT)
  token = sessions.create_session(db, person.id, at=AT).token
  client = app.test_client()
  client.set_cookie(SESSION_COOKIE, token)
  return client, person


@pytest.fixture
def staff(app, db):
  return _client(app, db, "Ada", roles=(Role.ADMIN,))


def _request(db, number, requester_id, title):
  record = Request(
    id=number,
    title=title,
    description="Because it matters.",
    requester_id=requester_id,
    created_at=AT,
    updated_at=AT,
    domains=("Gym",),
  )
  return requests_data.save(db, record)


def _order(body: str) -> tuple[int, int]:
  """Return the offsets of the unread and opened groups, or -1 when absent."""
  return body.find('id="group-unread"'), body.find('id="group-opened"')


def test_an_unopened_request_sits_above_an_opened_one(db, staff):
  client, person = staff
  _request(db, 1, person.id, "Rope climb plan")
  _request(db, 2, person.id, "Ladder audit")
  client.get("/gym/requests/1")

  body = client.get("/workspace").get_data(as_text=True)
  unread, opened = _order(body)
  assert unread != -1 and opened != -1, "the inbox carries both groups"
  assert "/gym/requests/2" in body[unread:opened], "the unread request sits on top"
  assert "/gym/requests/1" in body[opened:], "the opened request sits below"


def test_opening_an_item_in_the_workspace_marks_it_read(db, staff):
  client, person = staff
  _request(db, 1, person.id, "Rope climb plan")

  client.get("/workspace?selected=1")
  body = client.get("/workspace").get_data(as_text=True)
  unread, opened = _order(body)

  assert "/gym/requests/1" in body[opened:]
  assert "/gym/requests/1" not in body[unread:opened]


def test_each_staff_member_keeps_their_own_read_list(db, staff):
  client, person = staff
  _request(db, 1, person.id, "Rope climb plan")
  other, _ = _client(app=client.application, db=db, name="Sam", roles=(Role.ADMIN,))

  client.get("/workspace?selected=1")
  body = other.get("/workspace").get_data(as_text=True)

  unread, opened = _order(body)
  assert "/gym/requests/1" in body[unread:opened]


def test_the_opened_item_takes_the_wide_card(db, staff):
  client, person = staff
  _request(db, 1, person.id, "Rope climb plan")

  body = client.get("/workspace?selected=1").get_data(as_text=True)
  assert 'class="workspace-grid is-open is-main"' in body
  assert 'class="panel inspector is-main"' in body


def test_the_mobile_view_offers_a_way_back(db, staff):
  client, person = staff
  _request(db, 1, person.id, "Rope climb plan")

  body = client.get("/workspace?selected=1").get_data(as_text=True)
  assert 'class="back-to-list"' in body
