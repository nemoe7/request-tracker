import re
from datetime import UTC, datetime, timedelta

import pytest
from _paths import record_url

from pwedepa.auth import Role, assign_role, sessions, users
from pwedepa.core import Issue, IssueStatus, Priority, Request, Visibility
from pwedepa.data import db as data_db
from pwedepa.data import events as events_data
from pwedepa.data import issues as issues_data
from pwedepa.data import notifications as notifications_data
from pwedepa.data import preferences as preferences_data
from pwedepa.data import requests as requests_data
from pwedepa.data import sharing as sharing_data
from pwedepa.data import site as site_data
from pwedepa.web import SESSION_COOKIE, create_app

AT = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)


@pytest.fixture
def app(tmp_path):
  return create_app(
    {
      "DATABASE": str(tmp_path / "test.db"),
      "WEBAUTHN_RP_ID": "example.com",
      "WEBAUTHN_RP_NAME": "PwedePa",
      "WEBAUTHN_ORIGIN": "https://example.com",
      "SESSION_COOKIE_SECURE": True,
    }
  )


@pytest.fixture
def db(app):
  connection = data_db.connect(app.config["DATABASE"])
  yield connection
  connection.close()


def _client(app, db, name, display, roles=()):
  person = users.create_user(db, name, display, at=AT)
  for role in roles:
    assign_role(db, person.id, role, at=AT)
  token = sessions.create_session(db, person.id, at=AT).token
  client = app.test_client()
  client.set_cookie(SESSION_COOKIE, token)
  return client, person


@pytest.fixture
def cast(app, db):
  admin, admin_user = _client(app, db, "admin", "Ada Admin", roles=(Role.ADMIN,))
  Mara, Mara_user = _client(app, db, "Mara", "Mara Reyes", roles=(Role.REQUESTER,))
  Sam, Sam_user = _client(app, db, "Sam", "Sam Cruz", roles=(Role.ASSIGNEE,))
  return {
    "admin": (admin, admin_user),
    "Mara": (Mara, Mara_user),
    "Sam": (Sam, Sam_user),
  }


def _request(db, requester_id):
  record = Request(
    id=1,
    title="Broken projector",
    description="The projector in Room 4 is dead.",
    requester_id=requester_id,
    created_at=AT,
    updated_at=AT,
  )
  requests_data.save(db, record)
  return record


def _share_token(client, object_type="request", object_id=1, permission="VIEW"):
  client.post(
    f"/records/{object_type}/{object_id}/share", data={"permission": permission}
  )
  detail = client.get(record_url(object_id, f"{object_type}s"))
  match = re.search(rb"/share/([A-Za-z0-9_-]+)", detail.data)
  assert match is not None
  return match.group(1).decode()


def test_share_token_is_hashed_and_anonymous_view_is_one_time(app, cast, db):
  Mara, Mara_user = cast["Mara"]
  _request(db, Mara_user.id)
  token = _share_token(Mara)
  link = sharing_data.find_by_token(db, token)
  assert link is not None
  assert link.permissions == ("VIEW",)
  row = db.exec_driver_sql("SELECT token_hash FROM share_links WHERE id = 1").fetchone()
  assert token not in row._mapping["token_hash"]

  anonymous = app.test_client()
  notice = anonymous.get(f"/share/{token}")
  assert notice.status_code == 200
  assert f'action="/share/{token}/view"'.encode() in notice.data
  opened = anonymous.post(f"/share/{token}/view")
  assert "/shared/1" in opened.headers["Location"]
  page = anonymous.get("/shared/1")
  assert page.status_code == 200
  assert b"Broken projector" in page.data
  assert b'class="issue-layout"' in page.data, "the share page keeps the record shape"
  assert anonymous.get("/shared/1").status_code == 404
  assert anonymous.get(f"/share/{token}").status_code == 410


