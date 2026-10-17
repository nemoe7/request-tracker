"""Render record prose as markdown with a safe subset of inline html."""

from html import unescape

import nh3
from markdown_it import MarkdownIt
from markupsafe import Markup

# CommonMark plus raw html and single-newline breaks, as a mail client reads it.
_MARKDOWN = MarkdownIt("commonmark", {"html": True, "breaks": True, "linkify": False})

# The tags GitHub keeps. Scripts and styles go, with their content.
_TAGS = {
  "a",
  "b",
  "blockquote",
  "br",
  "code",
  "del",
  "details",
  "div",
  "em",
  "h1",
  "h2",
  "h3",
  "h4",
  "h5",
  "h6",
  "hr",
  "i",
  "img",
  "kbd",
  "li",
  "ol",
  "p",
  "pre",
  "s",
  "span",
  "strong",
  "sub",
  "summary",
  "sup",
  "table",
  "tbody",
  "td",
  "th",
  "thead",
  "tr",
  "ul",
}

_ATTRIBUTES = {
  "a": {"href", "title"},
  "code": {"class"},
  "img": {"src", "alt", "title", "width", "height"},
  "td": {"align"},
  "th": {"align"},
}

_SCHEMES = {"http", "https", "mailto"}


def render_prose(text: str | None) -> Markup:
  """Render one prose block, then strip every unsafe tag and url."""
  html = _MARKDOWN.render(text or "")
  return Markup(
    nh3.clean(
      html,
      tags=_TAGS,
      clean_content_tags={"script", "style"},
      attributes=_ATTRIBUTES,
      url_schemes=_SCHEMES,
      url_relative="pass_through",
      link_rel="noopener noreferrer",
    )
  )


def plain_prose(text: str | None) -> str:
  """Flatten one prose block to a single line of text, for a list snippet."""
  html = nh3.clean(
    _MARKDOWN.render(text or ""),
    tags=set(),
    clean_content_tags={"script", "style"},
    url_schemes=_SCHEMES,
  )
  return " ".join(unescape(html).split())
