import json
from datetime import UTC, datetime

import pytest
from webauthn.authentication.verify_authentication_response import (
  VerifiedAuthentication,
)
from webauthn.helpers.structs import (
  AttestationFormat,
  CredentialDeviceType,
  PublicKeyCredentialType,
)
from webauthn.registration.verify_registration_response import VerifiedRegistration

from pwedepa.auth import Role, credentials, enrollment, grants, sessions, users
from pwedepa.data import db as data_db
from pwedepa.web import create_app

AT = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)
CREDENTIAL = {"id": "Y3JlZC0x"}


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
def client(app):
  return app.test_client()


@pytest.fixture
def db(app):
  connection = data_db.connect(app.config["DATABASE"])
  yield connection
  connection.close()


@pytest.fixture
def user(db):
  return users.create_user(db, "Ada", "Ada Lovelace", at=AT)


def _verified_registration():
  return VerifiedRegistration(
    credential_id=b"cred-1",
    credential_public_key=b"public-key",
    sign_count=1,
    aaguid="00000000-0000-0000-0000-000000000000",
    fmt=AttestationFormat.NONE,
    credential_type=PublicKeyCredentialType.PUBLIC_KEY,
    user_verified=True,
    attestation_object=b"attestation",
    credential_device_type=CredentialDeviceType.SINGLE_DEVICE,
    credential_backed_up=False,
  )


def _mock_registration(monkeypatch):
  monkeypatch.setattr(
    credentials,
    "verify_registration_response",
    lambda **kwargs: _verified_registration(),
  )


def _mock_authentication(monkeypatch, sign_count=2):
  monkeypatch.setattr(
    credentials,
    "verify_authentication_response",
    lambda **kwargs: VerifiedAuthentication(
      credential_id=b"cred-1",
      new_sign_count=sign_count,
      credential_device_type=CredentialDeviceType.SINGLE_DEVICE,
      credential_backed_up=False,
      user_verified=True,
    ),
  )


def _register_passkey(db, user, monkeypatch):
  _mock_registration(monkeypatch)
  config = _config(db)
  start = credentials.start_registration(db, user, config, at=AT)
  return credentials.finish_registration(
    db, user, start.flow_id, CREDENTIAL, config, at=AT
  )


def _config(db):
  from pwedepa.auth import WebAuthnConfig

  return WebAuthnConfig(
    rp_id="example.com", rp_name="PwedePa", origin="https://example.com"
  )


def _login(client, monkeypatch):
  _mock_authentication(monkeypatch)
  start = client.post("/login/options").get_json()
  return client.post(
    "/login/finish",
    json={"flow_id": start["flow_id"], "credential": CREDENTIAL},
  )


def test_landing_renders_and_home_requires_login(client):
  landing = client.get("/")
  assert landing.status_code == 200
  assert b'href="/login"' in landing.data
  assert b'id="tagline"' in landing.data
  assert b'id="tagline-marks"' in landing.data

  script = client.get("/static/app.js")
  assert b'"#tagline"' in script.data
  assert b'"#tagline-marks"' in script.data

  home = client.get("/home")
  assert home.status_code == 302
  assert "/login" in home.headers["Location"]


def test_login_flow_sets_a_hardened_cookie(client, db, user, monkeypatch):
  _register_passkey(db, user, monkeypatch)

  response = _login(client, monkeypatch)
  assert response.status_code == 200
  cookie = response.headers["Set-Cookie"]
  assert "HttpOnly" in cookie
  assert "Secure" in cookie
  assert "SameSite=Lax" in cookie

  home = client.get("/home")
  assert home.status_code == 200
  assert b"Ada Lovelace" in home.data


def test_login_finish_rejects_an_unknown_flow(client, db, user, monkeypatch):
  _register_passkey(db, user, monkeypatch)
  response = client.post(
    "/login/finish", json={"flow_id": "missing", "credential": CREDENTIAL}
  )
  assert response.status_code == 400
  assert "error" in response.get_json()


def test_the_enroll_page_asks_for_a_name(client):
  body = client.get("/enroll").data
  assert b'id="username"' in body
  assert b'name="display_name"' in body


def test_enrollment_flow_creates_a_session(client, db, monkeypatch):
  issued = enrollment.issue_enrollment_token(db, role=Role.REQUESTER, at=AT)

  start = client.post(
    "/enroll/options", json={"token": issued.token, "username": "mara"}
  )
  assert start.status_code == 200
  options = start.get_json()["options"]
  assert options["rp"]["id"] == "example.com"

  _mock_registration(monkeypatch)
  finish = client.post(
    "/enroll/finish",
    json={
      "token": issued.token,
      "flow_id": start.get_json()["flow_id"],
      "credential": CREDENTIAL,
      "username": "mara",
      "display_name": "Mara Reyes",
    },
  )
  assert finish.status_code == 200
  assert "HttpOnly" in finish.headers["Set-Cookie"]
  assert client.get("/home").status_code == 200
  created = users.get_user_by_username(db, "mara")
  assert created is not None
  assert created.display_name == "Mara Reyes"
  assert Role.REQUESTER in grants.list_roles(db, created.id)

  replay = client.post(
    "/enroll/options", json={"token": issued.token, "username": "mara"}
  )
  assert replay.status_code == 400


def test_logout_revokes_the_session(client, db, user, monkeypatch):
  _register_passkey(db, user, monkeypatch)
  assert _login(client, monkeypatch).status_code == 200
  assert client.get("/home").status_code == 200

  assert client.post("/logout").status_code == 200
  assert client.get("/home").status_code == 302


