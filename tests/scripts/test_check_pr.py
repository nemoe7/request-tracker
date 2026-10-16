import check_pr


def test_good_commit_passes():
  assert check_pr.validate_commit("feat: add request intake") == []


def test_bad_commit_reports_the_rule_it_breaks():
  failures = check_pr.validate_commit("Add stuff.")
  messages = " ".join(str(failure) for failure in failures)
  assert "lowercase" in messages or "must match" in messages


def test_commit_with_a_body_fails():
  failures = check_pr.validate_commit("feat: add request intake\n\na body")
  assert any("no commit body" in str(failure) for failure in failures)


def test_pr_body_needs_the_locked_headings(tmp_path):
  body = tmp_path / "body.md"
  body.write_text("## Changes\n\n- one change\n", encoding="utf-8")
  failures = check_pr.check(None, None, str(body), False)
  assert any("Summary" in str(failure) for failure in failures)


def test_pr_body_in_order_passes(tmp_path):
  body = tmp_path / "body.md"
  body.write_text(
    "## Summary\n\nOne paragraph.\n\n"
    "## Changes\n\n- one change\n\n"
    "## Validation\n\n- [x] tests pass\n",
    encoding="utf-8",
  )
  assert check_pr.check(None, None, str(body), False) == []
