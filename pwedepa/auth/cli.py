"""Administrative CLI: issue a sign-up token with one role."""

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

from pwedepa.data import connect

from . import enrollment
from .errors import AuthError
from .grants import Role


def main(argv: list[str] | None = None) -> int:
  parser = _parser()
  args = parser.parse_args(argv)
  db = connect(args.database)
  try:
    at = datetime.now(UTC)
    role = Role.ADMIN if args.command == "create-admin" else Role(args.role)
    _print_token(db, role, at)
    return 0
  except AuthError as exc:
    print(f"error: {exc}", file=sys.stderr)
    return 2
  finally:
    db.close()


def _print_token(db, role: Role, at: datetime) -> None:
  issued = enrollment.issue_enrollment_token(db, role=role, at=at)
  print(f"Role: {role.value}")
  print(f"Sign-up token: {issued.token}")
  print("Store the token now. It is shown only once.")


def _parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(prog="python -m pwedepa.auth")
  commands = parser.add_subparsers(dest="command", required=True)

  admin = commands.add_parser(
    "create-admin", help="issue a sign-up token with the admin role"
  )
  _add_database(admin)

  token = commands.add_parser("issue-token", help="issue a sign-up token with one role")
  _add_database(token)
  token.add_argument(
    "--role",
    choices=[role.value for role in Role],
    default=Role.REQUESTER.value,
  )
  return parser


def _add_database(parser: argparse.ArgumentParser) -> None:
  parser.add_argument("--database", type=Path, required=True)
