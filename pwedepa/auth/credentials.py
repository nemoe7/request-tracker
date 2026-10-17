"""Passkey registration and authentication through the WebAuthn library."""

import json
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import webauthn
from sqlalchemy.engine import Connection, Row
from sqlalchemy.exc import IntegrityError
from webauthn import (
  generate_authentication_options,
  generate_registration_options,
  options_to_json,
  verify_authentication_response,
  verify_registration_response,
)
from webauthn.helpers.structs import (
  AuthenticatorSelectionCriteria,
  PublicKeyCredentialDescriptor,
  ResidentKeyRequirement,
  UserVerificationRequirement,
)

from pwedepa.data._rows import pack_time, unpack_time

from .audit import record_audit
from .enrollment import consume_enrollment_token, validate_enrollment_token
from .errors import AuthenticationFailed, AuthError
from .grants import assign_role
from .users import User, UserStatus, create_user, get_user, get_user_by_username

CHALLENGE_TTL = timedelta(minutes=5)


@dataclass(frozen=True)
class WebAuthnConfig:
  rp_id: str
  rp_name: str
  origin: str
  challenge_ttl: timedelta = CHALLENGE_TTL
  timeout_ms: int = 60_000


@dataclass(frozen=True)
class Passkey:
  id: int
  user_id: int
  credential_id: bytes
  public_key: bytes
  sign_count: int
  created_at: datetime | None
  last_used_at: datetime | None
  revoked_at: datetime | None


@dataclass(frozen=True)
class CeremonyStart:
  flow_id: str
  options_json: str


def start_registration(
  db: Connection,
  user: User,
  config: WebAuthnConfig,
  *,
  at: datetime,
) -> CeremonyStart:
  _require_active(user)
  existing = [
    PublicKeyCredentialDescriptor(id=passkey.credential_id)
    for passkey in list_passkeys(db, user.id)
  ]
  options = generate_registration_options(
    rp_id=config.rp_id,
    rp_name=config.rp_name,
    user_id=str(user.id).encode("utf-8"),
    user_name=user.username,
    user_display_name=user.display_name,
    challenge=_new_challenge(),
    timeout=config.timeout_ms,
    authenticator_selection=AuthenticatorSelectionCriteria(
      resident_key=ResidentKeyRequirement.REQUIRED,
      require_resident_key=True,
      user_verification=UserVerificationRequirement.REQUIRED,
    ),
    exclude_credentials=existing,
  )
  flow_id = _store_challenge(db, user.id, "registration", options.challenge, config, at)
  return CeremonyStart(flow_id, options_to_json(options))


def finish_registration(
  db: Connection,
  user: User,
  flow_id: str,
  credential: Any,
  config: WebAuthnConfig,
  *,
  at: datetime,
) -> Passkey:
  _require_active(user)
  return _finish_registration(db, user, flow_id, credential, config, at=at)


def start_enrollment_registration(
  db: Connection,
  token: str,
  username: str,
  config: WebAuthnConfig,
  *,
  at: datetime,
) -> CeremonyStart:
  validate_enrollment_token(db, token, at=at)
  name = username.strip()
  if not name:
    raise AuthError("a sign-up needs a username")
  if get_user_by_username(db, name) is not None:
    raise AuthError("the username is already in use")
  options = generate_registration_options(
    rp_id=config.rp_id,
    rp_name=config.rp_name,
    user_id=secrets.token_bytes(32),
    user_name=name,
    user_display_name=name,
    challenge=_new_challenge(),
    timeout=config.timeout_ms,
    authenticator_selection=AuthenticatorSelectionCriteria(
      resident_key=ResidentKeyRequirement.REQUIRED,
      require_resident_key=True,
      user_verification=UserVerificationRequirement.REQUIRED,
    ),
  )
  flow_id = _store_challenge(db, None, "registration", options.challenge, config, at)
  return CeremonyStart(flow_id, options_to_json(options))


def finish_enrollment_registration(
  db: Connection,
  token: str,
  flow_id: str,
  credential: Any,
  username: str,
  display_name: str,
  config: WebAuthnConfig,
  *,
  at: datetime,
) -> Passkey:
  """The account exists only after the passkey verifies."""
  validate_enrollment_token(db, token, at=at)
  challenge, _ = _claim_challenge(db, flow_id, "registration", at=at)
  try:
    verified = verify_registration_response(
      credential=credential,
      expected_challenge=challenge,
      expected_rp_id=config.rp_id,
      expected_origin=config.origin,
      require_user_verification=True,
    )
  except Exception as exc:
    raise AuthenticationFailed("passkey registration failed") from exc
  # A taken name must not burn the token, so look it up before the claim.
  if get_user_by_username(db, username.strip()) is not None:
    raise AuthError("the username is already in use")
  record = consume_enrollment_token(db, token, at=at)
  user = create_user(db, username, display_name, at=at)
  assign_role(db, user.id, record.role, at=at)
  return _store_passkey(db, user, verified, at=at)