def test_authenticated_share_grants_only_the_picked_access(cast, db):
  Mara, Mara_user = cast["Mara"]
  Sam, _ = cast["Sam"]
  admin, _ = cast["admin"]
  _request(db, Mara_user.id)
  token = _share_token(Mara, permission="COMMENT")

  opened = Sam.get(f"/share/{token}")
  assert record_url(1) in opened.headers["Location"]
  assert Sam.get(record_url(1)).status_code == 200
  Sam.post("/requests/1/comment", data={"text": "I can check it Friday."})
  comment = next(
    event
    for event in events_data.list_for(db, "request", 1)
    if event.event_type == "request.comment"
  )
  assert comment.data["text"].encode() in Mara.get(record_url(1)).data

  Sam.post("/requests/1/transition", data={"target": "PENDING"})
  assert requests_data.get(db, 1).status.value == "OPEN"
  Sam.post(
    "/requests/1/edit",
    data={
      "title": "Changed by Sam",
      "description": "Nope.",
      "domains": "",
      "visibility": "PRIVATE",
      "priority_suggestion": "",
    },
  )
  assert requests_data.get(db, 1).title == "Broken projector"

  edit_token = _share_token(Mara, permission="EDIT")
  Sam.get(f"/share/{edit_token}")
  Sam.post(
    "/requests/1/edit",
    data={
      "title": "Changed by Sam",
      "description": "Nope.",
      "domains": "",
      "visibility": "PRIVATE",
      "priority_suggestion": "",
    },
  )
  assert requests_data.get(db, 1).title == "Changed by Sam"

  admin.post("/share-links/2/revoke", data={"reason": "The link leaked."})
  assert Sam.get(record_url(1)).status_code == 404
  assert Sam.get(f"/share/{edit_token}").status_code == 404
  revoked = next(
    event
    for event in events_data.list_for(db, "request", 1)
    if event.event_type == "request.share_revoked"
  )
  assert revoked.data["reason"] == "The link leaked."


def _demo_app(tmp_path, name: str = "demo.db", switch: bool = False):
  return create_app(
    {
      "DATABASE": str(tmp_path / name),
      "WEBAUTHN_RP_ID": "example.com",
      "WEBAUTHN_RP_NAME": "PwedePa",
      "WEBAUTHN_ORIGIN": "https://example.com",
      "SESSION_COOKIE_SECURE": False,
      "DEMO_MODE": True,
      "DEMO_SWITCH": switch,
    }
  )


def test_demo_mode_opens_seeded_workspace_without_credentials(tmp_path):
  client = _demo_app(tmp_path).test_client()
  workspace = client.get("/")
  assert workspace.status_code == 200
  assert re.search(rb'href="/\?[^"]*selected=\d+"', workspace.data)


def test_the_demo_entry_is_not_a_url(cast, tmp_path):
  admin, _ = cast["admin"]
  assert admin.get("/demo").status_code == 404
  assert admin.get("/demo/switch/client").status_code == 404
  demo = _demo_app(tmp_path, "demo-url.db").test_client()
  assert demo.get("/demo").status_code == 404
  assert demo.get("/demo/switch/staff").status_code == 404


def test_the_demo_seat_swaps_in_code(tmp_path):
  from pwedepa.web.routes.demo import set_seat

  client = _demo_app(tmp_path, "demo-seat.db").test_client()
  assert client.get("/").status_code == 200
  assert client.get("/login").headers["Location"].endswith("/")
  assert client.get("/enroll").headers["Location"].endswith("/")
  assert client.get("/home").headers["Location"].endswith("/")
  set_seat("client")
  try:
    assert "/requests" in client.get("/").headers["Location"]
  finally:
    set_seat("staff")


def test_the_demo_switch_shows_only_when_the_build_asks(tmp_path):
  """The live preview holds one seat, so only the frozen build shows the switch."""
  live = _demo_app(tmp_path, "demo-live.db").test_client()
  home = live.get("/").get_data(as_text=True)
  assert "demo-switch" not in home, "one seat needs no switch"
  frozen = _demo_app(tmp_path, "demo-frozen.db", switch=True).test_client()
  page = frozen.get("/").get_data(as_text=True)
  assert re.search(r'<a href="/" class="on">Staff</a>', page)
  assert re.search(r'<a href="/home">Client</a>', page)


def test_the_environment_cannot_open_the_demo(monkeypatch, tmp_path):
  monkeypatch.setenv("PWEDEPA_DEMO", "1")
  client = create_app(
    {
      "DATABASE": str(tmp_path / "env.db"),
      "WEBAUTHN_RP_ID": "example.com",
      "WEBAUTHN_RP_NAME": "PwedePa",
      "WEBAUTHN_ORIGIN": "https://example.com",
      "SESSION_COOKIE_SECURE": False,
    }
  ).test_client()
  root = client.get("/")
  assert root.status_code == 302
  assert root.headers["Location"].endswith("/login")
  page = client.get("/login")
  assert page.status_code == 200
  assert b"demo-switch" not in page.data


