"""Domain announcements: staff publish and edit them, clients read them."""

from datetime import UTC, datetime

import pytest

from pwedepa.auth import Role, assign_role, sessions, users
from pwedepa.data import announcements as announcements_data
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


@pytest.fixture
def requester(app, db):
  return _client(app, db, "Mara", roles=(Role.REQUESTER,))


def _post(client, path, title="A new floor", body="The floor opens on Monday."):
  return client.post(path, data={"title": title, "body": body})


def test_a_staff_member_publishes_an_announcement(db, staff):
  client, person = staff
  done = _post(client, "/gym/announcements")

  assert done.status_code == 302
  assert done.headers["Location"] == "/gym"
  saved = announcements_data.list_for_domain(db, "Gym")
  assert len(saved) == 1
  assert saved[0].author_id == person.id
  page = client.get("/gym").get_data(as_text=True)
  assert "A new floor" in page
  assert "The floor opens on Monday." in page
  assert "Ada" in page


def test_an_announcement_stays_on_its_domain(db, staff):
  client, _ = staff
  _post(client, "/gym/announcements")

  assert "A new floor" in client.get("/gym").get_data(as_text=True)
  assert "A new floor" not in client.get("/asset-tracker").get_data(as_text=True)


def test_an_edit_replaces_the_text_and_marks_the_time(db, staff):
  client, _ = staff
  _post(client, "/gym/announcements")

  done = _post(
    client,
    "/gym/announcements/1/edit",
    title="A new floor",
    body="The floor opens on Tuesday.",
  )
  assert done.status_code == 302
  saved = announcements_data.get(db, 1)
  assert saved.body == "The floor opens on Tuesday."
  assert saved.edited_at is not None
  page = client.get("/gym").get_data(as_text=True)
  assert "The floor opens on Tuesday." in page
  assert "edited" in page


def test_the_edit_form_opens_filled_in(db, staff):
  client, _ = staff
  _post(client, "/gym/announcements")

  page = client.get("/gym/announcements/1/edit")
  assert page.status_code == 200
  assert b"The floor opens on Monday." in page.data


def test_a_client_cannot_manage_announcements(db, requester):
  person_client, _ = requester
  assert person_client.get("/gym/announcements/new").status_code == 403
  assert _post(person_client, "/gym/announcements").status_code == 403


def test_an_edit_under_another_domain_answers_404(db, staff):
  client, _ = staff
  _post(client, "/gym/announcements")

  assert _post(client, "/asset-tracker/announcements/1/edit").status_code == 404


def test_an_empty_announcement_keeps_the_form(db, staff):
  client, _ = staff
  done = _post(client, "/gym/announcements", title="", body="No title here.")

  assert done.status_code == 200
  assert b"needs a title and a body" in done.data
  assert announcements_data.list_for_domain(db, "Gym") == []


def test_a_signed_out_visitor_lands_on_the_login_page(app, db):
  answer = app.test_client().get("/gym/announcements/new")
  assert answer.status_code == 302
  assert answer.headers["Location"] == "/login"
