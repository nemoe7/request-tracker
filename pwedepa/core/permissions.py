"""Capability checks: a matching deny beats every allow, then the narrowest
allow wins. Owners hold a baseline on their own objects, and admins pass unless a
deny matches.
"""

from dataclasses import dataclass
from enum import Enum

from .models import Visibility


class Effect(str, Enum):
  ALLOW = "ALLOW"
  DENY = "DENY"


@dataclass(frozen=True)
class Grant:
  permission: str
  effect: Effect = Effect.ALLOW


@dataclass(frozen=True)
class Actor:
  id: int | None
  is_admin: bool = False
  grants: tuple[Grant, ...] = ()


OWNER_VERBS = {
  "request": {"view", "comment", "edit", "revoke"},
  "issue": {"view", "comment", "close", "reopen"},
}


def matches(pattern: str, action: str) -> bool:
  if pattern == "*" or pattern == action:
    return True
  if pattern.endswith(".*"):
    prefix = pattern[:-2]
    return action == prefix or action.startswith(prefix + ".")
  pattern_parts = pattern.split(".")
  action_parts = action.split(".")
  if len(pattern_parts) == 2 and len(action_parts) == 3:
    return pattern_parts[0] == action_parts[0] and pattern_parts[1] == action_parts[2]
  return False


def _matched(actor: Actor, effect: Effect, action: str, object_id: int | None) -> bool:
  candidates = [action]
  if object_id is not None:
    object_type, verb = action.split(".", 1)
    candidates.insert(0, f"{object_type}.{object_id}.{verb}")
  return any(
    grant.effect is effect
    and any(matches(grant.permission, candidate) for candidate in candidates)
    for grant in actor.grants
  )


def _object_matched(actor: Actor, action: str, object_id: int | None) -> bool:
  if object_id is None:
    return False
  object_type, verb = action.split(".", 1)
  object_action = f"{object_type}.{object_id}.{verb}"
  return any(
    grant.effect is Effect.ALLOW and grant.permission in ("*", object_action)
    for grant in actor.grants
  )


def authorize(
  actor: Actor,
  action: str,
  *,
  object_id: int | None = None,
  owner_id: int | None = None,
  visibility: Visibility | None = None,
) -> bool:
  """True when the actor may run `action` (`<type>.<verb>`) on an object."""
  if actor.id is None and not actor.is_admin:
    return False
  if _matched(actor, Effect.DENY, action, object_id):
    return False
  if actor.is_admin:
    return True
  object_type, verb = action.split(".", 1)
  if visibility is Visibility.PRIVATE and verb in ("view", "comment"):
    if _object_matched(actor, action, object_id):
      return True
  elif _matched(actor, Effect.ALLOW, action, object_id):
    return True
  if owner_id is not None and actor.id == owner_id:
    return verb in OWNER_VERBS.get(object_type, set())
  return False
