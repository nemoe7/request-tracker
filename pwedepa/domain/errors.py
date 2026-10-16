"""Domain errors. HTTP and UI layers translate these into responses."""


class DomainError(Exception):
  """A domain rule blocked the operation."""


class InvalidTransition(DomainError):
  """The state machine has no move from the current state to the target."""


class PermissionDenied(DomainError):
  """The actor lacks the capability for the operation."""


class ConfirmationRequired(DomainError):
  """The operation needs an explicit confirmation first."""
