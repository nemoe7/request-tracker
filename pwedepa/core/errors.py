class CoreError(Exception):
  pass


class InvalidTransition(CoreError):
  pass


class PermissionDenied(CoreError):
  pass


class ConfirmationRequired(CoreError):
  pass