def test_signed_in_user_can_add_a_passkey(client, db, user, monkeypatch):
  issued = sessions.create_session(db, user.id, at=AT)
  client.set_cookie("pwedepa_session", issued.token)

  _mock_registration(monkeypatch)
  start = client.post("/auth/register/options")
  assert start.status_code == 200
  finish = client.post(
    "/auth/register/finish",
    json={"flow_id": start.get_json()["flow_id"], "credential": CREDENTIAL},
  )
  assert finish.status_code == 200
  assert credentials.list_passkeys(db, user.id)

  home = client.get("/home")
  assert b"1 passkey" in home.data


def test_home_survives_concurrent_requests(app, db, user):
  import threading

  issued = sessions.create_session(db, user.id, at=AT)
  results = []

  def hit():
    thread_client = app.test_client()
    thread_client.set_cookie("pwedepa_session", issued.token)
    results.append(thread_client.get("/home").status_code)

  threads = [threading.Thread(target=hit) for _ in range(4)]
  for thread in threads:
    thread.start()
  for thread in threads:
    thread.join()
  assert results == [200, 200, 200, 200]


def test_pwa_assets_are_served(client):
  manifest = client.get("/static/manifest.webmanifest")
  assert manifest.status_code == 200
  data = json.loads(manifest.data)
  assert data["name"] == "PwedePa"
  purposes = {icon["purpose"] for icon in data["icons"]}
  assert "maskable" in purposes

  worker = client.get("/sw.js")
  assert worker.status_code == 200
  assert worker.headers["Service-Worker-Allowed"] == "/"

  icon = client.get("/static/icons/icon-maskable-512.png")
  assert icon.status_code == 200
  assert icon.data[:4] == b"\x89PNG"


def test_the_manifest_points_inside_its_own_site(client):
  """A demo under a path prefix must not send its start, scope, and icons to the root."""
  data = json.loads(client.get("/static/manifest.webmanifest").data)
  assert not data["start_url"].startswith("/")
  assert not data["scope"].startswith("/")
  assert all(not icon["src"].startswith("/") for icon in data["icons"])


def test_the_pwa_sprite_answers(client):
  sprite = client.get("/static/icons/lucide.svg")
  assert sprite.status_code == 200
  assert b'id="contrast"' in sprite.data
  assert b'id="log-out"' in sprite.data


def test_the_passkey_id_follows_the_public_origin(monkeypatch, tmp_path):
  monkeypatch.setenv("PWEDEPA_ORIGIN", "https://pwedepa.tail1234.ts.net")
  monkeypatch.delenv("PWEDEPA_RP_ID", raising=False)
  app = create_app({"DATABASE": str(tmp_path / "origin.db")})
  assert app.config["WEBAUTHN_RP_ID"] == "pwedepa.tail1234.ts.net"


def test_the_passkey_id_keeps_its_own_value(monkeypatch, tmp_path):
  monkeypatch.setenv("PWEDEPA_ORIGIN", "https://pwedepa.tail1234.ts.net")
  monkeypatch.setenv("PWEDEPA_RP_ID", "example.com")
  app = create_app({"DATABASE": str(tmp_path / "explicit.db")})
  assert app.config["WEBAUTHN_RP_ID"] == "example.com"


def test_a_public_host_refuses_the_sample_secret():
  """A deploy that forgets its secret must not start on the public value."""
  from pwedepa.web import check_secret

  with pytest.raises(RuntimeError, match="PWEDEPA_SECRET_KEY"):
    check_secret("pwedepa-dev-secret", "https://pwedepa.example.ts.net")


def test_a_real_secret_or_a_local_run_passes_the_check():
  from pwedepa.web import check_secret

  check_secret("a-real-secret", "https://pwedepa.example.ts.net")
  check_secret("pwedepa-dev-secret", "http://localhost:5000")


def test_the_container_entry_serves_through_uvicorn(monkeypatch, tmp_path):
  """The image must not start on the Flask development server."""
  from pwedepa.web import __main__ as entry

  served = {}
  monkeypatch.setattr(
    entry.uvicorn, "run", lambda application, **options: served.update(options)
  )
  monkeypatch.setenv("PWEDEPA_HOST", "0.0.0.0")
  monkeypatch.setenv("PWEDEPA_PORT", "5055")
  monkeypatch.setenv("PWEDEPA_DB", str(tmp_path / "entry.db"))

  entry.main()

  assert served["host"] == "0.0.0.0"
  assert served["port"] == 5055


def test_the_health_route_answers_from_the_database(app):
  """A deploy waits on this route, so it must prove the database opens."""
  response = app.test_client().get("/health")
  assert response.status_code == 200
  assert response.data.strip() == b"ok"


def test_the_font_waits_for_no_paint(app):
  """A refresh must not strand the page on the fallback face."""
  with app.test_client() as client:
    sheet = client.get("/static/tokens.css").get_data(as_text=True)
  assert "font-display: swap" in sheet
  assert "font-display: optional" not in sheet


def test_a_start_reads_an_empty_config_as_no_domains_yet(tmp_path, monkeypatch):
  from pwedepa.data import domains as domains_data

  path = tmp_path / "config.yml"
  path.write_text("# the admin adds Domains in the app\n", encoding="utf-8")
  monkeypatch.setattr(domains_data, "CONFIG", path)

  app = create_app({"DATABASE": str(tmp_path / "test.db")})
  assert app.config["DATABASE"].endswith("test.db")
