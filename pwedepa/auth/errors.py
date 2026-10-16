"""Authentication and authorization errors."""


class AuthError(Exception):
  """An auth rule blocked the operation."""


class InvalidToken(AuthError):
  """A token is unknown, expired, or already used."""


class AuthenticationFailed(AuthError):
  """Authentication did not prove the claimed identity."""
