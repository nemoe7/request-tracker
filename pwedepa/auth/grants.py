"""Roles, direct permission grants, and actor construction."""

from datetime import datetime
from enum import Enum

from sqlalchemy.engine import Connection

from pwedepa.core import Actor, Effect, Grant
from pwedepa.data._rows import pack_time

from .audit import record_audit
from .errors import AuthenticationFailed
from .users import UserStatus, get_user


class Role(str, Enum):
  ADMIN = "ADMIN"
  REQUESTER = "REQUESTER"
  ASSIGNEE = "ASSIGNEE"


ROLE_GRANTS = {
  Role.ADMIN: (Grant("*"),),
  Role.REQUESTER: (
    Grant("request.create"),
    Grant("request.view"),
    Grant("request.comment"),
    Grant("issue.view"),
    Grant("issue.comment"),
  ),
  Role.ASSIGNEE: (
    Grant("issue.view"),
    Grant("issue.comment"),
  ),
}


def assign_role(
  db: Connection,
  user_id: int,
  role: Role,
  *,
  at: datetime,
  actor_id: int | None = None,
) -> None:
  _require_user(db, user_id)
  cursor = db.exec_driver_sql(
    "INSERT OR IGNORE INTO user_roles (user_id, role, created_at) VALUES (?, ?, ?)",
    (user_id, role.value, pack_time(at)),
  )
  if cursor.rowcount:
    record_audit(
      db,
      "role.assigned",
      at=at,
      actor_id=actor_id,
      object_type="user",
      object_id=user_id,
      data={"role": role.value},
      commit=False,
    )
  db.commit()


def revoke_role(
  db: Connection,
  user_id: int,
  role: Role,
  *,
  at: datetime,
  actor_id: int | None = None,
) -> bool:
  _require_user(db, user_id)
  cursor = db.exec_driver_sql(
    "DELETE FROM user_roles WHERE user_id = ? AND role = ?", (user_id, role.value)
  )
  if cursor.rowcount:
    record_audit(
      db,
      "role.revoked",
      at=at,
      actor_id=actor_id,
      object_type="user",
      object_id=user_id,
      data={"role": role.value},
      commit=False,
    )
  db.commit()
  return cursor.rowcount == 1


def list_roles(db: Connection, user_id: int) -> tuple[Role, ...]:
  _require_user(db, user_id)
  rows = db.exec_driver_sql(
    "SELECT role FROM user_roles WHERE user_id = ? ORDER BY role", (user_id,)
  )
  return tuple(Role(row._mapping["role"]) for row in rows)


def grant_permission(
  db: Connection,
  user_id: int,
  grant: Grant,
  *,
  at: datetime,
  actor_id: int | None = None,
) -> None:
  _require_user(db, user_id)
  if not grant.permission.strip():
    raise ValueError("a grant needs a permission")
  db.exec_driver_sql(
    "INSERT INTO permission_grants (user_id, permission, effect, created_at) "
    "VALUES (?, ?, ?, ?) "
    "ON CONFLICT(user_id, permission, effect) DO UPDATE SET revoked_at = NULL",
    (user_id, grant.permission, grant.effect.value, pack_time(at)),
  )
  record_audit(
    db,
    "permission.granted",
    at=at,
    actor_id=actor_id,
    object_type="user",
    object_id=user_id,
    data={"permission": grant.permission, "effect": grant.effect.value},
    commit=False,
  )
  db.commit()


def revoke_permission(
  db: Connection,
  user_id: int,
  permission: str,
  effect: Effect,
  *,
  at: datetime,
  actor_id: int | None = None,
) -> bool:
  _require_user(db, user_id)
  cursor = db.exec_driver_sql(
    "UPDATE permission_grants SET revoked_at = ? "
    "WHERE user_id = ? AND permission = ? AND effect = ? AND revoked_at IS NULL",
    (pack_time(at), user_id, permission, effect.value),
  )
  if cursor.rowcount:
    record_audit(
      db,
      "permission.revoked",
      at=at,
      actor_id=actor_id,
      object_type="user",
      object_id=user_id,
      data={"permission": permission, "effect": effect.value},
      commit=False,
    )
  db.commit()
  return cursor.rowcount == 1


def list_direct_grants(db: Connection, user_id: int) -> tuple[Grant, ...]:
  """List active grants stored for one user, without role grants."""
  _require_user(db, user_id)
  rows = db.exec_driver_sql(
    "SELECT permission, effect FROM permission_grants "
    "WHERE user_id = ? AND revoked_at IS NULL ORDER BY id",
    (user_id,),
  )
  return tuple(
    Grant(row._mapping["permission"], Effect(row._mapping["effect"])) for row in rows
  )


def grants_for_user(db: Connection, user_id: int) -> tuple[Grant, ...]:
  grants: list[Grant] = []
  for role in list_roles(db, user_id):
    grants.extend(ROLE_GRANTS[role])
  rows = db.exec_driver_sql(
    "SELECT permission, effect FROM permission_grants "
    "WHERE user_id = ? AND revoked_at IS NULL ORDER BY id",
    (user_id,),
  )
  grants.extend(
    Grant(row._mapping["permission"], Effect(row._mapping["effect"])) for row in rows
  )
  return tuple(dict.fromkeys(grants))


def actor_for_user(db: Connection, user_id: int) -> Actor:
  """Build the core actor for an active user."""
  user = get_user(db, user_id)
  if user is None:
    raise AuthenticationFailed("the user does not exist")
  if user.status is UserStatus.ARCHIVED:
    raise AuthenticationFailed("archived users cannot authenticate")
  roles = list_roles(db, user_id)
  return Actor(
    id=user.id,
    is_admin=Role.ADMIN in roles,
    grants=grants_for_user(db, user_id),
  )


def _require_user(db: Connection, user_id: int) -> None:
  if get_user(db, user_id) is None:
    raise AuthenticationFailed("the user does not exist")
