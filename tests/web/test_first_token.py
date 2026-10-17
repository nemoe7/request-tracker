from datetime import UTC, datetime

from pwedepa.auth import Role, enrollment
from pwedepa.data import db as data_db
from pwedepa.web import create_app, print_first_token


def test_the_first_start_prints_one_admin_token(tmp_path, capsys):
  app = create_app({"DATABASE": str(tmp_path / "first.db")})
  print_first_token(app)
  out = capsys.readouterr().out
  token = next(
    line.split(": ", 1)[1].strip()
    for line in out.splitlines()
    if line.startswith("Enrollment token: ")
  )

  connection = data_db.connect(app.config["DATABASE"])
  found = enrollment.validate_enrollment_token(connection, token, at=datetime.now(UTC))
  assert found.role is Role.ADMIN
  connection.close()

  print_first_token(app)
  second = capsys.readouterr().out
  assert "Enrollment token: " not in second
