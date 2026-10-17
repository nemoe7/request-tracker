import pytest

from pwedepa.web.prose import plain_prose, render_prose


def test_markdown_reads_as_rich_text():
  html = str(render_prose("**bold** and `code`\n\n- one\n- two"))
  assert "<strong>bold</strong>" in html
  assert "<code>code</code>" in html
  assert "<li>one</li>" in html


def test_a_single_newline_stays_a_break():
  assert render_prose("first\nsecond").count("<br") == 1


def test_inline_html_survives_a_clean_pass():
  html = str(render_prose("<details><summary>More</summary><em>kept</em></details>"))
  assert "<details>" in html
  assert "<summary>More</summary>" in html
  assert "<em>kept</em>" in html


@pytest.mark.parametrize(
  "prose",
  [
    "<script>alert(1)</script>",
    "<img src=x onerror=alert(1)>",
    '<a href="javascript:alert(1)">go</a>',
    '<a href="data:text/html;base64,PHNjcmlwdD4=">go</a>',
    '<div style="position:fixed">cover</div>',
  ],
)
def test_unsafe_html_never_reaches_the_page(prose):
  html = str(render_prose(prose))
  for bad in ("<script", "onerror", "javascript:", "data:text/html", "style="):
    assert bad not in html


def test_a_link_keeps_its_address_and_gains_noopener():
  html = str(render_prose("[docs](https://example.com/docs)"))
  assert 'href="https://example.com/docs"' in html
  assert 'rel="noopener noreferrer"' in html


def test_a_relative_link_stays_local():
  assert 'href="/static/guide.pdf"' in str(render_prose("[guide](/static/guide.pdf)"))
  assert 'src="/static/shot.png"' in str(render_prose("![shot](/static/shot.png)"))


def test_a_plain_snippet_drops_tags_and_markup():
  assert plain_prose("**bold** <b>tag</b>\nnext") == "bold tag next"


def test_an_empty_body_renders_empty():
  assert str(render_prose(None)) == ""
  assert plain_prose(None) == ""
