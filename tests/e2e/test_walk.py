"""End to end in a browser: the walk a person takes through the running app.

The server is the same child process the socket checks use. Chromium drives the
pages, so a click, a redirect, and a computed style are the check.
"""

import os

import pytest
from playwright.sync_api import expect, sync_playwright

PHONE = {"width": 390, "height": 844}
DESKTOP = {"width": 1440, "height": 1000}
OVERFLOW = (
  "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
)


@pytest.fixture(scope="session")
def browser():
  with sync_playwright() as driver:
    engine = driver.chromium.launch(
      executable_path=os.environ.get("PWEDEPA_CHROMIUM") or None,
      args=["--no-sandbox", "--disable-dev-shm-usage"],
    )
    yield engine
    engine.close()


@pytest.fixture
def page(browser, served):
  """A fresh browser page signed in with one cookie, at a chosen size."""

  def open_page(cookie: str, viewport: dict[str, int]):
    context = browser.new_context(viewport=viewport)
    context.add_cookies(
      [
        {
          "name": "pwedepa_session",
          "value": cookie.split("=", 1)[1],
          "url": served["base"],
        }
      ]
    )
    return context, context.new_page()

  yield open_page


def test_the_bar_opens_the_new_request_chooser_in_the_pane(page, served):
  context, tab = page(served["cookie"], DESKTOP)
  try:
    tab.goto(f"{served['base']}/", wait_until="networkidle")
    tab.locator("a.bell[href='/requests/new']").first.click()
    tab.wait_for_url("**/requests/new")
    pane = tab.locator(".inspector")
    expect(pane.locator("h1")).to_have_text("Which domain is this for?")
    assert pane.locator("a[href$='/requests/new']").count() == 6, "six Domains"
    expect(pane.get_by_role("link", name="Cancel")).to_be_visible()
    assert tab.evaluate(OVERFLOW) == 0
  finally:
    context.close()


def test_a_picked_row_keeps_its_band_only_where_the_pane_has_room(page, served):
  """The band reads as one block on a wide screen, and never tints one cell on a phone."""
  marks = {}
  for name, viewport in (("phone", PHONE), ("desktop", DESKTOP)):
    context, tab = page(served["cookie"], viewport)
    try:
      tab.goto(f"{served['base']}/", wait_until="networkidle")
      row = tab.locator(".mail-row.is-selected").first
      expect(row).to_be_visible()
      marks[name] = row.locator(".mail-from").evaluate(
        "cell => ({ background: getComputedStyle(cell).backgroundColor,"
        " shadow: getComputedStyle(cell).boxShadow })"
      )
      assert tab.evaluate(OVERFLOW) == 0
    finally:
      context.close()

  assert marks["phone"]["background"] in ("rgba(0, 0, 0, 0)", "transparent")
  assert marks["phone"]["shadow"] == "none"
  assert marks["desktop"]["background"] not in ("rgba(0, 0, 0, 0)", "transparent")
  assert "inset" in marks["desktop"]["shadow"]


def test_a_typed_token_url_lands_on_the_users_page(page, served):
  context, tab = page(served["cookie"], DESKTOP)
  try:
    tab.goto(f"{served['base']}/admin/tokens")
    expect(tab).to_have_url(f"{served['base']}/admin/users")
    expect(tab.locator("h1")).to_have_text("Users")
  finally:
    context.close()
