"""Collect first-party prose with source anchors and explicit manual-review limits.

Scope is Python comments and docstrings, Markdown files, and the text and
attribute strings of a Jinja template. Runtime strings stay out: they are code,
not prose.
"""

import argparse
import ast
import fnmatch
import io
import json
import re
import subprocess
import sys
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

EXCLUDES = (
  ".agents/**",
  ".github/workflows/gemini-release.yml",
  ".github/workflows/gemini-release-evidence.json",
  ".github/workflows/gemini_release.py",
  "node_modules/**",
  "**/node_modules/**",
  "vendor/**",
  "**/vendor/**",
  "ARENA.md",
  "AGENTS.md",
  "**/AGENTS.md",
  "LICENSE*",
  "**/LICENSE*",
  "uv.lock",
  "*.png",
  "*.jpg",
  "*.jpeg",
  "*.gif",
  "*.ico",
  "*.woff*",
)


def tracked_files(excludes: list[str] | tuple[str, ...] = ()) -> list[Path]:
  listed = subprocess.run(
    ["git", "-C", str(ROOT), "ls-files", "-z"],
    capture_output=True,
    text=True,
    check=True,
  ).stdout
  return [
    Path(name)
    for name in listed.split("\0")
    if name
    and not any(
      fnmatch.fnmatchcase(name, pattern) for pattern in (*EXCLUDES, *excludes)
    )
  ]


TEMPLATE_TEXT = re.compile(r">([^<>]+)<")
TEMPLATE_ATTR = re.compile(r'\b(title|placeholder|aria-label|alt)="([^"<>]+)"')
JINJA_TOKEN = re.compile(r"\{\{.*?\}\}|\{%.*?%\}|\{#.*?#\}", re.DOTALL)
RAW_BLOCK = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
HAS_WORD = re.compile(r"[A-Za-z]")


def _masked(source: str) -> str:
  """Blank out Jinja tags, keeping every offset, so anchors stay true."""
  return JINJA_TOKEN.sub(lambda found: " " * len(found.group(0)), source)


def _template_parts(source: str) -> list[tuple[int, str, str]]:
  """The text nodes and attribute strings a reader sees in a rendered page."""
  masked = RAW_BLOCK.sub(lambda found: " " * len(found.group(0)), _masked(source))
  parts = []
  for match in TEMPLATE_TEXT.finditer(masked):
    text = " ".join(match.group(1).split())
    if HAS_WORD.search(text):
      line = masked.count("\n", 0, match.start(1)) + 1
      parts.append((line, "template", text))
  for match in TEMPLATE_ATTR.finditer(masked):
    text = " ".join(match.group(2).split())
    if HAS_WORD.search(text):
      line = masked.count("\n", 0, match.start(2)) + 1
      parts.append((line, "attribute", text))
  return parts


def extract(path: Path) -> tuple[list[tuple[int, str, str]], list[str]]:
  """Extract text without execution, with source anchors and coverage limits."""
  if path.is_symlink():
    return [], ["Symbolic link. Review its target manually."]
  if path.suffix not in (".py", ".md", ".jinja"):
    return [], ["Unsupported format. Review its prose manually."]
  source = path.read_text(encoding="utf-8")
  if path.suffix == ".md":
    return [(1, "markdown", source)], []
  if path.suffix == ".jinja":
    return _template_parts(source), []
  tree = ast.parse(source, filename=str(path))
  parts = []
  for node in ast.walk(tree):
    if isinstance(
      node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    ):
      first = node.body[0] if node.body else None
      if (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Constant)
        and isinstance(first.value.value, str)
      ):
        parts.append((first.lineno, "docstring", first.value.value))
  for token in tokenize.generate_tokens(io.StringIO(source).readline):
    if token.type == tokenize.COMMENT:
      parts.append((token.start[0], "comment", token.string.lstrip("# ")))
  return sorted(parts), []


def prose(path: Path) -> str:
  return "\n".join(text for _, _, text in extract(path)[0])


def page_files() -> list[Path]:
  return [ROOT / path for path in tracked_files() if path.suffix == ".md"]


def collect(paths: list[Path]) -> list[dict]:
  records = []
  for relative in paths:
    path = ROOT / relative
    try:
      parts, manual = extract(path)
    except (OSError, SyntaxError, UnicodeError, ValueError, TypeError) as exc:
      parts, manual = [], [f"Extraction error: {exc}"]
    records.append(
      {
        "path": str(path),
        "parts": [
          {"line": line, "kind": kind, "text": text} for line, kind, text in parts
        ],
        "manual": manual,
      }
    )
  return records


def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument(
    "--exclude",
    action="append",
    default=[],
    metavar="GLOB",
    help="Exclude another tracked path pattern.",
  )
  args = parser.parse_args()
  records = collect(tracked_files(args.exclude))
  manual = sum(bool(record["manual"]) for record in records)
  print(json.dumps({"files": records, "manual_files": manual}, indent=2))
  return 2 if manual else 0


if __name__ == "__main__":
  sys.exit(main())
