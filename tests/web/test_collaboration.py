import re
from datetime import UTC, datetime

import pytest

from pwedepa.auth import Role, assign_role, sessions, users
from pwedepa.core import IssueStatus, Priority, Request
from pwedepa.data import db as data_db
from pwedepa.data import issues as issues_data
from pwedepa.data import notifications as notifications_data
from pwedepa.data import requests as requests_data
from pwedepa.data import sharing as sharing_data
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
  detail = client.get(f"/{object_type}s/{object_id}")
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
  assert b"one signed-out view" in notice.data.lower()
  opened = anonymous.post(f"/share/{token}/view")
  assert "/shared/1" in opened.headers["Location"]
  page = anonymous.get("/shared/1")
  assert page.status_code == 200
  assert b"Broken projector" in page.data
  assert anonymous.get("/shared/1").status_code == 404
  assert anonymous.get(f"/share/{token}").status_code == 410


def test_authenticated_share_grants_only_the_picked_access(cast, db):
  Mara, Mara_user = cast["Mara"]
  Sam, _ = cast["Sam"]
  admin, _ = cast["admin"]
  _request(db, Mara_user.id)
  token = _share_token(Mara, permission="COMMENT")

  opened = Sam.get(f"/share/{token}")
  assert "/requests/1" in opened.headers["Location"]
  assert Sam.get("/requests/1").status_code == 200
  Sam.post("/requests/1/comment", data={"text": "I can check it Friday."})
  assert b"I can check it Friday." in Mara.get("/requests/1").data

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

  admin.post("/share-links/2/revoke")
  assert Sam.get("/requests/1").status_code == 404
  assert Sam.get(f"/share/{edit_token}").status_code == 404


def test_demo_mode_opens_seeded_workspace_without_credentials(tmp_path):
  demo_app = create_app(
    {
      "DATABASE": str(tmp_path / "demo.db"),
      "WEBAUTHN_RP_ID": "example.com",
      "WEBAUTHN_RP_NAME": "PwedePa",
      "WEBAUTHN_ORIGIN": "https://example.com",
      "SESSION_COOKIE_SECURE": False,
      "DEMO_MODE": True,
    }
  )
  client = demo_app.test_client()
  assert "/workspace" in client.get("/").headers["Location"]
  opened = client.get("/demo")
  assert opened.status_code == 302
  assert "/workspace" in opened.headers["Location"]
  workspace = client.get("/workspace")
  assert workspace.status_code == 200
  assert b"Broken projector in Room 4" in workspace.data


def test_demo_route_stays_off_by_default(cast):
  admin, _ = cast["admin"]
  assert admin.get("/demo").status_code == 404
  assert admin.get("/demo/switch/client").status_code == 404


def test_demo_switch_swaps_between_staff_and_client(tmp_path):
  demo_app = create_app(
    {
      "DATABASE": str(tmp_path / "demo2.db"),
      "WEBAUTHN_RP_ID": "example.com",
      "WEBAUTHN_RP_NAME": "PwedePa",
      "WEBAUTHN_ORIGIN": "https://example.com",
      "SESSION_COOKIE_SECURE": False,
      "DEMO_MODE": True,
    }
  )
  client = demo_app.test_client()
  landing = client.get("/")
  assert b"Sign in with a passkey" not in landing.data
  assert "/workspace" in landing.headers["Location"]
  assert "/demo" in client.get("/login").headers["Location"]
  assert "/demo" in client.get("/enroll").headers["Location"]
  assert client.get("/workspace").status_code == 200
  assert client.get("/demo").status_code == 302
  assert client.get("/workspace").status_code == 200
  assert client.get("/demo/switch/client").status_code == 302
  home = client.get("/home")
  assert home.status_code == 200
  assert b"Staff" in home.data and b"Client" in home.data
  assert client.get("/demo/switch/staff").status_code == 302
  assert client.get("/workspace").status_code == 200


def test_notifications_and_preferences(cast, db):
  admin, _ = cast["admin"]
  Mara, Mara_user = cast["Mara"]
  _request(db, Mara_user.id)
  admin.post("/requests/1/transition", data={"target": "PENDING"})
  inbox = Mara.get("/notifications")
  assert b"Broken projector" in inbox.data
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
  assert b"No notifications yet." in Mara.get("/notifications").data

  anonymous = app.test_client()
  assert anonymous.post("/notifications/clear").status_code == 302
  assert anonymous.post("/notifications/1/dismiss").status_code == 302


def test_settings_profile_and_admin_pages(cast, db):
  admin, _ = cast["admin"]
  Mara, Mara_user = cast["Mara"]
  Sam, _ = cast["Sam"]
  assert Sam.get("/admin").status_code == 403

  Mara.post("/settings/profile", data={"display_name": "Mara R."})
  assert users.get_user(db, Mara_user.id).display_name == "Mara R."
  assert b"Mara R." in Mara.get("/settings").data

  admin.post(
    "/admin/users",
    data={"username": "Lee", "display_name": "Lee Park", "role": "REQUESTER"},
  )
  lee = users.get_user_by_username(db, "Lee")
  assert lee is not None
  admin.post(f"/admin/users/{lee.id}/enrollment-token")
  users_page = admin.get("/admin/users")
  assert b"Copy this enrollment token now" in users_page.data
  admin.post(f"/admin/users/{lee.id}/archive")
  assert users.get_user(db, lee.id).status.value == "ARCHIVED"
  admin.post(f"/admin/users/{lee.id}/reactivate")
  assert users.get_user(db, lee.id).status.value == "ACTIVE"
  assert b"user.created" in admin.get("/admin/audit").data


def test_admin_site_message_and_direct_issue(app, cast, db):
  admin, _ = cast["admin"]
  _, Sam_user = cast["Sam"]
  admin.post(
    "/admin/site-message", data={"message": "Demo day is Friday.", "enabled": "on"}
  )
  anonymous = app.test_client()
  assert b"Demo day is Friday." in anonymous.get("/").data

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
  assert "/issues/1" in response.headers["Location"]
  issue = issues_data.get(db, 1)
  assert issue.status is IssueStatus.OPEN
  assert issue.priority is Priority.LOW
  assert issue.assignee_id == Sam_user.id
