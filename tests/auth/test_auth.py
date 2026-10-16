import hashlib
import json
from datetime import UTC, datetime, timedelta

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

from pwedepa.auth import (
  AuthenticationFailed,
  AuthError,
  InvalidToken,
  Role,
  WebAuthnConfig,
  credentials,
  enrollment,
  grants,
  sessions,
  users,
)
from pwedepa.auth.audit import list_audit_events
from pwedepa.auth.cli import main as cli_main
from pwedepa.core import Effect, Grant
from pwedepa.data import db as data_db

AT = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)
LATER = AT + timedelta(hours=1)
CONFIG = WebAuthnConfig(
  rp_id="example.com",
  rp_name="PwedePa",
  origin="https://example.com",
)


@pytest.fixture
def db(tmp_path):
  connection = data_db.connect(tmp_path / "test.db")
  yield connection
  connection.close()


@pytest.fixture
def user(db):
  return users.create_user(db, "ada", "Ada Lovelace", at=AT)


def test_user_lifecycle_and_actor_block(db, user):
  assert users.get_user_by_username(db, "ADA") == user
  assert users.list_users(db) == [user]
  audit = list_audit_events(db, object_type="user", object_id=user.id)
  assert [event.event_type for event in audit] == ["user.created"]
  with pytest.raises(AuthError):
    users.create_user(db, "Ada", "Another Ada", at=AT)

  archived = users.archive_user(db, user.id, at=LATER)
  assert archived.status is users.UserStatus.ARCHIVED
  assert archived.archived_at == LATER
  assert users.list_users(db) == []
  assert users.list_users(db, include_archived=True) == [archived]
  with pytest.raises(AuthenticationFailed):
    grants.actor_for_user(db, user.id)

  active = users.reactivate_user(db, user.id, at=LATER)
  assert active.status is users.UserStatus.ACTIVE
  assert active.archived_at is None


def test_roles_and_direct_grants_make_an_actor(db, user):
  assert Grant("request.create") in grants.ROLE_GRANTS[Role.REQUESTER]
  assert Grant("issue.view") in grants.ROLE_GRANTS[Role.ASSIGNEE]
  assert grants.ROLE_GRANTS[Role.ADMIN] == (Grant("*"),)

  grants.assign_role(db, user.id, Role.REQUESTER, at=AT)
  audit = list_audit_events(db, object_type="user", object_id=user.id)
  assert audit[-1].event_type == "role.assigned"
  grants.grant_permission(db, user.id, Grant("issue.12.view"), at=AT)
  grants.grant_permission(db, user.id, Grant("issue.comment", Effect.DENY), at=AT)
  actor = grants.actor_for_user(db, user.id)
  assert not actor.is_admin
  assert actor.grants.count(Grant("request.create")) == 1
  assert Grant("issue.12.view") in actor.grants
  assert Grant("issue.comment", Effect.DENY) in actor.grants

  grants.revoke_permission(db, user.id, "issue.12.view", Effect.ALLOW, at=LATER)
  grants.revoke_role(db, user.id, Role.REQUESTER, at=LATER)
  actor = grants.actor_for_user(db, user.id)
  assert Grant("issue.12.view") not in actor.grants
  assert Grant("request.create") not in actor.grants

  grants.assign_role(db, user.id, Role.ADMIN, at=LATER)
  assert grants.actor_for_user(db, user.id).is_admin


def test_enrollment_token_is_hashed_single_use_and_expiring(db, user):
  issued = enrollment.issue_enrollment_token(db, user.id, at=AT)
  row = db.exec_driver_sql("SELECT token_hash FROM enrollment_tokens").fetchone()
  assert row[0] != issued.token
  assert row[0] == hashlib.sha256(issued.token.encode()).hexdigest()
  assert (
    enrollment.validate_enrollment_token(db, issued.token, at=AT).user_id == user.id
  )

  consumed = enrollment.consume_enrollment_token(db, issued.token, at=LATER)
  assert consumed.used_at == LATER
  with pytest.raises(InvalidToken):
    enrollment.consume_enrollment_token(db, issued.token, at=LATER)

  expired = enrollment.issue_enrollment_token(
    db, user.id, at=AT, ttl=timedelta(minutes=5)
  )
  with pytest.raises(InvalidToken):
    enrollment.validate_enrollment_token(
      db, expired.token, at=AT + timedelta(minutes=5)
    )


