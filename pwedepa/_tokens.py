"""Bearer tokens and the hashes the database stores. One rule, one place."""

import hashlib
import secrets


def new_token() -> str:
  """Return a fresh random token, safe for a URL."""
  return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
  """Return the stored hash of a token."""
  return hashlib.sha256(token.encode("utf-8")).hexdigest()
