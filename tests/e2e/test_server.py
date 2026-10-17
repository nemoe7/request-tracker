"""End to end: start the real server, then talk to it over a socket.

No test client and no in-process app. A separate process serves the pages. The
test reads them the way a browser does: a real port, a real cookie, real
redirects, and the database on disk.
"""

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pwedepa.auth import Role, assign_role, sessions, users
from pwedepa.data import db as data_db

ROOT = Path(__file__).resolve().parents[2]
AT = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)
START_TIMEOUT = 20.0


def _free_port() -> int:
  with socket.socket() as probe:
    probe.bind(("127.0.0.1", 0))
    return probe.getsockname()[1]


def _fetch(url: str, *, cookie: str | None = None, data: bytes | None = None):
  """Return status, final URL, and body for one request, with redirects followed."""
  request = urllib.request.Request(url, data=data)
  if cookie:
    request.add_header("Cookie", cookie)
  try:
    with urllib.request.urlopen(request, timeout=5) as answer:
      return answer.status, answer.geturl(), answer.read().decode("utf-8", "replace")
  except urllib.error.HTTPError as error:
    return error.code, error.url, error.read().decode("utf-8", "replace")


@pytest.fixture(scope="module")
def served(tmp_path_factory):
  """Serve the app from a child process and hand back its address and a session."""
  database = tmp_path_factory.mktemp("e2e") / "app.db"
  connection = data_db.connect(str(database))
  admin = users.create_user(connection, "ada", "Ada Admin", at=AT)
  assign_role(connection, admin.id, Role.ADMIN, at=AT)
  token = sessions.create_session(connection, admin.id, at=AT).token
  connection.close()

  port = _free_port()
  environment = {
    **os.environ,
    "PWEDEPA_DB": str(database),
    "PWEDEPA_HOST": "127.0.0.1",
    "PWEDEPA_PORT": str(port),
    "PWEDEPA_ORIGIN": f"http://localhost:{port}",
    "PWEDEPA_SECRET_KEY": "e2e-secret",
    "PWEDEPA_COOKIE_SECURE": "0",
  }
  process = subprocess.Popen(
    [sys.executable, "-m", "pwedepa.web"],
    cwd=ROOT,
    env=environment,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
  )
  base = f"http://127.0.0.1:{port}"
  deadline = time.monotonic() + START_TIMEOUT
  while time.monotonic() < deadline:
    if process.poll() is not None:
      pytest.fail(
        f"the server exited with code {process.returncode} before it answered"
      )
    try:
      if _fetch(f"{base}/health")[0] == 200:
        break
    except (urllib.error.URLError, TimeoutError, ConnectionError):
      time.sleep(0.1)
  else:
    process.terminate()
    pytest.fail(
      f"the server did not answer on {base} within {START_TIMEOUT:.0f} seconds"
    )

  yield {"base": base, "cookie": f"pwedepa_session={token}"}
  process.terminate()
  process.wait(timeout=10)


def test_the_server_answers_health_over_a_socket(served):
  status, _, body = _fetch(f"{served['base']}/health")
  assert status == 200
  assert body.strip() == "ok"


def test_a_session_cookie_opens_the_workspace(served):
  status, url, body = _fetch(f"{served['base']}/workspace", cookie=served["cookie"])
  assert status == 200
  assert url.endswith("/workspace")
  assert "Workspace" in body


def test_a_created_request_reads_back_by_id(served):
  form = urllib.parse.urlencode(
    {"title": "E2E chairs", "description": "Two chairs", "visibility": "PRIVATE"}
  ).encode()
  status, url, _ = _fetch(
    f"{served['base']}/requests", cookie=served["cookie"], data=form
  )
  assert status == 200
  assert "/requests/" in url
  request_id = url.rstrip("/").rsplit("/", 1)[-1]
  status, _, body = _fetch(
    f"{served['base']}/requests/{request_id}", cookie=served["cookie"]
  )
  assert status == 200
  assert "E2E chairs" in body


def test_a_missing_record_answers_a_styled_404(served):
  status, _, body = _fetch(f"{served['base']}/requests/9999", cookie=served["cookie"])
  assert status == 404
  assert "404" in body


def test_a_signed_out_read_lands_on_the_login_page(served):
  status, url, body = _fetch(f"{served['base']}/requests")
  assert status == 200
  assert "login" in url or "Sign in" in body or "sign in" in body.lower()
