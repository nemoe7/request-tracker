"""The client mini dashboard: what the client can see now, and one wide card."""

from datetime import UTC, datetime

import pytest

from pwedepa.auth import Role, assign_role, sessions, users
from pwedepa.core import Request, Visibility
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


def _person(db, name):
  person = users.create_user(db, name, name.title(), at=AT)
  assign_role(db, person.id, Role.REQUESTER, at=AT)
  return person


def _client(app, db, person):
  token = sessions.create_session(db, person.id, at=AT).token
  client = app.test_client()
  client.set_cookie(SESSION_COOKIE, token)
  return client


def _request(db, number, requester_id, title, visibility=Visibility.PRIVATE):
  return requests_data.save(
    db,
    Request(
      id=number,
      title=title,
      description="Because it matters.",
      requester_id=requester_id,
      visibility=visibility,
      created_at=AT,
      updated_at=AT,
      domains=("Gym",),
    ),
  )


def test_the_client_sees_what_is_visible_now(app, db):
  Mara = _person(db, "Mara")
  Sam = _person(db, "Sam")
  _request(db, 1, Mara.id, "My own request")
  _request(db, 2, Sam.id, "A public request", visibility=Visibility.PUBLIC)
  _request(db, 3, Sam.id, "A private request")
  client = _client(app, db, Mara)

  body = client.get("/requests").get_data(as_text=True)

  assert 'id="today"' in body
  assert "/gym/requests/1" in body
  assert "/gym/requests/2" in body
  assert "/gym/requests/3" not in body


def test_each_card_opens_the_wide_card(app, db):
  Mara = _person(db, "Mara")
  _request(db, 1, Mara.id, "My own request")
  client = _client(app, db, Mara)

  body = client.get("/requests").get_data(as_text=True)

  assert 'href="/requests?selected=1"' in body, "a card opens its own wide card"
  assert 'href="/gym/requests/1"' in body, "the card keeps a link to the request"


def test_a_selected_item_opens_as_the_wide_card(app, db):
  Mara = _person(db, "Mara")
  _request(db, 1, Mara.id, "My own request")
  client = _client(app, db, Mara)

  body = client.get("/requests?selected=1").get_data(as_text=True)

  assert 'class="client-dash is-open is-main"' in body
  assert 'class="panel inspector is-main"' in body
  assert 'class="back-to-list"' in body


def test_another_persons_private_item_opens_no_card(app, db):
  Mara = _person(db, "Mara")
  Sam = _person(db, "Sam")
  _request(db, 3, Sam.id, "A private request")
  client = _client(app, db, Mara)

  body = client.get("/requests?selected=3").get_data(as_text=True)

  assert 'class="panel inspector is-main"' not in body
  assert "/gym/requests/3" not in body
