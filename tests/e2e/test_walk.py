"""End to end in a browser: the walk a person takes through the running app.

The server is the same child process the socket checks use. Chromium drives the
pages, so a click, a redirect, and a computed style are the check.
"""

import os
import re

import pytest
from conftest import walk
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


@pytest.fixture
def passkey_page(browser, served):
  """A signed-out page on the passkey origin, with a virtual authenticator."""
  context = browser.new_context()
  tab = context.new_page()
  session = context.new_cdp_session(tab)
  session.send("WebAuthn.enable")
  session.send(
    "WebAuthn.addVirtualAuthenticator",
    {
      "options": {
        "protocol": "ctap2",
        "transport": "internal",
        "hasResidentKey": True,
        "hasUserVerification": True,
        "isUserVerified": True,
        "automaticPresenceSimulation": True,
      }
    },
  )
  yield context, tab
  context.close()


def test_a_passkey_enrolls_and_signs_in_through_the_browser(passkey_page, served):
  """The real WebAuthn path runs: admin token, enroll, sign out, sign in."""
  base = f"http://localhost:{served['port']}"
  admin = walk(served["base"], served["cookie"])
  status, _, body = admin("/admin/tokens", {"role": "REQUESTER"})
  assert status == 200
  found = re.search(r'id="issued-token"[^>]*value="([^"]+)"', body)
  assert found, "the users page shows the sign-up token once"
  token = found.group(1)

  context, tab = passkey_page
  tab.goto(f"{base}/enroll?token={token}", wait_until="networkidle")
  tab.fill("#username", "nina")
  tab.fill("#display-name", "Nina Enrols")
  tab.click("button[type=submit]", force=True)
  tab.wait_for_url("**/requests", timeout=15_000)
  expect(tab.locator("h1").first).to_have_text("Requests")

  context.clear_cookies()
  tab.goto(f"{base}/login", wait_until="networkidle")
  tab.click("#login-button")
  tab.wait_for_url("**/requests", timeout=15_000)
  expect(tab.locator("h1").first).to_have_text("Requests")


def test_the_service_worker_takes_control_after_a_load(page, served):
  """The page registers `/sw.js`, and the worker claims its scope."""
  context, tab = page(served["cookie"], DESKTOP)
  try:
    tab.goto(f"{served['base']}/", wait_until="networkidle")
    worker = tab.evaluate(
      """async () => {
        const ready = await navigator.serviceWorker.ready;
        const script = ready.active || ready.waiting || ready.installing;
        return { scope: ready.scope, script: script && script.scriptURL };
      }"""
    )
    assert worker["scope"] == f"{served['base']}/"
    assert worker["script"] == f"{served['base']}/sw.js"
  finally:
    context.close()


def test_nuu_recipes_work_in_the_browser(page, served):
  """Page memory paints before fetch finishes, and modal and loading helpers work."""
  context, tab = page(served["cookie"], DESKTOP)
  try:
    tab.goto(f"{served['base']}/", wait_until="networkidle")
    check = tab.evaluate(
      """async () => {
        let fetchCount = 0;
        let releaseFetch = null;
        const origFetch = window.fetch.bind(window);
        window.fetch = (input, init) => {
          const url = typeof input === "string" ? input : input.url;
          if (url.endsWith("/notifications")) {
            fetchCount += 1;
            if (fetchCount === 2) {
              return new Promise((resolve) => {
                releaseFetch = () => resolve(origFetch(input, init));
              });
            }
          }
          return origFetch(input, init);
        };

        const inboxLink = document.querySelector('a.bell[href="/notifications"]');
        inboxLink.click();
        await new Promise((r) => setTimeout(r, 150));
        const firstHeading = document.querySelector("main.wrap h1")?.textContent?.trim();

        document.querySelector("a.brand").click();
        await new Promise((r) => setTimeout(r, 150));

        document.querySelector('a.bell[href="/notifications"]').click();
        const paintedBeforeAnswer =
          document.querySelector("main.wrap h1")?.textContent?.trim() === "Notifications";
        const busyOnHit = document.querySelector("main.wrap")?.dataset?.loading === "true";
        if (releaseFetch) releaseFetch();
        await new Promise((r) => setTimeout(r, 150));
        window.fetch = origFetch;

        const trigger = document.querySelector("#user-menu-button");
        trigger.focus();
        const pendingConfirm = window.PwedePaModal.confirm({
          title: "Confirm action?",
          slots: { message: "Check shared modal shell.", "confirm-label": "Proceed" },
          trigger,
        });
        const shell = document.getElementById("modal-shell");
        const modalOpen = shell.open && shell.dataset.suppressRing === "true";
        const cancelFocused = document.activeElement?.textContent?.trim() === "Cancel";
        shell.close("cancel");
        const modalResult = await pendingConfirm;
        const focusRestored = document.activeElement === trigger;

        const dummyBtn = document.createElement("button");
        document.body.appendChild(dummyBtn);
        let btnBusyDuring = false;
        await window.runButtonFetch(dummyBtn, async () => {
          btnBusyDuring =
            dummyBtn.disabled && dummyBtn.getAttribute("aria-busy") === "true";
        });
        const btnIdleAfter =
          !dummyBtn.disabled && dummyBtn.getAttribute("aria-busy") === "false";
        dummyBtn.remove();

        return {
          fetchCount,
          firstHeading,
          paintedBeforeAnswer,
          busyOnHit,
          modalOpen,
          cancelFocused,
          modalResult,
          focusRestored,
          btnBusyDuring,
          btnIdleAfter,
        };
      }"""
    )
    assert check["firstHeading"] == "Notifications"
    assert check["fetchCount"] == 2
    assert check["paintedBeforeAnswer"] is True
    assert check["busyOnHit"] is False
    assert check["modalOpen"] is True
    assert check["cancelFocused"] is True
    assert check["modalResult"] == "cancel"
    assert check["focusRestored"] is True
    assert check["btnBusyDuring"] is True
    assert check["btnIdleAfter"] is True
  finally:
    context.close()
