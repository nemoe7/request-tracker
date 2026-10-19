"""A dev seed fills an empty database once."""

from datetime import UTC, datetime

import pytest

from pwedepa.auth import Role, list_roles, users
from pwedepa.data import db, issues, requests
from pwedepa.data.seed import SeedError, seed, seed_from_config

AT = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)
ROWS = [
  {
    "kind": "request",
    "title": "Leaking tap",
    "description": "It drips all night.",
    "domain": "Handyman/DIY",
  },
  {
    "kind": "issue",
    "title": "Fix the tap",
    "description": "A new washer does it.",
    "domain": "Handyman/DIY",
    "status": "BLOCKED",
  },
]


def test_a_first_start_inserts_every_row(tmp_path):
  connection = db.connect(tmp_path / "seed.db")

  assert seed(connection, ROWS, at=AT) == 2

  assert [row.title for row in requests.list_requests(connection)] == ["Leaking tap"]
  found = issues.list_issues(connection)
  assert [row.title for row in found] == ["Fix the tap"]
  assert found[0].status.value == "BLOCKED"
  assert found[0].domains == ("Handyman/DIY",)


def test_a_second_start_adds_nothing(tmp_path):
  connection = db.connect(tmp_path / "seed.db")
  seed(connection, ROWS, at=AT)

  assert seed(connection, ROWS, at=AT) == 0
  assert len(requests.list_requests(connection)) == 1
  assert len(issues.list_issues(connection)) == 1


def test_a_bad_status_stops_the_seed(tmp_path):
  connection = db.connect(tmp_path / "seed.db")
  broken = [
    {
      "kind": "issue",
      "title": "x",
      "description": "y",
      "domain": "Gym",
      "status": "NOPE",
    }
  ]

  with pytest.raises(SeedError):
    seed(connection, broken, at=AT)

  assert requests.list_requests(connection) == []


def test_a_seed_domain_must_be_in_the_config(tmp_path):
  settings = {
    "domains": [{"name": "Gym", "description": "Training plans."}],
    "seed": [
      {
        "kind": "request",
        "title": "Lift the bench",
        "description": "The legs wobble.",
        "domain": "Gimm",
      }
    ],
  }

  with pytest.raises(SeedError) as error:
    seed_from_config(tmp_path / "seed.db", settings, at=AT)

  assert "Gimm" in str(error.value)
  connection = db.connect(tmp_path / "seed.db")
  assert requests.list_requests(connection) == []


def test_a_seeded_request_names_a_dummy_requester(tmp_path):
  connection = db.connect(tmp_path / "seed.db")

  seed(connection, ROWS, at=AT)

  row = requests.list_requests(connection)[0]
  assert row.requester_id is not None, "a seeded row with no owner reads as a dash"
  owner = users.get_user(connection, row.requester_id)
  assert owner.username.startswith("seed-")
  assert Role.REQUESTER in list_roles(connection, owner.id)


def test_a_seeded_issue_keeps_no_requester(tmp_path):
  connection = db.connect(tmp_path / "seed.db")

  seed(connection, ROWS, at=AT)

  assert issues.list_issues(connection)[0].requester_id is None


def test_a_second_seed_adds_no_more_people(tmp_path):
  connection = db.connect(tmp_path / "seed.db")
  seed(connection, ROWS, at=AT)
  people = users.count_users(connection)

  seed(connection, ROWS, at=AT)

  assert users.count_users(connection) == people