def test_notifications_and_preferences(cast, db):
  admin, _ = cast["admin"]
  Mara, Mara_user = cast["Mara"]
  _request(db, Mara_user.id)
  admin.post("/requests/1/transition", data={"target": "PENDING"})
  inbox = Mara.get("/notifications")
  assert requests_data.get(db, 1).title.encode() in inbox.data
  assert notifications_data.count_for_user(db, Mara_user.id) == 1

  Mara.post(
    "/settings/notifications",
    data={"activity_enabled": "on", "activity_pip": "on"},
  )
  admin.post("/requests/1/comment", data={"text": "Any news?"})
  messages = [
    notice.message for notice in notifications_data.list_for_user(db, Mara_user.id)
  ]
  assert not any("comment" in message.lower() for message in messages)


def test_notification_dismiss_and_clear(app, cast, db):
  admin, _ = cast["admin"]
  Mara, Mara_user = cast["Mara"]
  Sam, _ = cast["Sam"]
  _request(db, Mara_user.id)
  admin.post("/requests/1/transition", data={"target": "PENDING"})
  admin.post("/requests/1/comment", data={"text": "Any news?"})
  assert notifications_data.count_for_user(db, Mara_user.id) == 2
  notices = notifications_data.list_for_user(db, Mara_user.id)

  Sam.post(f"/notifications/{notices[0].id}/dismiss")
  assert notifications_data.count_for_user(db, Mara_user.id) == 2

  Mara.post(f"/notifications/{notices[0].id}/dismiss")
  remaining = notifications_data.list_for_user(db, Mara_user.id)
  assert [notice.id for notice in remaining] == [notices[1].id]

  inbox = Mara.get("/notifications")
  assert b'action="/notifications/clear"' in inbox.data
  assert f'action="/notifications/{notices[1].id}/dismiss"'.encode() in inbox.data

  Mara.post("/notifications/clear")
  assert notifications_data.count_for_user(db, Mara_user.id) == 0
  assert b'action="/notifications/clear"' not in Mara.get("/notifications").data

  anonymous = app.test_client()
  assert anonymous.post("/notifications/clear").status_code == 302
  assert anonymous.post("/notifications/1/dismiss").status_code == 302


def test_header_nav_keeps_the_client_tabs(cast, db):
  """Staff hold no top tabs. The brand leads back to the workspace."""
  admin, _ = cast["admin"]
  Mara, _ = cast["Mara"]
  staff_page = admin.get("/").data
  assert b'<nav class="tabs"' not in staff_page
  assert b'<a class="brand" href="/">' in staff_page
  client_page = Mara.get("/requests").data
  client_nav = re.search(rb'<nav class="tabs".*?</nav>', client_page, re.DOTALL).group(
    0
  )
  assert b'href="/requests"' in client_nav
  assert b'href="/issues"' in client_nav
  assert b'href="/"' not in client_nav


def test_clock_preference_and_stamp_rendering(cast, db):
  Mara, Mara_user = cast["Mara"]
  assert preferences_data.get_clock(db, Mara_user.id) == "12"
  old = (datetime.now(UTC) - timedelta(days=4)).replace(
    hour=13, minute=5, second=0, microsecond=0
  )
  notifications_data.notify(db, Mara_user.id, "activity", "Old notice", at=old)
  notifications_data.notify(
    db, Mara_user.id, "activity", "Fresh notice", at=datetime.now(UTC)
  )
  inbox = Mara.get("/notifications")
  assert inbox.get_data(as_text=True).count('class="event-meta"') == 2

  Mara.post("/settings/clock", data={"clock": "24"})
  assert preferences_data.get_clock(db, Mara_user.id) == "24"
  assert b"13:05" in Mara.get("/notifications").data

  Mara.post("/settings/clock", data={"clock": "13"})
  assert preferences_data.get_clock(db, Mara_user.id) == "24"
  assert b'name="clock"' in Mara.get("/settings").data


def test_theme_preference_is_saved_on_the_account(cast, db):
  Mara, Mara_user = cast["Mara"]
  page = Mara.get("/settings")
  assert b'data-theme="system"' in page.data
  assert b'data-theme-scope="account"' in page.data
  assert preferences_data.get_theme(db, Mara_user.id) == "system"

  Mara.post("/settings/theme", data={"theme": "dark"})
  assert preferences_data.get_theme(db, Mara_user.id) == "dark"
  assert b'data-theme="dark"' in Mara.get("/settings").data

  Mara.post("/settings/theme", data={"theme": "neon"})
  assert preferences_data.get_theme(db, Mara_user.id) == "dark"


