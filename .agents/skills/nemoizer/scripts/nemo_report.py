"""Format findings, their messages, and the summary footer."""

from markers import is_advisory_finding
from nemo_rules import ADVISORY_RULE_IDS, RULE_DESCRIPTIONS

NMP100_LABELS = {
  "paragraph": "paragraph",
  "table": "table cell",
  "list": "list item",
  "heading": "heading",
  "blockquote": "blockquote",
}


def describe_finding(row):
  """Format a human-readable violation description for one prose or comment finding."""
  if row["rule"] == "NMP100" and row.get("kind") in NMP100_LABELS:
    label = NMP100_LABELS[row["kind"]]
    return f"{label} has {row['count']} sentences (cap {row['cap']})"
  if row["rule"] == "NMU100":
    return (
      f'label "{row["text"]}" carries "{row["word"]}"'
      f" ({row['count']} words, cap {row['cap']})"
    )
  if row["rule"] == "NMU200":
    return f'{row["scale"]} divisor paired with mismatched byte label "{row["text"]}"'
  template = RULE_DESCRIPTIONS.get(row["rule"], "{count} (cap {cap})")
  if "{count}" in template:
    return template.format(count=row["count"], cap=row["cap"])
  if row["count"] > 1:
    return f"{template} ({row['count']} matches)"
  return template


def format_finding(path, line, code, message, source_line=None, status=None):
  """Format one finding in STE-linter style with an indented source snippet."""
  advisory = code in ADVISORY_RULE_IDS or status == "manual_review"
  level = "advisory" if advisory else "advisory-free"
  suffix = " (manual review)" if advisory and "(manual review)" not in message else ""
  header = f"{path}:{line}: [{code}] ({level}) {message}{suffix}"
  if source_line is None:
    return header
  snippet = source_line.strip()
  if len(snippet) > 100:
    snippet = snippet[:97] + "..."
  return f"{header}\n    {snippet}" if snippet else header


def is_advisory(finding):
  return is_advisory_finding(finding, ADVISORY_RULE_IDS)


def format_summary(findings):
  """Format the STE-linter summary footer for a non-empty finding list."""
  if not findings:
    return ""
  hard = sum(1 for item in findings if not is_advisory(item))
  advisory = len(findings) - hard
  files = len({item.splitlines()[0].rsplit(":", 2)[0] for item in findings})
  return (
    f"\nSummary: {hard} hard violation(s), "
    f"{advisory} advisory finding(s) across {files} file(s)."
  )
