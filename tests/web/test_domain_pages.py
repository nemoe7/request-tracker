"""Domain pages and the domain-first item URLs."""

from datetime import UTC, datetime

import pytest

from pwedepa.auth import Role, assign_role, sessions, users
from pwedepa.core import Issue, Request
from pwedepa.data import db as data_db
from pwedepa.data import domains as domains_data
from pwedepa.data import issues as issues_data
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


def _client(app, db, name, roles=()):
  person = users.create_user(db, name, name.title(), at=AT)
  for role in roles:
    assign_role(db, person.id, role, at=AT)
  token = sessions.create_session(db, person.id, at=AT).token
  client = app.test_client()
  client.set_cookie(SESSION_COOKIE, token)
  return client, person


@pytest.fixture
def Mara(app, db):
  return _client(app, db, "Mara", roles=(Role.REQUESTER,))


def _request(db, number, requester_id, **overrides):
  record = Request(
    id=number,
    title=overrides.pop("title", "A record"),
    description="Because it matters.",
    requester_id=requester_id,
    created_at=AT,
    updated_at=AT,
    **overrides,
  )
  return requests_data.save(db, record)


def test_a_domain_page_shows_its_description_and_its_records(db, Mara):
  client, person = Mara
  mine = _request(db, 1, person.id, title="Rope climb plan", domains=("Gym",))
  other = _request(
    db, 2, person.id, title="Borrowed ladder", domains=("Asset Tracker",)
  )
  found = domains_data.find("gym")

  page = client.get(f"/{found.slug}")
  assert page.status_code == 200
  assert found.description.encode() in page.data
  assert mine.title.encode() in page.data
  assert other.title.encode() not in page.data


def test_a_record_opens_under_each_of_its_domains(db, Mara):
  client, person = Mara
  _request(db, 1, person.id, domains=("Gym", "Asset Tracker"))
  issues_data.save(
    db,
    Issue(
      id=1,
      title="A loose bolt",
      description="x",
      requester_id=person.id,
      created_at=AT,
      updated_at=AT,
      domains=("Gym", "Asset Tracker"),
    ),
  )

  assert client.get("/gym/requests/1").status_code == 200
  assert client.get("/asset-tracker/requests/1").status_code == 200
  assert client.get("/daedalus/requests/1").status_code == 404
  gym = client.get("/gym").get_data(as_text=True)
  asset = client.get("/asset-tracker").get_data(as_text=True)
  assert 'href="/gym/requests/1"' in gym
  assert 'href="/asset-tracker/requests/1"' in asset
  assert 'href="/asset-tracker/issues/1"' in asset


def test_the_old_record_urls_answer_404(db, Mara):
  client, person = Mara
  _request(db, 1, person.id)
  issues_data.save(
    db,
    Issue(
      id=1,
      title="An issue",
      description="x",
      requester_id=person.id,
      created_at=AT,
      updated_at=AT,
    ),
  )

  assert client.get("/requests/1").status_code == 404
  assert client.get("/issues/1").status_code == 404


def test_the_create_form_offers_the_configured_domains(db, Mara):
  client, _ = Mara
  page = client.get("/requests/new")

  assert b'name="domains"' in page.data
  for domain in domains_data.load():
    assert f'value="{domain.name}"'.encode() in page.data
  assert b'name="domains" type="text"' not in page.data, "the free text field is gone"


def test_a_new_request_keeps_the_checked_domains(db, Mara):
  client, _ = Mara
  done = client.post(
    "/requests",
    data={
      "title": "Rope climb plan",
      "description": "A plan.",
      "domains": ["Gym", "Asset Tracker"],
      "visibility": "PRIVATE",
    },
  )

  saved = requests_data.get(db, 1)
  assert saved.domains == ("Gym", "Asset Tracker")
  assert done.headers["Location"] == "/gym/requests/1"


def test_an_unknown_domain_is_dropped(db, Mara):
  client, _ = Mara
  client.post(
    "/requests",
    data={"title": "Rope climb plan", "domains": ["Not A Domain"]},
  )

  assert requests_data.get(db, 1).domains == ()


def test_a_domain_page_lists_its_records_as_dense_rows(db, Mara):
  client, person = Mara
  _request(db, 1, person.id, title="Rope climb plan", domains=("Gym",))
  issues_data.save(
    db,
    Issue(
      id=1,
      title="A loose bolt",
      description="x",
      requester_id=person.id,
      created_at=AT,
      updated_at=AT,
      domains=("Gym",),
    ),
  )

  page = client.get("/gym").get_data(as_text=True)

  assert page.count('class="record-list"') == 2, (
    "requests and issues each hold one list"
  )
  assert page.count('class="record-row"') == 2, "each record reads as one row"
  assert "Rope climb plan" in page and "A loose bolt" in page