def start_authentication(
  db: Connection,
  config: WebAuthnConfig,
  *,
  at: datetime,
  user: User | None = None,
) -> CeremonyStart:
  allowed = None
  user_id = None
  if user is not None:
    _require_active(user)
    passkeys = list_passkeys(db, user.id)
    if not passkeys:
      raise AuthenticationFailed("the user has no active passkeys")
    allowed = [
      PublicKeyCredentialDescriptor(id=passkey.credential_id) for passkey in passkeys
    ]
    user_id = user.id
  options = generate_authentication_options(
    rp_id=config.rp_id,
    challenge=_new_challenge(),
    timeout=config.timeout_ms,
    allow_credentials=allowed,
    user_verification=UserVerificationRequirement.REQUIRED,
  )
  flow_id = _store_challenge(
    db, user_id, "authentication", options.challenge, config, at
  )
  return CeremonyStart(flow_id, options_to_json(options))


def finish_authentication(
  db: Connection,
  flow_id: str,
  credential: Any,
  config: WebAuthnConfig,
  *,
  at: datetime,
) -> tuple[Passkey, User]:
  challenge, challenge_user_id = _claim_challenge(db, flow_id, "authentication", at=at)
  credential_id = _credential_id(credential)
  passkey = _get_by_credential_id(db, credential_id)
  if passkey is None or passkey.revoked_at is not None:
    raise AuthenticationFailed("the passkey is unknown or revoked")
  if challenge_user_id is not None and challenge_user_id != passkey.user_id:
    raise AuthenticationFailed("the passkey does not match the login attempt")
  user = get_user(db, passkey.user_id)
  if user is None or user.status is UserStatus.ARCHIVED:
    raise AuthenticationFailed("archived users cannot authenticate")

  try:
    verified = verify_authentication_response(
      credential=credential,
      expected_challenge=challenge,
      expected_rp_id=config.rp_id,
      expected_origin=config.origin,
      credential_public_key=passkey.public_key,
      credential_current_sign_count=passkey.sign_count,
      require_user_verification=True,
    )
  except Exception as exc:
    raise AuthenticationFailed("passkey authentication failed") from exc
  if verified.credential_id != passkey.credential_id:
    raise AuthenticationFailed("the passkey does not match the assertion")
  if (
    passkey.sign_count
    and verified.new_sign_count
    and verified.new_sign_count <= passkey.sign_count
  ):
    raise AuthenticationFailed("the passkey sign count did not increase")

  db.exec_driver_sql(
    "UPDATE passkeys SET sign_count = ?, last_used_at = ? WHERE id = ?",
    (verified.new_sign_count, pack_time(at), passkey.id),
  )
  record_audit(
    db,
    "authentication.succeeded",
    at=at,
    actor_id=user.id,
    object_type="user",
    object_id=user.id,
    data={"passkey_id": passkey.id},
    commit=False,
  )
  db.commit()
  return _get_passkey(db, passkey.id), user


def list_passkeys(
  db: Connection, user_id: int, *, include_revoked: bool = False
) -> list[Passkey]:
  query = "SELECT * FROM passkeys WHERE user_id = ?"
  if not include_revoked:
    query += " AND revoked_at IS NULL"
  query += " ORDER BY id"
  return [_from_row(row) for row in db.exec_driver_sql(query, (user_id,))]


def revoke_passkey(
  db: Connection,
  passkey_id: int,
  *,
  at: datetime,
  actor_id: int | None = None,
) -> Passkey:
  """Keep the row for audit history."""
  row = db.exec_driver_sql(
    "SELECT * FROM passkeys WHERE id = ?", (passkey_id,)
  ).fetchone()
  if row is None:
    raise AuthError("the passkey does not exist")
  if row._mapping["revoked_at"] is None:
    db.exec_driver_sql(
      "UPDATE passkeys SET revoked_at = ? WHERE id = ?", (pack_time(at), passkey_id)
    )
    record_audit(
      db,
      "passkey.revoked",
      at=at,
      actor_id=actor_id,
      object_type="passkey",
      object_id=passkey_id,
      data={"user_id": row._mapping["user_id"]},
      commit=False,
    )
    db.commit()
  return _get_passkey(db, passkey_id)


def _finish_registration(
  db: Connection,
  user: User,
  flow_id: str,
  credential: Any,
  config: WebAuthnConfig,
  *,
  at: datetime,
) -> Passkey:
  challenge, _ = _claim_challenge(db, flow_id, "registration", at=at, user_id=user.id)
  try:
    verified = verify_registration_response(
      credential=credential,
      expected_challenge=challenge,
      expected_rp_id=config.rp_id,
      expected_origin=config.origin,
      require_user_verification=True,
    )
  except Exception as exc:
    raise AuthenticationFailed("passkey registration failed") from exc

  return _store_passkey(db, user, verified, at=at)