def test_settings_profile_and_admin_pages(cast, db):
  admin, _ = cast["admin"]
  Mara, Mara_user = cast["Mara"]
  Sam, _ = cast["Sam"]
  assert Sam.get("/admin").status_code == 403

  Mara.post("/settings/profile", data={"display_name": "Mara R."})
  saved_name = users.get_user(db, Mara_user.id).display_name
  assert saved_name == "Mara R."
  assert saved_name.encode() in Mara.get("/settings").data

  admin.post("/admin/tokens", data={"role": "REQUESTER"})
  users_page = admin.get("/admin/users")
  assert b'id="issued-token"' in users_page.data
  admin.post(f"/admin/users/{Mara_user.id}/archive")
  assert users.get_user(db, Mara_user.id).status.value == "ARCHIVED"
  admin.post(f"/admin/users/{Mara_user.id}/reactivate")
  assert users.get_user(db, Mara_user.id).status.value == "ACTIVE"
  assert b"Enrollment token issued" in admin.get("/admin/audit").data


def test_every_admin_route_stands_behind_the_gate(app, cast, db):
  """A route that misses the guard would answer a stranger with admin data."""
  Sam, _ = cast["Sam"]
  bind = app.url_map.bind("example.com")
  routes = sorted(
    {
      (bind.build(rule.endpoint, {name: 1 for name in rule.arguments}), method)
      for rule in app.url_map.iter_rules()
      if rule.endpoint.startswith("admin.")
      for method in rule.methods - {"HEAD", "OPTIONS"}
    }
  )
  assert len({path for path, _ in routes}) >= 10, routes
  anonymous = app.test_client()
  for path, method in routes:
    answer = getattr(anonymous, method.lower())(path)
    assert answer.status_code == 302, (method, path, answer.status_code)
    assert "/login" in answer.headers["Location"], (method, path)
    answer = getattr(Sam, method.lower())(path)
    assert answer.status_code == 403, (method, path, answer.status_code)


def test_admin_site_message_and_direct_issue(app, cast, db):
  admin, _ = cast["admin"]
  _, Sam_user = cast["Sam"]
  admin.post(
    "/admin/site-message", data={"message": "Demo day is Friday.", "enabled": "on"}
  )
  anonymous = app.test_client()
  saved = site_data.list_messages(db)[0]
  assert saved.message.encode() in anonymous.get("/login").data

  response = admin.post(
    "/admin/issues",
    data={
      "title": "Direct repair",
      "description": "Created by an admin.",
      "assignee_id": str(Sam_user.id),
      "priority": "LOW",
      "visibility": "PRIVATE",
      "domains": "Facilities",
    },
  )
  assert record_url(1, "issues") in response.headers["Location"]
  issue = issues_data.get(db, 1)
  assert issue.status is IssueStatus.OPEN
  assert issue.priority is Priority.LOW
  assert issue.assignee_id == Sam_user.id


def test_the_share_rule_answers_the_page_and_the_endpoint(app, cast, db):
  """One rule decides both, so the panel hides wherever the endpoint refuses."""
  Mara, Mara_user = cast["Mara"]
  Sam, _sam_user = cast["Sam"]
  requests_data.save(
    db,
    Request(
      id=1,
      title="Broken projector",
      description="Room 4",
      requester_id=Mara_user.id,
      visibility=Visibility.PUBLIC,
      created_at=AT,
      updated_at=AT,
    ),
  )
  issues_data.save(
    db,
    Issue(
      id=1,
      title="Dead cable",
      description="Room 4",
      requester_id=Mara_user.id,
      visibility=Visibility.PUBLIC,
    ),
  )

  assert b"share-panel" in Mara.get(record_url(1)).data
  assert b"share-panel" in Mara.get(record_url(1, "issues")).data
  assert (
    Sam.post("/records/request/1/share", data={"permission": "VIEW"}).status_code == 404
  )
  assert (
    Sam.post("/records/issue/1/share", data={"permission": "VIEW"}).status_code == 404
  )
  assert b"share-panel" not in Sam.get(record_url(1)).data
  assert b"share-panel" not in Sam.get(record_url(1, "issues")).data


