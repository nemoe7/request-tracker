"""Passkey ceremonies, enrollment, and session endpoints."""

import json

from flask import Blueprint, current_app, jsonify, request
from werkzeug.wrappers import Response

from pwedepa.auth import (
  AuthError,
  create_session,
  finish_authentication,
  finish_enrollment_registration,
  finish_registration,
  list_passkeys,
  revoke_passkey,
  revoke_session,
  start_authentication,
  start_enrollment_registration,
  start_registration,
)
from pwedepa.auth.sessions import SESSION_TTL

from .. import SESSION_COOKIE, now
from ._helpers import current_user, db, webauthn_config

bp = Blueprint("auth", __name__)


@bp.errorhandler(AuthError)
def handle_auth_error(error: AuthError) -> tuple[Response, int]:
  """Turn an auth failure into a plain JSON error."""
  return jsonify(error=str(error)), 400


def _ceremony_payload(start) -> Response:
  return jsonify(flow_id=start.flow_id, options=json.loads(start.options_json))


def _session_response(user_id: int) -> Response:
  issued = create_session(db(), user_id, at=now())
  response = jsonify(ok=True, redirect="/home")
  response.set_cookie(
    SESSION_COOKIE,
    issued.token,
    httponly=True,
    secure=current_app.config["SESSION_COOKIE_SECURE"],
    samesite="Lax",
    max_age=int(SESSION_TTL.total_seconds()),
    path="/",
  )
  return response


def _credential() -> dict:
  payload = request.get_json(force=True)
  return payload["credential"]


@bp.post("/login/options")
def login_options() -> Response:
  """Start a discoverable passkey login ceremony."""
  start = start_authentication(db(), webauthn_config(), at=now())
  return _ceremony_payload(start)


@bp.post("/login/finish")
def login_finish() -> Response:
  """Verify a login assertion and open a session."""
  payload = request.get_json(force=True)
  _, user = finish_authentication(
    db(), payload["flow_id"], _credential(), webauthn_config(), at=now()
  )
  return _session_response(user.id)


@bp.post("/enroll/options")
def enroll_options() -> Response:
  """Start the first-passkey ceremony for an enrollment token."""
  payload = request.get_json(force=True)
  _, start = start_enrollment_registration(
    db(), payload["token"], webauthn_config(), at=now()
  )
  return _ceremony_payload(start)


@bp.post("/enroll/finish")
def enroll_finish() -> Response:
  """Store the first passkey, consume the token, and open a session."""
  payload = request.get_json(force=True)
  passkey = finish_enrollment_registration(
    db(),
    payload["token"],
    payload["flow_id"],
    _credential(),
    webauthn_config(),
    at=now(),
  )
  return _session_response(passkey.user_id)


@bp.post("/auth/register/options")
def register_options() -> Response:
  """Start an add-passkey ceremony for the signed-in user."""
  user = current_user()
  if user is None:
    return jsonify(error="sign in first"), 401
  start = start_registration(db(), user, webauthn_config(), at=now())
  return _ceremony_payload(start)


@bp.post("/auth/register/finish")
def register_finish() -> Response:
  """Store an added passkey for the signed-in user."""
  user = current_user()
  if user is None:
    return jsonify(error="sign in first"), 401
  payload = request.get_json(force=True)
  finish_registration(
    db(), user, payload["flow_id"], _credential(), webauthn_config(), at=now()
  )
  return jsonify(ok=True)


@bp.post("/auth/passkeys/<int:passkey_id>/revoke")
def passkey_revoke(passkey_id: int) -> Response:
  """Revoke one of the signed-in user's passkeys."""
  user = current_user()
  if user is None:
    return jsonify(error="sign in first"), 401
  owned = {passkey.id for passkey in list_passkeys(db(), user.id)}
  if passkey_id not in owned:
    return jsonify(error="passkey not found"), 404
  revoke_passkey(db(), passkey_id, at=now())
  return jsonify(ok=True)


@bp.post("/logout")
def logout() -> Response:
  """Revoke the current session and clear its cookie."""
  token = request.cookies.get(SESSION_COOKIE)
  if token:
    revoke_session(db(), token, at=now())
  response = jsonify(ok=True, redirect="/")
  response.delete_cookie(SESSION_COOKIE, path="/")
  return response
