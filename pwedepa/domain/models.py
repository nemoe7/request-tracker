"""Core domain values for Requests and Issues."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Priority(str, Enum):
  LOW = "LOW"
  MEDIUM = "MEDIUM"
  HIGH = "HIGH"
  URGENT = "URGENT"


class Visibility(str, Enum):
  PUBLIC = "PUBLIC"
  PRIVATE = "PRIVATE"


class RequestStatus(str, Enum):
  OPEN = "OPEN"
  PENDING = "PENDING"
  DELAYED = "DELAYED"
  RAISED = "RAISED"
  REJECTED = "REJECTED"
  FULFILLED = "FULFILLED"
  REVOKED = "REVOKED"


class IssueStatus(str, Enum):
  OPEN = "OPEN"
  BLOCKED = "BLOCKED"
  RESOLVED = "RESOLVED"
  CLOSED = "CLOSED"


@dataclass(frozen=True)
class Request:
  id: int
  title: str
  description: str
  status: RequestStatus = RequestStatus.OPEN
  requester_id: int | None = None
  priority_suggestion: Priority | None = None
  priority_unsure: bool = False
  visibility: Visibility = Visibility.PRIVATE
  domains: tuple[str, ...] = ()
  created_at: datetime | None = None
  updated_at: datetime | None = None
  deleted_at: datetime | None = None


@dataclass(frozen=True)
class Issue:
  id: int
  title: str
  description: str
  status: IssueStatus = IssueStatus.OPEN
  source_request_id: int | None = None
  requester_id: int | None = None
  assignee_id: int | None = None
  priority: Priority = Priority.HIGH
  visibility: Visibility = Visibility.PRIVATE
  domains: tuple[str, ...] = ()
  created_at: datetime | None = None
  updated_at: datetime | None = None
  deleted_at: datetime | None = None


@dataclass(frozen=True)
class Event:
  """One activity entry. The persistence layer stores these. The domain creates them."""

  event_type: str
  actor_id: int | None
  at: datetime | None
  data: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Change:
  """The new object state plus the activity events the change produced."""

  object: object
  events: tuple[Event, ...] = ()
