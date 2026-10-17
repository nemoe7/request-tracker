"""Render docs/schema.md from docs/schema.dbml, the diagram source.

    python scripts/render_schema.py

The page is a Mermaid entity diagram, so GitHub draws it. The executable
schema stays in pwedepa/data/schema.sql, which this file does not touch.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DBML = ROOT / "docs" / "schema.dbml"
OUT = ROOT / "docs" / "schema.md"

TABLE = re.compile(r"^Table\s+(\w+)\s*\{\s*$")
COLUMN = re.compile(r"^(\w+)\s+(\w+)(?:\s+\[(.*)\])?$")
REF = re.compile(r"^Ref:\s*(\w+)\.(\w+)\s*>\s*(\w+)\.(\w+)$")
INDEX = re.compile(r"^\((.*)\)\s*\[pk\]$")

HEADER = """# The database schema

`docs/schema.dbml` is the source of this page, and `scripts/render_schema.py` draws it.
Run the script after a DBML edit. The executable schema lives in
`pwedepa/data/schema.sql`.

`pwedepa/data/db.py` reads `schema.sql` at import. `initialize()` runs each statement with
`exec_driver_sql` the first time a database path appears in the process, then stamps
`PRAGMA user_version`. The number is 1 today.

A 0.1.0 file carries 0, and step 1 gives it the theme column and a token that names a role.
A file from a newer release stops the app with its path and the command to delete it.

`docs/schema.svg` is the dbdiagram export of the same DBML, and this script does not draw
it. Export it again after a DBML edit.

"""

FOOTER = """
## How to change a table

1. Edit `pwedepa/data/schema.sql` for a fresh database.
2. Raise `SCHEMA_VERSION` in `pwedepa/data/db.py`, and add one step that guards on the
   number it moves from, so a second run changes nothing.
3. Edit `docs/schema.dbml`, then run `python scripts/render_schema.py`.
4. Add a test that opens a database with the old shape, connects, and reads the new shape.
"""


def parse(
  text: str,
) -> tuple[list[tuple[str, list[tuple[str, str, str]]]], list[tuple]]:
  """Return the tables with their columns, and the refs, from DBML text."""
  tables: list[tuple[str, list[tuple[str, str, str]]]] = []
  refs: list[tuple[str, str, str, str]] = []
  name = ""
  columns: list[tuple[str, str, str]] = []
  in_indexes = False
  for raw in text.splitlines():
    line = raw.split("//", 1)[0].strip()
    if not line:
      continue
    if line.startswith("Ref:"):
      found = REF.fullmatch(line)
      if found is None:
        raise ValueError(f"the render reads only a many-to-one ref: {line}")
      refs.append(found.groups())
      continue
    if not name:
      opened = TABLE.fullmatch(line)
      if opened:
        name = opened.group(1)
        columns = []
      continue
    if in_indexes:
      if line.startswith("}"):
        in_indexes = False
      continue
    if line.startswith("indexes"):
      in_indexes = True
      continue
    if line.startswith("}"):
      tables.append((name, columns))
      name = ""
      continue
    if line.startswith("Note:"):
      continue
    if line.startswith("("):
      continue
    found = COLUMN.fullmatch(line)
    if found is None:
      raise ValueError(f"the render cannot read this column: {line}")
    columns.append(found.groups())
  return tables, refs


def _flags(attributes: str) -> tuple[str, list[str]]:
  """Return the key marker and the note parts for one column."""
  parts = [part.strip() for part in attributes.split(",") if part.strip()]
  key = ""
  notes: list[str] = []
  for part in parts:
    lowered = part.lower()
    if lowered == "pk":
      key = "PK"
    elif lowered.startswith("default:"):
      notes.append(f"DEFAULT {part.split(':', 1)[1].strip()}")
    elif lowered == "unique":
      key = "UK"
    elif lowered == "increment":
      notes.append("AUTOINCREMENT")
    elif lowered == "not null":
      notes.append("NOT NULL")
    else:
      notes.append(part.upper())
  return key, notes


def render() -> str:
  """Return the page for the DBML on disk."""
  tables, refs = parse(DBML.read_text(encoding="utf-8"))
  lines = [
    HEADER.rstrip("\n"),
    "",
    "```mermaid",
    "---",
    "config:",
    "  layout: elk",
    "  elk:",
    "    nodePlacementStrategy: LINEAR_SEGMENTS",
    "---",
    "erDiagram",
    "    direction LR",
  ]
  for name, columns in tables:
    lines.append(f"    {name} {{")
    for column, kind, attributes in columns:
      key, notes = _flags(attributes or "")
      tail = f" {key}" if key else ""
      if notes:
        tail += f' "{", ".join(notes)}"'
      lines.append(f"        {kind} {column}{tail}")
    lines.append("    }")
  for source, column, target, _ in refs:
    lines.append(f'    {target} ||--o{{ {source} : "{column}"')
  lines.extend(["```", FOOTER])
  return "\n".join(lines)


if __name__ == "__main__":
  OUT.write_text(render(), encoding="utf-8")
  print(f"wrote {OUT}")
