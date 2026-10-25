"""`render_schema.py` generates `docs/schema.md` from `docs/schema.dbml` without drift."""

import re

import render_schema


def test_the_page_matches_the_dbml():
  assert render_schema.OUT.read_text(encoding="utf-8") == render_schema.render()


def test_the_dbml_names_every_table_the_schema_creates():
  tables, _ = render_schema.parse(render_schema.DBML.read_text(encoding="utf-8"))
  schema = (render_schema.ROOT / "pwedepa" / "data" / "schema.sql").read_text(
    encoding="utf-8"
  )
  created = set(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", schema))

  assert {name for name, _ in tables} == created


def test_every_table_and_ref_reaches_the_page():
  tables, refs = render_schema.parse(render_schema.DBML.read_text(encoding="utf-8"))
  page = render_schema.OUT.read_text(encoding="utf-8")

  for name, _ in tables:
    assert f"    {name} {{" in page, name
  for source, column, target, _ in refs:
    assert f'    {target} ||--o{{ {source} : "{column}"' in page, (source, column)
