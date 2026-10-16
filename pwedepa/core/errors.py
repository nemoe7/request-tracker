"""Domain errors. HTTP and UI layers translate these into responses."""


class CoreError(Exception):
  """A core rule blocked the operation."""


class InvalidTransition(CoreError):
  """The state machine has no move from the current state to the target."""


class PermissionDenied(CoreError):
  """The actor lacks the capability for the operation."""


class ConfirmationRequired(CoreError):
  """The operation needs an explicit confirmation first."""