def test_a_share_expiry_reads_a_number_the_field_allows(cast, db):
  """A number field submits exponent forms, so the route must read them."""
  from pwedepa.data import sharing as sharing_data

  Mara, Mara_user = cast["Mara"]
  _request(db, Mara_user.id)

  exponent = Mara.post(
    "/records/request/1/share", data={"permission": "VIEW", "expires_days": "1e3"}
  )
  assert exponent.status_code == 302
  link = sharing_data.list_for_object(db, "request", 1)[-1]
  assert link.expires_at is not None
  assert link.expires_at > AT
  assert link.expires_at <= AT.replace(year=AT.year + 10)

  junk = Mara.post(
    "/records/request/1/share", data={"permission": "VIEW", "expires_days": "soon"}
  )
  assert junk.status_code == 302
  newest = sharing_data.list_for_object(db, "request", 1)[-1]
  assert newest.expires_at is None


def test_a_share_expiry_is_clamped(cast, db):
  """A wild number cannot overflow the clock or ship a dead link."""
  from pwedepa.data import sharing as sharing_data

  Mara, Mara_user = cast["Mara"]
  _request(db, Mara_user.id)

  huge = Mara.post(
    "/records/request/1/share", data={"permission": "VIEW", "expires_days": "99999999"}
  )
  assert huge.status_code == 302
  farthest = sharing_data.list_for_object(db, "request", 1)[-1]
  assert farthest.expires_at is not None
  assert farthest.expires_at <= AT.replace(year=AT.year + 10)

  past = Mara.post(
    "/records/request/1/share", data={"permission": "VIEW", "expires_days": "-5"}
  )
  assert past.status_code == 302
  newest = sharing_data.list_for_object(db, "request", 1)[-1]
  assert newest.expires_at > AT


def test_a_staff_member_can_check_the_client_view(cast, db):
  """The toggle drops the staff controls and refuses every item write."""
  admin, admin_user = cast["admin"]
  _request(db, cast["Mara"][1].id)

  entered = admin.get("/view-as/client")
  assert entered.status_code == 302
  assert entered.headers["Location"].endswith("/requests")

  detail = admin.get(record_url(1))
  assert detail.status_code == 200
  assert b'aria-label="Edit"' not in detail.data
  assert b"share-form" not in detail.data
  assert b'href="/view-as/client"' not in detail.data
  assert b'href="/view-as/staff"' in detail.data
  assert b'id="client-view"' in admin.get("/settings").data

  queue = admin.get("/")
  assert queue.status_code == 302
  assert "/requests" in queue.headers["Location"]

  refused = admin.post("/requests/1/transition", data={"target": "OPEN"})
  assert refused.status_code == 403

  saved = admin.post("/settings/theme", data={"theme": "dark"})
  assert saved.status_code == 204
  assert preferences_data.get_theme(db, admin_user.id) == "dark"
  assert admin.post("/auth/passkeys/999/revoke").status_code == 404


def test_the_staff_view_keeps_its_controls(cast, db):
  """Leaving the client view hands the staff controls back."""
  admin, _ = cast["admin"]
  _request(db, cast["Mara"][1].id)

  admin.get("/view-as/client")
  left = admin.get("/view-as/staff")
  assert left.status_code == 302
  assert left.headers["Location"].endswith("/")

  detail = admin.get(record_url(1))
  assert b'href="/requests/1/edit"' in detail.data
  assert b'id="client-view"' in admin.get("/settings").data
  assert admin.get("/").status_code == 200


def test_a_client_cannot_turn_on_the_client_view(cast):
  """The toggle belongs to the staff seat, so a client has no such page."""
  Mara, _ = cast["Mara"]
  assert Mara.get("/view-as/client").status_code == 404


def test_a_staff_member_can_sign_out_from_the_client_view(cast):
  """The read-only guard must not trap a person in the mode."""
  admin, _ = cast["admin"]
  admin.get("/view-as/client")

  signed_out = admin.post("/logout")
  assert signed_out.status_code == 200
  with admin.session_transaction() as flask_session:
    assert "view_as" not in flask_session


def _function_body(script: str, name: str) -> str:
  """Return one function's text, with its braces matched."""
  start = script.index(f"function {name}(")
  depth = 0
  for index in range(script.index("{", start), len(script)):
    depth += {"{": 1, "}": -1}.get(script[index], 0)
    if depth == 0:
      return script[start:index]
  raise AssertionError(f"{name} has no closing brace")


