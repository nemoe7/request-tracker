"""End to end: start the real server, then talk to it over a socket.

No test client and no in-process app. A separate process serves the pages. The
test reads them the way a browser does: a real port, a real cookie, real
redirects, and the database on disk.
"""

import http.client
import re
import urllib.parse
import urllib.request

from conftest import fetch, walk

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


def test_a_share_link_spends_one_view_and_then_reads_gone(served):
  """A guest reads the record once, and the second visit answers gone."""
  requester = walk(served["base"], served["requester_cookie"])
  status, url, body = requester("/records/request/1/share", {"permission": "VIEW"})
  assert status == 200
  assert url == "/3d-print-model/requests/1"
  found = re.search(r'value="(http[^"]+/share/[^"]+)"', body)
  assert found, "the page shows the link once"
  link = found.group(1).replace(served["base"], "")

  guest = walk(served["base"])
  status, _, body = guest(link)
  assert status == 200
  assert f'action="{link}/view"' in body

  status, url, body = guest(link + "/view", {})
  assert status == 200
  assert url == "/shared/1"
  assert "A lamp that blinks" in body

  status, _, body = guest(link)
  assert status == 410
  assert f'action="{link}/view"' not in body
  assert 'class="panel empty-state"' in body


def test_a_non_admin_cannot_change_a_role_and_an_admin_can(served):
  """The role guard answers across the wire, and a real write reads back."""
  mara = walk(served["base"], served["requester_cookie"])
  status, _, _ = mara("/admin/users/1/roles", {"role": "ADMIN", "user_id": "1"})
  assert status == 403

  admin = walk(served["base"], served["cookie"])
  status, url, _ = admin("/admin/users/2/roles", {"role": "ASSIGNEE"})
  assert status == 200
  assert url == "/admin/users"
  status, _, body = admin("/admin/users")
  assert "Assignee" in body


def test_a_settings_write_reads_back_on_the_settings_page(served):
  """A fetch write answers 204, and the next page read shows the new value."""
  mara = walk(served["base"], served["requester_cookie"])
  status, _, _ = mara("/settings/clock", {"clock": "24"})
  assert status == 200
  status, _, body = mara("/settings")
  assert status == 200
  assert 'value="24"' in body
  assert "is-active" in body
