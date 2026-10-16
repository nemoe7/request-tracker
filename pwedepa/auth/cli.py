"""Administrative CLI for the first admin, users, and enrollment tokens."""

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

from pwedepa.data import connect

from . import enrollment, grants, users
from .errors import AuthError
from .grants import Role


def main(argv: list[str] | None = None) -> int:
  parser = _parser()
  args = parser.parse_args(argv)
  db = connect(args.database)
  try:
    at = datetime.now(UTC)
    if args.command == "create-admin":
      user = users.create_user(db, args.username, args.display_name, at=at)
      grants.assign_role(db, user.id, Role.ADMIN, at=at)
      _print_token(db, user.id, at)
    elif args.command == "create-user":
      user = users.create_user(db, args.username, args.display_name, at=at)
      grants.assign_role(db, user.id, Role(args.role), at=at)
      _print_token(db, user.id, at)
    elif args.command == "enrollment-token":
      user = users.get_user_by_username(db, args.username)
      if user is None:
        raise AuthError("the user does not exist")
      _print_token(db, user.id, at)
    return 0
  except AuthError as exc:
    print(f"error: {exc}", file=sys.stderr)
    return 2
  finally:
    db.close()


def _print_token(db, user_id: int, at: datetime) -> None:
  issued = enrollment.issue_enrollment_token(db, user_id, at=at)
  print(f"User ID: {user_id}")
  print(f"Enrollment token: {issued.token}")
  print("Store the token now. It is shown only once.")


def _parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(prog="python -m pwedepa.auth")
  commands = parser.add_subparsers(dest="command", required=True)

  admin = commands.add_parser("create-admin", help="create the first admin user")
  _add_database(admin)
  _add_user(admin)

  user = commands.add_parser("create-user", help="create a user and enrollment token")
  _add_database(user)
  _add_user(user)
  user.add_argument(
    "--role",
    choices=[role.value for role in Role],
    default=Role.REQUESTER.value,
  )

  token = commands.add_parser(
    "enrollment-token", help="issue a new enrollment token for a user"
  )
  _add_database(token)
  token.add_argument("--username", required=True)
  return parser


def _add_database(parser: argparse.ArgumentParser) -> None:
  parser.add_argument("--database", type=Path, required=True)


def _add_user(parser: argparse.ArgumentParser) -> None:
  parser.add_argument("--username", required=True)
  parser.add_argument("--display-name", required=True)
