from pwedepa.core import Actor, Effect, Grant, Visibility, authorize, matches


def test_matches_wildcards_and_object_grants():
  assert matches("*", "request.10.view")
  assert matches("request.*", "request.10.view")
  assert matches("request.view", "request.10.view")
  assert matches("request.10.view", "request.10.view")
  assert not matches("request.10.view", "request.11.view")
  assert not matches("issue.*", "request.10.view")


def test_direct_deny_beats_wildcard_allow_and_admin():
  grants = (Grant("*"), Grant("request.view", Effect.DENY))
  assert not authorize(Actor(id=2, grants=grants), "request.view", object_id=10)
  admin = Actor(id=1, is_admin=True, grants=(Grant("request.view", Effect.DENY),))
  assert not authorize(admin, "request.view", object_id=10)


def test_object_allow_beats_no_namespace_grant():
  actor = Actor(id=2, grants=(Grant("request.10.view"),))
  assert authorize(actor, "request.view", object_id=10)
  assert not authorize(actor, "request.view", object_id=11)


def test_private_object_owner_and_admin_only_by_default():
  owner = Actor(id=2)
  other = Actor(id=3)
  assert authorize(
    owner, "request.view", object_id=10, owner_id=2, visibility=Visibility.PRIVATE
  )
  assert not authorize(
    other, "request.view", object_id=10, owner_id=2, visibility=Visibility.PRIVATE
  )
  assert authorize(
    Actor(id=1, is_admin=True),
    "request.view",
    object_id=10,
    owner_id=2,
    visibility=Visibility.PRIVATE,
  )


def test_private_view_needs_an_object_grant_not_a_namespace_grant():
  namespace_viewer = Actor(id=3, grants=(Grant("request.view"),))
  assert not authorize(
    namespace_viewer,
    "request.view",
    object_id=10,
    owner_id=2,
    visibility=Visibility.PRIVATE,
  )
  object_viewer = Actor(id=3, grants=(Grant("request.10.view"),))
  assert authorize(
    object_viewer,
    "request.view",
    object_id=10,
    owner_id=2,
    visibility=Visibility.PRIVATE,
  )


def test_public_view_still_needs_the_view_capability():
  other = Actor(id=3)
  assert not authorize(
    other, "request.view", object_id=10, visibility=Visibility.PUBLIC
  )
  viewer = Actor(id=3, grants=(Grant("request.view"),))
  assert authorize(viewer, "request.view", object_id=10, visibility=Visibility.PUBLIC)


def test_anonymous_actor_gets_nothing():
  assert not authorize(
    Actor(id=None), "request.view", object_id=10, visibility=Visibility.PUBLIC
  )
