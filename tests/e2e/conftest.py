"""Shared setup for the end to end checks: one real server on one real port."""

import http.cookiejar
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
from pwedepa.core import Request, Visibility
from pwedepa.data import db as data_db
from pwedepa.data import domains as domains_data
from pwedepa.data import requests as requests_data

ROOT = Path(__file__).resolve().parents[2]
AT = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)
START_TIMEOUT = 20.0


def free_port() -> int:
  with socket.socket() as probe:
    probe.bind(("127.0.0.1", 0))
    return probe.getsockname()[1]


def fetch(url: str, *, cookie: str | None = None, data: bytes | None = None):
  """Return status, final URL, and body for one request, with redirects followed."""
  request = urllib.request.Request(url, data=data)
  if cookie:
    request.add_header("Cookie", cookie)
  try:
    with urllib.request.urlopen(request, timeout=5) as answer:
      return answer.status, answer.geturl(), answer.read().decode("utf-8", "replace")
  except urllib.error.HTTPError as error:
    return error.code, error.url, error.read().decode("utf-8", "replace")


def walk(base: str, cookie: str | None = None):
  """Return a guest or a signed-in caller that keeps its own cookies."""
  jar = http.cookiejar.CookieJar()
  opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
  if cookie:
    name, value = cookie.split("=", 1)
    jar.set_cookie(
      http.cookiejar.Cookie(
        version=0,
        name=name,
        value=value,
        port=None,
        port_specified=False,
        domain=urllib.parse.urlsplit(base).hostname,
        domain_specified=False,
        domain_initial_dot=False,
        path="/",
        path_specified=True,
        secure=False,
        expires=None,
        discard=True,
        comment=None,
        comment_url=None,
        rest={},
      )
    )

  def go(path: str, form: dict[str, str] | None = None):
    data = urllib.parse.urlencode(form).encode() if form is not None else None
    request = urllib.request.Request(f"{base}{path}", data=data)
    try:
      with opener.open(request, timeout=5) as answer:
        return (
          answer.status,
          answer.geturl().replace(base, ""),
          answer.read().decode("utf-8", "replace"),
        )
    except urllib.error.HTTPError as error:
      return (
        error.code,
        error.url.replace(base, ""),
        error.read().decode("utf-8", "replace"),
      )

  return go


@pytest.fixture(scope="session")
def served(tmp_path_factory):
  """Serve the app from a child process and hand back its address and sessions."""
  database = tmp_path_factory.mktemp("e2e") / "app.db"
  connection = data_db.connect(str(database))
  admin = users.create_user(connection, "ada", "Ada Admin", at=AT)
  assign_role(connection, admin.id, Role.ADMIN, at=AT)
  mara = users.create_user(connection, "mara", "Mara Requester", at=AT)
  assign_role(connection, mara.id, Role.REQUESTER, at=AT)
  requests_data.save(
    connection,
    Request(
      id=1,
      title="A lamp that blinks",
      description="It blinks twice, then goes dark.",
      requester_id=mara.id,
      visibility=Visibility.PRIVATE,
      created_at=AT,
      updated_at=AT,
      domains=(domains_data.load(str(database))[0].name,),
    ),
  )
  admin_token = sessions.create_session(connection, admin.id, at=AT).token
  mara_token = sessions.create_session(connection, mara.id, at=AT).token
  connection.close()

  port = free_port()
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
      if fetch(f"{base}/health")[0] == 200:
        break
    except (urllib.error.URLError, TimeoutError, ConnectionError):
      time.sleep(0.1)
  else:
    process.terminate()
    pytest.fail(
      f"the server did not answer on {base} within {START_TIMEOUT:.0f} seconds"
    )

  yield {
    "base": base,
    "port": port,
    "cookie": f"pwedepa_session={admin_token}",
    "requester_cookie": f"pwedepa_session={mara_token}",
    "database": database,
  }
  process.terminate()
  process.wait(timeout=10)
