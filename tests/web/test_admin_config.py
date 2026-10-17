"""The domain config page imports a YAML file from the mount or a picked file."""

import io
from datetime import UTC, datetime

import pytest

from pwedepa.auth import Role, assign_role, sessions, users
from pwedepa.data import db as data_db
from pwedepa.data import domains as domains_data
from pwedepa.web import SESSION_COOKIE, create_app

AT = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)
NEW_CONFIG = b"domains:\n  - name: Garden\n    description: Plots and tools.\n"


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
  return client


@pytest.fixture
def admin(app, db):
  return _client(app, db, "admin", roles=(Role.ADMIN,))


@pytest.fixture
def requester(app, db):
  return _client(app, db, "Mara", roles=(Role.REQUESTER,))


def test_an_admin_opens_the_domain_config_page(admin):
  page = admin.get("/admin/config")
  assert page.status_code == 200
  for name in domains_data.starter_domains():
    assert name.encode() in page.data
  assert b'type="file"' in page.data, "the picker is offered"
  assert b'action="/admin/config/import"' in page.data


def test_a_client_cannot_open_the_domain_config_page(requester):
  assert requester.get("/admin/config").status_code == 403


def test_an_import_replaces_the_copy_before_it(app, admin):
  db_path = app.config["DATABASE"]
  first = b"domains:\n  - name: Garden\n"
  second = b"domains:\n  - name: Gym\n"
  for raw in (first, second):
    done = admin.post(
      "/admin/config/import",
      data={"config": (io.BytesIO(raw), "config.yml")},
      content_type="multipart/form-data",
    )
    assert done.status_code == 302

  assert domains_data.imported_path(db_path).is_file()
  assert [domain.name for domain in domains_data.load(db_path)] == ["Gym"]
  page = admin.get("/admin/config")
  assert b"Gym" in page.data


def test_an_admin_imports_a_chosen_file(app, admin):
  done = admin.post(
    "/admin/config/import",
    data={"config": (io.BytesIO(NEW_CONFIG), "config.yml")},
    content_type="multipart/form-data",
  )
  assert done.status_code == 302

  db_path = app.config["DATABASE"]
  found = domains_data.load(db_path)
  assert [domain.name for domain in found] == ["Garden"]
  assert found[0].description == "Plots and tools."


def test_a_bad_file_leaves_the_config_alone(app, admin):
  db_path = app.config["DATABASE"]
  before = [domain.name for domain in domains_data.load(db_path)]
  admin.post(
    "/admin/config/import",
    data={"config": (io.BytesIO(b"domains: []\n"), "config.yml")},
    content_type="multipart/form-data",
    follow_redirects=True,
  )
  assert not domains_data.imported_path(db_path).exists()
  assert [domain.name for domain in domains_data.load(db_path)] == before


def test_a_missing_choice_asks_for_a_file(admin):
  done = admin.post("/admin/config/import", follow_redirects=True)
  assert done.status_code == 200
  assert b'type="file"' in done.data
  assert not domains_data.imported_path(admin.application.config["DATABASE"]).exists()


def test_an_admin_adds_a_domain(app, admin):
  done = admin.post(
    "/admin/config/add", data={"name": "Garden", "description": "Plots and tools."}
  )
  assert done.status_code == 302

  db_path = app.config["DATABASE"]
  assert [domain.name for domain in domains_data.load(db_path)] == ["Garden"]
  page = admin.get("/admin/config")
  assert b"Garden" in page.data


def test_a_client_cannot_add_a_domain(requester):
  done = requester.post("/admin/config/add", data={"name": "Garden"})
  assert done.status_code == 403


def test_an_admin_renames_a_domain_and_the_old_url_redirects(app, admin):
  admin.post("/admin/config/add", data={"name": "Gym"})
  db_path = app.config["DATABASE"]
  assert domains_data.load(db_path)[0].slug == "gym"

  done = admin.post(
    "/admin/config/rename",
    data={"slug": "gym", "name": "Fitness", "new_slug": "fitness"},
  )
  assert done.status_code == 302
  assert [domain.name for domain in domains_data.load(db_path)] == ["Fitness"]

  old = admin.get("/gym")
  assert old.status_code == 302
  assert old.headers["Location"].endswith("/fitness")
  assert admin.get("/fitness").status_code == 200


def test_a_rename_keeps_the_domain_records(app, admin):
  from pwedepa.core import Request, RequestStatus, Visibility
  from pwedepa.data import db as data_db
  from pwedepa.data import requests as requests_data

  admin.post("/admin/config/add", data={"name": "Gym"})
  db_path = app.config["DATABASE"]
  connection = data_db.connect(db_path)
  try:
    requests_data.save(
      connection,
      Request(
        id=0,
        title="A leak",
        description="Under the sink.",
        status=RequestStatus.OPEN,
        visibility=Visibility.PUBLIC,
        domains=("Gym",),
        created_at=AT,
        updated_at=AT,
      ),
      commit=True,
    )
  finally:
    connection.close()

  admin.post(
    "/admin/config/rename", data={"slug": "gym", "name": "Fitness", "new_slug": "gym"}
  )

  connection = data_db.connect(db_path)
  try:
    saved = requests_data.list_requests(connection)
  finally:
    connection.close()
  assert [record.domains for record in saved] == [("Fitness",)]


def test_a_remove_needs_the_tick_when_the_domain_holds_records(app, admin):
  from pwedepa.core import Request, RequestStatus, Visibility
  from pwedepa.data import db as data_db
  from pwedepa.data import requests as requests_data

  admin.post("/admin/config/add", data={"name": "Gym"})
  db_path = app.config["DATABASE"]
  connection = data_db.connect(db_path)
  try:
    requests_data.save(
      connection,
      Request(
        id=0,
        title="A leak",
        description="Under the sink.",
        status=RequestStatus.OPEN,
        visibility=Visibility.PUBLIC,
        domains=("Gym",),
        created_at=AT,
        updated_at=AT,
      ),
      commit=True,
    )
  finally:
    connection.close()

  held = admin.post("/admin/config/remove", data={"slug": "gym"}, follow_redirects=True)
  assert held.status_code == 200
  assert b"Gym has 1 Request" in held.data
  assert [domain.slug for domain in domains_data.load(db_path)] == ["gym"]

  gone = admin.post(
    "/admin/config/remove",
    data={"slug": "gym", "confirm": "yes"},
    follow_redirects=True,
  )
  assert gone.status_code == 200
  assert domains_data.load(db_path)
  connection = data_db.connect(db_path)
  try:
    assert requests_data.list_requests(connection) == []
  finally:
    connection.close()


def test_an_old_domain_path_lands_on_the_same_page(app, admin):
  from pwedepa.data import domain_store

  admin.post("/admin/config/add", data={"name": "Gym"})
  db_path = app.config["DATABASE"]
  domain_store.rename(db_path, "gym", name="Fitness", new_slug="fitness")

  detail = admin.get("/gym/requests/4")
  assert detail.status_code == 302
  assert detail.headers["Location"].endswith("/fitness/requests/4")

  other = admin.get("/gym/announcements/9")
  assert other.status_code == 302
  assert other.headers["Location"].endswith("/fitness")

  edit = admin.get("/gym/announcements/9/edit")
  assert edit.status_code == 302
  assert edit.headers["Location"].endswith("/fitness/announcements/9/edit")

  fresh = admin.get("/gym/announcements/new")
  assert fresh.status_code == 302
  assert fresh.headers["Location"].endswith("/fitness/announcements/new")