def test_every_settings_control_saves_itself(cast, db):
  """One save model per view: each control writes, and no Save row waits."""
  Mara = cast["Mara"][0]
  main = Mara.get("/settings").data.decode()
  main = main[main.index("settings-main") :]
  profile = main[main.index('action="/settings/profile"') :]
  profile = profile[: profile.index("</form>")]
  assert "data-auto-submit" in profile, "a changed name sends the form"
  assert "data-save" in profile, "a bare browser keeps one way to save the name"
  size = main[main.index('action="/settings/font-size"') :]
  assert "data-save" in size[: size.index("</form>")], (
    "a bare browser keeps one way to save the size"
  )
  script = Mara.get("/static/app.js").data.decode()
  assert 'fontForm.classList.add("is-auto")' in script, (
    "the script hides the row only after it saves the size"
  )
  assert 'form[data-auto-submit]")' in script

  Mara.post("/settings/profile", data={"display_name": "Mara R."})
  assert Mara.get("/settings").data.count(b"Mara R.") >= 1


def test_a_taken_username_is_refused(cast, db):
  """A taken name blocks the write, and the case does not matter."""
  Mara, Mara_user = cast["Mara"]

  answer = Mara.post(
    "/settings/username", data={"username": "SAM"}, follow_redirects=True
  )

  body = answer.data.decode()
  assert "already in use" in body
  assert users.get_user(db, Mara_user.id).username == "Mara"
  assert (
    'id="change-username"' in body
    and "hidden" not in body.split('id="change-username"')[1].split(">")[0]
  ), "a refused name keeps the modal open"
  assert 'role="alert"' in body, "the refusal shows inside the modal"
  assert body.index('role="alert"') > body.index('id="change-username"')

  saved = Mara.post(
    "/settings/username", data={"username": "mara-r"}, follow_redirects=True
  )
  assert b"Username saved." in saved.data
  assert users.get_user(db, Mara_user.id).username == "mara-r"


def test_the_username_change_opens_from_a_modal(cast):
  Mara, _ = cast["Mara"]
  main = Mara.get("/settings").data.decode()
  main = main[main.index("settings-main") :]
  assert 'data-modal-open="change-username"' in main
  assert 'id="change-username"' in main
  assert 'action="/settings/username"' in main
  assert main.index("</form>") < main.index('id="change-username"'), (
    "the modal form must not nest in the profile form"
  )
  modal = main[main.index('id="change-username"') :]
  form = modal[modal.index('class="modal-form"') : modal.index("</form>")]
  assert 'class="field"' not in form, "the modal holds one card, not a card inside"
  assert 'class="ios-input"' not in form, "the row input style drops the box"


def test_notification_switches_save_as_they_flip(cast, db):
  Mara, Mara_user = cast["Mara"]
  main = Mara.get("/settings").data.decode()
  main = main[main.index("settings-main") :]
  assert 'aria-label="Save notifications"' in main, "a bare browser needs a way out"
  assert "data-save" in main
  css = Mara.get("/static/app.css").data.decode()
  assert "form.is-auto [data-save] { display: none; }" in css, (
    "the script hides the button only after it takes the switches over"
  )
  script = Mara.get("/static/app.js").data.decode()
  assert 'document.querySelectorAll("form[data-autosave]")' in script
  assert "form[data-autosave]" not in _function_body(script, "setTheme"), (
    "the switch handler binds at load, not after a theme click"
  )

  answer = Mara.post(
    "/settings/notifications",
    data={"activity_enabled": "on", "comments_inbox": "on"},
    headers={"X-Autosave": "1"},
  )
  assert answer.status_code == 204
  saved = {
    pref.category: pref for pref in notifications_data.preferences(db, Mara_user.id)
  }
  assert saved["activity"].enabled is True
  assert saved["comments"].inbox_enabled is True
  assert saved["sharing"].enabled is False


def test_settings_has_no_shortcut_to_notifications(cast, db):
  Mara, _ = cast["Mara"]
  main = Mara.get("/settings").data.decode()
  main = main[main.index("settings-main") :]
  assert 'href="/notifications"' not in main


def test_the_frozen_demo_keeps_the_save_button(tmp_path):
  """The demo has no server. A switch there must not claim a save."""
  body = _demo_app(tmp_path).test_client().get("/settings").data
  main = body[body.index(b"settings-main") :]
  assert b"data-autosave action" not in main
  assert b"Save notifications" in main, "the control still names its action"