def test_a_session_stamps_its_use_once_an_hour(db, user):
  """A page load must not take a write for a stamp that nothing reads."""
  issued = sessions.create_session(db, user.id, at=AT)
  early = sessions.resolve_session(db, issued.token, at=AT + timedelta(minutes=5))
  assert early.last_used_at == AT, "a five minute old stamp holds"
  old = sessions.resolve_session(db, issued.token, at=AT + timedelta(hours=2))
  assert old.last_used_at == AT + timedelta(hours=2), "an old stamp refreshes"


def test_session_lifecycle_and_rotation_reuse_detection(db, user):
  issued = sessions.create_session(db, user.id, at=AT)
  row = db.exec_driver_sql("SELECT token_hash FROM sessions").fetchone()
  assert row[0] != issued.token
  assert row[0] == hashlib.sha256(issued.token.encode()).hexdigest()
  resolved = sessions.resolve_session(db, issued.token, at=LATER)
  assert resolved.user_id == user.id
  assert resolved.last_used_at == LATER

  rotated = sessions.rotate_session(db, issued.token, at=LATER)
  assert rotated.token != issued.token
  assert sessions.resolve_session(db, issued.token, at=LATER) is None
  assert sessions.resolve_session(db, rotated.token, at=LATER).id == rotated.session.id
  with pytest.raises(AuthenticationFailed):
    sessions.rotate_session(db, issued.token, at=LATER)
  assert sessions.resolve_session(db, rotated.token, at=LATER) is None


def test_session_expiry_revocation_and_archived_users(db, user):
  issued = sessions.create_session(db, user.id, at=AT, ttl=timedelta(minutes=10))
  assert (
    sessions.resolve_session(db, issued.token, at=AT + timedelta(minutes=10)) is None
  )
  assert sessions.revoke_session(db, issued.token, at=AT)
  assert sessions.resolve_session(db, issued.token, at=AT) is None

  second = sessions.create_session(db, user.id, at=AT)
  third = sessions.create_session(db, user.id, at=AT)
  assert sessions.revoke_user_sessions(db, user.id, at=LATER) == 2
  assert sessions.resolve_session(db, second.token, at=LATER) is None
  assert sessions.resolve_session(db, third.token, at=LATER) is None

  users.archive_user(db, user.id, at=LATER)
  with pytest.raises(AuthenticationFailed):
    sessions.create_session(db, user.id, at=LATER)


def _verified_registration(sign_count=1):
  return VerifiedRegistration(
    credential_id=b"cred-1",
    credential_public_key=b"public-key",
    sign_count=sign_count,
    aaguid="00000000-0000-0000-0000-000000000000",
    fmt=AttestationFormat.NONE,
    credential_type=PublicKeyCredentialType.PUBLIC_KEY,
    user_verified=True,
    attestation_object=b"attestation",
    credential_device_type=CredentialDeviceType.SINGLE_DEVICE,
    credential_backed_up=False,
  )


def _verified_authentication(sign_count):
  return VerifiedAuthentication(
    credential_id=b"cred-1",
    new_sign_count=sign_count,
    credential_device_type=CredentialDeviceType.SINGLE_DEVICE,
    credential_backed_up=False,
    user_verified=True,
  )


