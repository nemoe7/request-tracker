class AuthError(Exception):
  pass


class InvalidToken(AuthError):
  """A token is unknown, expired, or already used."""


class AuthenticationFailed(AuthError):
  pass
