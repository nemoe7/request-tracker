"""Render docs/schema.md from docs/schema.dbml, the diagram source.

Run it after a DBML edit:

    python scripts/render_schema.py

The test in tests/scripts/test_schema_doc.py fails when the page is stale.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DBML = ROOT / "docs" / "schema.dbml"
OUT = ROOT / "docs" / "schema.md"

HEADER = """# The database schema

`scripts/render_schema.py` generates this page from `docs/schema.dbml`. Do not edit this
page by hand. Edit the DBML and run the script.

The executable schema is `pwedepa/data/schema.sql`. `pwedepa/data/db.py` reads it once at
import, and `initialize()` runs each statement with `exec_driver_sql` the first time a
database path appears in the process.

Two repair blocks then update an older file. The first
adds `user_preferences.theme` when that column is missing. The second rebuilds
`enrollment_tokens` when the table still holds `user_id`, because a token now names a role
and not a person.

There is no migration tool and no ORM model. Alembic is not a dependency, so a schema change
reaches an old file only through a repair block. A later change numbers the schema in
`PRAGMA user_version`, one step for each change, so the blocks retire.

```mermaid
---
config:
  layout: elk
---
erDiagram
"""

FOOTER = """```

## How to change a table

1. Edit `pwedepa/data/schema.sql` for a fresh database.
2. Add a repair block to `initialize()` for an existing one. Guard it on a `PRAGMA
   table_info` check so a second run changes nothing.
3. Edit `docs/schema.dbml`, then run `python scripts/render_schema.py`.
4. Add a test that opens a database with the old shape, connects, and reads the new shape.
"""


def parse(
  text: str,
) -> tuple[list[tuple[str, list[tuple[str, str, str]]]], list[tuple]]:
  """Return the tables with their columns, and every reference, from DBML text."""
  tables: list[tuple[str, list[tuple[str, str, str]]]] = []
  refs: list[tuple[str, str, str, str, str]] = []
  name = ""
  columns: list[tuple[str, str, str]] = []
  inside = False
  for raw in text.splitlines():
    line = raw.split("//", 1)[0].strip()
    if not line:
      continue
    if not inside:
      opened = re.fullmatch(r"Table\s+(\w+)\s*\{", line)
      if opened:
        name, columns, inside = opened.group(1), [], True
        continue
      found = re.fullmatch(r"Ref:\s*(\w+)\.(\w+)\s*(<>|<|>|-)\s*(\w+)\.(\w+)", line)
      if found:
        refs.append(found.groups())
      continue
    if line == "}":
      tables.append((name, columns))
      inside = False
      continue
    column = re.fullmatch(r"(\w+)\s+(\w+)\s*(?:\[(.*)\])?", line)
    if column:
      columns.append(
        (column.group(1), column.group(2), (column.group(3) or "").strip())
      )
  return tables, refs


def _note(flags: str) -> str:
  """Turn a DBML flag list into a Mermaid attribute note."""
  parts = [part.strip() for part in flags.split(",") if part.strip()]
  words = []
  for part in parts:
    if part == "pk":
      continue
    if part == "not null":
      words.append("NOT NULL")
    elif part.startswith("default:"):
      words.append(f"DEFAULT {part.split(':', 1)[1].strip()}")
    elif part == "unique":
      words.append("UNIQUE")
    elif part == "increment":
      words.append("AUTOINCREMENT")
    else:
      words.append(part)
  return ", ".join(words)


def _arrow(op: str, left: str, right: str, column: str) -> str:
  """Return one Mermaid relationship line for a DBML reference."""
  if op == ">":
    return f'    {right} ||--o{{ {left} : "{column}"'
  if op == "<":
    return f'    {left} ||--o{{ {right} : "{column}"'
  if op == "<>":
    return f'    {left} }}o--o{{ {right} : "{column}"'
  return f'    {left} ||--|| {right} : "{column}"'


def render(text: str | None = None) -> str:
  """Return the whole page, so a test can compare it with the file."""
  source = DBML.read_text(encoding="utf-8") if text is None else text
  tables, refs = parse(source)
  lines = [HEADER.rstrip("\n")]
  for name, columns in tables:
    lines.append(f"    {name} {{")
    for column, kind, flags in columns:
      note = _note(flags)
      key = " PK" if "pk" in [part.strip() for part in flags.split(",")] else ""
      tail = f' "{note}"' if note else ""
      lines.append(f"        {kind} {column}{key}{tail}")
    lines.append("    }")
  if refs:
    lines.append("")
    for left, left_col, op, right, right_col in refs:
      column = left_col if op in (">", "-", "<>") else right_col
      lines.append(_arrow(op, left, right, column))
  lines.append(FOOTER)
  return "\n".join(lines)


def main() -> int:
  OUT.write_text(render(), encoding="utf-8")
  print(f"wrote {OUT.relative_to(ROOT)}")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
