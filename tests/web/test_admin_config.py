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


def test_an_admin_imports_the_mounted_file(app, admin, monkeypatch, tmp_path):
  mounted = tmp_path / "mounted.yaml"
  mounted.write_bytes(NEW_CONFIG)
  monkeypatch.setenv("PWEDEPA_DOMAINS_CONFIG", str(mounted))

  done = admin.post("/admin/config/import")
  assert done.status_code == 302

  db_path = app.config["DATABASE"]
  assert domains_data.imported_path(db_path).is_file()
  assert [domain.name for domain in domains_data.load(db_path)] == ["Garden"]
  page = admin.get("/admin/config")
  assert b"Garden" in page.data


def test_an_admin_imports_a_chosen_file(app, admin):
  done = admin.post(
    "/admin/config/import",
    data={"config": (io.BytesIO(NEW_CONFIG), "domains.yaml")},
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
    data={"config": (io.BytesIO(b"domains: []\n"), "domains.yaml")},
    content_type="multipart/form-data",
    follow_redirects=True,
  )
  assert not domains_data.imported_path(db_path).exists()
  assert [domain.name for domain in domains_data.load(db_path)] == before


def test_a_missing_choice_asks_for_a_file(admin, monkeypatch):
  monkeypatch.delenv("PWEDEPA_DOMAINS_CONFIG", raising=False)
  done = admin.post("/admin/config/import", follow_redirects=True)
  assert done.status_code == 200
  assert b'type="file"' in done.data
  assert not domains_data.imported_path(admin.application.config["DATABASE"]).exists()
