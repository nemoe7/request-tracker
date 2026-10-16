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

from pwedepa.auth import credentials, enrollment, sessions, users
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
  assert b"PwedePa" in landing.data
  assert b"Sign in" in landing.data
  assert b"pwede pa" in landing.data
  assert b'id="tagline-marks"' in landing.data

  script = client.get("/static/app.js")
  assert b"pwede na!" in script.data

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


def test_enrollment_flow_creates_a_session(client, db, user, monkeypatch):
  issued = enrollment.issue_enrollment_token(db, user.id, at=AT)

  start = client.post("/enroll/options", json={"token": issued.token})
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
    },
  )
  assert finish.status_code == 200
  assert "HttpOnly" in finish.headers["Set-Cookie"]
  assert client.get("/home").status_code == 200

  replay = client.post("/enroll/options", json={"token": issued.token})
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

  sprite = client.get("/static/icons/lucide.svg")
  assert sprite.status_code == 200
  assert b'id="contrast"' in sprite.data
  assert b'id="log-out"' in sprite.data
