"""End to end: start the real server, then talk to it over a socket.

No test client and no in-process app. A separate process serves the pages. The
test reads them the way a browser does: a real port, a real cookie, real
redirects, and the database on disk.
"""

import http.client
import urllib.parse
import urllib.request

from conftest import fetch

from pwedepa.data import domains as domains_data


def test_the_server_answers_health_over_a_socket(served):
  status, _, body = fetch(f"{served['base']}/health")
  assert status == 200
  assert body.strip() == "ok"


def test_a_session_cookie_opens_the_workspace(served):
  status, url, body = fetch(f"{served['base']}/", cookie=served["cookie"])
  assert status == 200
  assert url.rstrip("/") == served["base"]
  assert "Workspace" in body


def test_a_created_request_reads_back_by_id(served):
  form = urllib.parse.urlencode(
    {"title": "E2E chairs", "description": "Two chairs", "visibility": "PRIVATE"}
  ).encode()
  status, url, _ = fetch(
    f"{served['base']}/requests", cookie=served["cookie"], data=form
  )
  assert status == 200
  assert "/requests/" in url
  status, _, body = fetch(url, cookie=served["cookie"])
  assert status == 200
  assert "E2E chairs" in body


def test_the_script_reaches_the_browser_through_the_server(served):
  """A page can render while its script never arrives with a usable type."""
  request = urllib.request.Request(f"{served['base']}/static/app.js")
  with urllib.request.urlopen(request, timeout=5) as answer:
    assert answer.status == 200
    assert "javascript" in answer.headers["Content-Type"]
    assert answer.read()


def test_a_missing_record_answers_a_styled_404(served):
  slug = domains_data.load(served["database"])[0].slug
  status, _, body = fetch(
    f"{served['base']}/{slug}/requests/9999", cookie=served["cookie"]
  )
  assert status == 404
  assert "404" in body


def test_a_signed_out_read_lands_on_the_login_page(served):
  status, url, _ = fetch(f"{served['base']}/requests")
  assert status == 200
  assert url.endswith("/login")


def test_a_kept_alive_connection_can_reload_a_page(served):
  """A browser reuses one connection for a page and its assets, and a refresh must hold."""
  connection = http.client.HTTPConnection("127.0.0.1", served["port"], timeout=10)
  try:
    for path in (
      "/health",
      "/static/app.css",
      "/static/tokens.css",
      "/static/app.js",
      "/static/icons/icon-static.png",
      "/settings",
    ):
      connection.request("GET", path)
      answer = connection.getresponse()
      answer.read()
      assert answer.status < 400, f"{path} answered {answer.status}"
  finally:
    connection.close()
