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

from pwedepa.data import announcements as announcements_data
from pwedepa.data import domains as domains_data

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


@bp.get("/<slug>/announcements/new")
def new(slug: str) -> str | Response:
  """Show the form for a new announcement."""
  domain = _domain(slug)
  user = _staff_user()
  if user is None:
    return redirect(url_for("pages.login"))
  return render_template(
    "announcement_form.html",
    domain=domain,
    announcement=None,
    action=url_for("announcements.create", slug=domain.slug),
    values={"title": "", "body": ""},
  )


@bp.post("/<slug>/announcements")
def create(slug: str) -> str | Response:
  """Store one announcement, then show the Domain page."""
  domain = _domain(slug)
  user = _staff_user()
  if user is None:
    return redirect(url_for("pages.login"))
  title, body = _submitted()
  if not title or not body:
    flash("An announcement needs a title and a body.")
    return render_template(
      "announcement_form.html",
      domain=domain,
      announcement=None,
      action=url_for("announcements.create", slug=domain.slug),
      values={"title": title, "body": body},
    )
  announcements_data.create(
    db(), domain=domain.name, title=title, body=body, author_id=user.id, at=now()
  )
  flash("Announcement published.")
  return redirect(url_for("records.domain_page", slug=domain.slug))


@bp.get("/<slug>/announcements/<int:announcement_id>/edit")
def edit(slug: str, announcement_id: int) -> str | Response:
  """Show the form for one announcement, filled in."""
  domain = _domain(slug)
  user = _staff_user()
  if user is None:
    return redirect(url_for("pages.login"))
  found = _find(domain, announcement_id)
  return render_template(
    "announcement_form.html",
    domain=domain,
    announcement=found,
    action=url_for(
      "announcements.edit_save", slug=domain.slug, announcement_id=found.id
    ),
    values={"title": found.title, "body": found.body},
  )


@bp.post("/<slug>/announcements/<int:announcement_id>/edit")
def edit_save(slug: str, announcement_id: int) -> str | Response:
  """Save one edited announcement and mark the edit time."""
  domain = _domain(slug)
  user = _staff_user()
  if user is None:
    return redirect(url_for("pages.login"))
  found = _find(domain, announcement_id)
  title, body = _submitted()
  if not title or not body:
    flash("An announcement needs a title and a body.")
    return render_template(
      "announcement_form.html",
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


def _find(domain, announcement_id: int):
  found = announcements_data.get(db(), announcement_id)
  if found is None or found.domain != domain.name:
    abort(404)
  return found
