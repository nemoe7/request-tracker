"""Fail the suite when docs/schema.md no longer matches the DBML."""

import render_schema


def test_the_schema_page_matches_the_dbml():
  assert render_schema.OUT.read_text(encoding="utf-8") == render_schema.render()


def test_every_table_and_reference_reaches_the_page():
  tables, refs = render_schema.parse(render_schema.DBML.read_text(encoding="utf-8"))
  page = render_schema.OUT.read_text(encoding="utf-8")

  assert tables
  for name, _ in tables:
    assert f"    {name} {{" in page, name
  assert page.count("--") >= len(refs), "a reference went missing"
