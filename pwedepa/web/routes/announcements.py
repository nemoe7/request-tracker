"""Domain announcements: staff write them, everyone signed in reads them."""

from flask import (
  Blueprint,
  abort,
  current_app,
  flash,
  redirect,
  render_template,
  request,
  url_for,
)
from werkzeug.wrappers import Response

from pwedepa.auth.audit import record_audit
from pwedepa.data import announcements as announcements_data
from pwedepa.data import domains as domains_data
from pwedepa.data import notifications as notifications_data
from pwedepa.data import subscriptions

from .. import now
from ._helpers import current_user, db
from .records import is_staff

bp = Blueprint("announcements", __name__)


def _domain(slug: str):
  found = domains_data.find(slug, current_app.config["DATABASE"])
  if found is None:
    abort(404)
  return found


def _staff_user():
  """Return the signed-in staff user, or None. A client gets a 403."""
  user = current_user()
  if user is None:
    return None
  if not is_staff(user):
    abort(403)
  return user


def _submitted() -> tuple[str, str]:
  return request.form.get("title", "").strip(), request.form.get("body", "").strip()


def _find(domain, announcement_id: int):
  """Return one announcement of this Domain, or answer 404."""
  found = announcements_data.get(db(), announcement_id)
  if found is None or found.slug != domain.slug:
    abort(404)
  return found


@bp.get("/<slug>/announcements/new")
def new(slug: str) -> str | Response:
  domain = _domain(slug)
  user = _staff_user()
  if user is None:
    return redirect(url_for("pages.login"))
  return render_template(
    "announcement_form.jinja",
    domain=domain,
    announcement=None,
    action=url_for("announcements.create", slug=domain.slug),
    values={"title": "", "body": ""},
  )


@bp.post("/<slug>/announcements")
def create(slug: str) -> str | Response:
  domain = _domain(slug)
  user = _staff_user()
  if user is None:
    return redirect(url_for("pages.login"))
  title, body = _submitted()
  if not title or not body:
    flash("An announcement needs a title and a body.")
    return render_template(
      "announcement_form.jinja",
      domain=domain,
      announcement=None,
      action=url_for("announcements.create", slug=domain.slug),
      values={"title": title, "body": body},
    )
  at = now()
  created = announcements_data.create(
    db(), slug=domain.slug, title=title, body=body, author_id=user.id, at=at
  )
  for subscriber in subscriptions.subscribers(db(), domain.slug):
    if subscriber == user.id:
      continue
    notifications_data.notify(
      db(),
      subscriber,
      "activity",
      f'{user.display_name} posted "{title}" in {domain.name}',
      at=at,
      object_type="announcement",
      object_id=created.id,
      actor_id=user.id,
    )
  flash("Announcement published.")
  return redirect(url_for("records.domain_page", slug=domain.slug))


@bp.get("/<slug>/announcements/<int:announcement_id>/edit")
def edit(slug: str, announcement_id: int) -> str | Response:
  domain = _domain(slug)
  user = _staff_user()
  if user is None:
    return redirect(url_for("pages.login"))
  found = _find(domain, announcement_id)
  return render_template(
    "announcement_form.jinja",
    domain=domain,
    announcement=found,
    action=url_for(
      "announcements.edit_save", slug=domain.slug, announcement_id=found.id
    ),
    values={"title": found.title, "body": found.body},
  )


@bp.post("/<slug>/announcements/<int:announcement_id>/edit")
def edit_save(slug: str, announcement_id: int) -> str | Response:
  domain = _domain(slug)
  user = _staff_user()
  if user is None:
    return redirect(url_for("pages.login"))
  found = _find(domain, announcement_id)
  title, body = _submitted()
  if not title or not body:
    flash("An announcement needs a title and a body.")
    return render_template(
      "announcement_form.jinja",
      domain=domain,
      announcement=found,
      action=url_for(
        "announcements.edit_save", slug=domain.slug, announcement_id=found.id
      ),
      values={"title": title, "body": body},
    )
  announcements_data.update(db(), found.id, title=title, body=body, at=now())
  flash("Announcement saved.")
  return redirect(url_for("records.domain_page", slug=domain.slug))


@bp.get("/<slug>/announcements/<int:announcement_id>/delete")
def confirm_delete(slug: str, announcement_id: int) -> str | Response:
  """Ask before one announcement goes for good."""
  domain = _domain(slug)
  user = _staff_user()
  if user is None:
    return redirect(url_for("pages.login"))
  found = _find(domain, announcement_id)
  return render_template(
    "announcement_confirm.jinja",
    domain=domain,
    announcement=found,
    action=url_for("announcements.remove", slug=domain.slug, announcement_id=found.id),
  )


@bp.post("/<slug>/announcements/<int:announcement_id>/delete")
def remove(slug: str, announcement_id: int) -> str | Response:
  """Delete one announcement after the second click."""
  domain = _domain(slug)
  user = _staff_user()
  if user is None:
    return redirect(url_for("pages.login"))
  found = _find(domain, announcement_id)
  record_audit(
    db(),
    "announcement.removed",
    at=now(),
    actor_id=user.id,
    object_type="announcement",
    object_id=found.id,
    data={"reason": request.form.get("reason")} if request.form.get("reason") else None,
  )
  announcements_data.delete(db(), found.id)
  flash("Announcement removed.")
  return redirect(url_for("records.domain_page", slug=domain.slug))


@bp.post("/<slug>/subscribe")
def subscribe(slug: str) -> str | Response:
  domain = _domain(slug)
  user = current_user()
  if user is None:
    return redirect(url_for("pages.login"))
  on = not subscriptions.subscribed(db(), user.id, domain.slug)
  subscriptions.set_subscribed(db(), user.id, domain.slug, on=on)
  flash(
    f"Subscribed to {domain.name} announcements."
    if on
    else f"Unsubscribed from {domain.name} announcements."
  )
  return redirect(url_for("records.domain_page", slug=domain.slug))