def _store_passkey(
  db: Connection, user: User, verified: Any, *, at: datetime
) -> Passkey:
  try:
    cursor = db.exec_driver_sql(
      "INSERT INTO passkeys "
      "(user_id, credential_id, public_key, sign_count, created_at) "
      "VALUES (?, ?, ?, ?, ?)",
      (
        user.id,
        verified.credential_id,
        verified.credential_public_key,
        verified.sign_count,
        pack_time(at),
      ),
    )
  except IntegrityError as exc:
    db.rollback()
    raise AuthError("the passkey is already registered") from exc
  record_audit(
    db,
    "passkey.registered",
    at=at,
    actor_id=user.id,
    object_type="passkey",
    object_id=cursor.lastrowid,
    data={"user_id": user.id},
    commit=False,
  )
  db.commit()
  return _get_passkey(db, cursor.lastrowid)


def _store_challenge(
  db: Connection,
  user_id: int | None,
  ceremony: str,
  challenge: bytes,
  config: WebAuthnConfig,
  at: datetime,
) -> str:
  flow_id = uuid.uuid4().hex
  db.exec_driver_sql(
    "INSERT INTO webauthn_challenges "
    "(id, user_id, ceremony, challenge, created_at, expires_at) "
    "VALUES (?, ?, ?, ?, ?, ?)",
    (
      flow_id,
      user_id,
      ceremony,
      challenge,
      pack_time(at),
      pack_time(at + config.challenge_ttl),
    ),
  )
  db.commit()
  return flow_id


def _claim_challenge(
  db: Connection,
  flow_id: str,
  ceremony: str,
  *,
  at: datetime,
  user_id: int | None = None,
) -> tuple[bytes, int | None]:
  row = db.exec_driver_sql(
    "SELECT * FROM webauthn_challenges WHERE id = ?", (flow_id,)
  ).fetchone()
  if (
    row is None
    or row._mapping["ceremony"] != ceremony
    or row._mapping["used_at"] is not None
  ):
    raise AuthenticationFailed("the WebAuthn challenge is invalid or already used")
  if user_id is not None and row._mapping["user_id"] != user_id:
    raise AuthenticationFailed("the WebAuthn challenge belongs to another user")
  if (
    row._mapping["expires_at"] is None or unpack_time(row._mapping["expires_at"]) <= at
  ):
    raise AuthenticationFailed("the WebAuthn challenge has expired")
  cursor = db.exec_driver_sql(
    "UPDATE webauthn_challenges SET used_at = ? "
    "WHERE id = ? AND used_at IS NULL AND expires_at > ?",
    (pack_time(at), flow_id, pack_time(at)),
  )
  if cursor.rowcount != 1:
    db.rollback()
    raise AuthenticationFailed("the WebAuthn challenge is invalid or already used")
  db.commit()
  return bytes(row._mapping["challenge"]), row._mapping["user_id"]


def _credential_id(credential: Any) -> bytes:
  if isinstance(credential, str):
    try:
      credential = json.loads(credential)
    except json.JSONDecodeError as exc:
      raise AuthenticationFailed("the WebAuthn credential is malformed") from exc
  if isinstance(credential, dict):
    value = credential.get("id") or credential.get("rawId")
    if isinstance(value, bytes):
      return value
    if isinstance(value, str):
      return webauthn.base64url_to_bytes(value)
  raw_id = getattr(credential, "raw_id", None)
  if isinstance(raw_id, bytes):
    return raw_id
  raise AuthenticationFailed("the WebAuthn credential is malformed")


def _get_by_credential_id(db: Connection, credential_id: bytes) -> Passkey | None:
  row = db.exec_driver_sql(
    "SELECT * FROM passkeys WHERE credential_id = ?", (credential_id,)
  ).fetchone()
  return None if row is None else _from_row(row)


def _get_passkey(db: Connection, passkey_id: int) -> Passkey:
  row = db.exec_driver_sql(
    "SELECT * FROM passkeys WHERE id = ?", (passkey_id,)
  ).fetchone()
  return _from_row(row)


def _require_active(user: User) -> None:
  if user.status is UserStatus.ARCHIVED:
    raise AuthenticationFailed("archived users cannot authenticate")


def _new_challenge() -> bytes:
  return secrets.token_bytes(32)


def _from_row(row: Row) -> Passkey:
  return Passkey(
    id=row._mapping["id"],
    user_id=row._mapping["user_id"],
    credential_id=bytes(row._mapping["credential_id"]),
    public_key=bytes(row._mapping["public_key"]),
    sign_count=row._mapping["sign_count"],
    created_at=unpack_time(row._mapping["created_at"]),
    last_used_at=unpack_time(row._mapping["last_used_at"]),
    revoked_at=unpack_time(row._mapping["revoked_at"]),
  )
