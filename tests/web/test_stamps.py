from datetime import UTC, datetime, timedelta

from pwedepa.web.stamps import format_stamp

NOW = datetime(2026, 10, 16, 15, 30, tzinfo=UTC)


def test_relative_under_72_hours():
  assert format_stamp(None, "12", NOW) == ""
  assert format_stamp(NOW - timedelta(seconds=20), "12", NOW) == "just now"
  assert format_stamp(NOW - timedelta(minutes=5), "12", NOW) == "5m ago"
  assert format_stamp(NOW - timedelta(hours=3), "24", NOW) == "3h ago"
  assert format_stamp(NOW - timedelta(hours=26), "12", NOW) == "1d ago"
  assert format_stamp(NOW - timedelta(hours=71), "12", NOW) == "2d ago"
  assert format_stamp(NOW + timedelta(minutes=2), "12", NOW) == "just now"


def test_absolute_after_72_hours_follows_the_clock_choice():
  old = datetime(2026, 10, 12, 13, 5, tzinfo=UTC)
  assert format_stamp(old, "24", NOW) == "Oct 12, 13:05"
  assert format_stamp(old, "12", NOW) == "Oct 12, 1:05 PM"