def _register(db, user, monkeypatch):
  monkeypatch.setattr(
    credentials,
    "verify_registration_response",
    lambda **kwargs: _verified_registration(),
  )
  start = credentials.start_registration(db, user, CONFIG, at=AT)
  assert json.loads(start.options_json)["challenge"]
  return credentials.finish_registration(
    db,
    user,
    start.flow_id,
    {"id": "Y3JlZC0x"},
    CONFIG,
    at=AT,
  )


def test_passkey_registration_and_authentication(db, user, monkeypatch):
  passkey = _register(db, user, monkeypatch)
  assert passkey.user_id == user.id
  assert passkey.credential_id == b"cred-1"
  assert passkey.public_key == b"public-key"
  assert credentials.list_passkeys(db, user.id) == [passkey]
  audit = list_audit_events(db, object_type="passkey", object_id=passkey.id)
  assert [event.event_type for event in audit] == ["passkey.registered"]

  monkeypatch.setattr(
    credentials,
    "verify_authentication_response",
    lambda **kwargs: _verified_authentication(2),
  )
  start = credentials.start_authentication(db, CONFIG, at=LATER, user=user)
  authenticated, owner = credentials.finish_authentication(
    db, start.flow_id, {"id": "Y3JlZC0x"}, CONFIG, at=LATER
  )
  assert owner == user
  assert authenticated.sign_count == 2
  assert authenticated.last_used_at == LATER

  second = credentials.start_authentication(db, CONFIG, at=LATER, user=user)
  with pytest.raises(AuthenticationFailed):
    credentials.finish_authentication(
      db, second.flow_id, {"id": "Y3JlZC0x"}, CONFIG, at=LATER
    )
  assert credentials.list_passkeys(db, user.id)[0].sign_count == 2


def test_passkey_challenges_are_single_use_and_revocation_blocks_login(
  db, user, monkeypatch
):
  monkeypatch.setattr(
    credentials,
    "verify_registration_response",
    lambda **kwargs: _verified_registration(),
  )
  start = credentials.start_registration(db, user, CONFIG, at=AT)
  passkey = credentials.finish_registration(
    db, user, start.flow_id, {"id": "Y3JlZC0x"}, CONFIG, at=AT
  )
  with pytest.raises(AuthenticationFailed):
    credentials.finish_registration(
      db, user, start.flow_id, {"id": "Y3JlZC0x"}, CONFIG, at=AT
    )

  credentials.revoke_passkey(db, passkey.id, at=LATER)
  assert credentials.list_passkeys(db, user.id) == []
  assert (
    credentials.list_passkeys(db, user.id, include_revoked=True)[0].revoked_at == LATER
  )
  with pytest.raises(AuthenticationFailed):
    credentials.start_authentication(db, CONFIG, at=LATER, user=user)


def test_enrollment_registration_consumes_the_token(db, user, monkeypatch):
  issued = enrollment.issue_enrollment_token(db, user.id, at=AT)
  owner, start = credentials.start_enrollment_registration(
    db, issued.token, CONFIG, at=AT
  )
  assert owner == user
  monkeypatch.setattr(
    credentials,
    "verify_registration_response",
    lambda **kwargs: _verified_registration(),
  )
  passkey = credentials.finish_enrollment_registration(
    db,
    issued.token,
    start.flow_id,
    {"id": "Y3JlZC0x"},
    CONFIG,
    at=AT,
  )
  assert passkey.user_id == user.id
  with pytest.raises(InvalidToken):
    enrollment.validate_enrollment_token(db, issued.token, at=AT)


def test_admin_cli_creates_an_admin_and_prints_a_token_once(db, tmp_path, capsys):
  database = tmp_path / "cli.db"
  code = cli_main(
    [
      "create-admin",
      "--database",
      str(database),
      "--username",
      "root",
      "--display-name",
      "Root User",
    ]
  )
  output = capsys.readouterr().out
  assert code == 0
  assert "Enrollment token:" in output

  connection = data_db.connect(database)
  root = users.get_user_by_username(connection, "root")
  assert grants.actor_for_user(connection, root.id).is_admin
  connection.close()
