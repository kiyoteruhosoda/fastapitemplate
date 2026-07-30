from shared.application.authenticated_principal import AuthenticatedPrincipal


def _principal(*scopes: str) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(user_id=1, email="a@example.com", username="a", permissions=frozenset(scopes))


def test_can_requires_all_codes() -> None:
    principal = _principal("item:view", "item:manage")
    assert principal.can("item:view")
    assert principal.can("item:view", "item:manage")
    assert not principal.can("item:view", "user:manage")


def test_empty_scope_means_no_permission() -> None:
    assert not _principal().can("item:view")


def test_id_hash_contains_no_raw_id() -> None:
    principal = _principal()
    assert str(principal.user_id) != principal.id_hash
    assert len(principal.id_hash) == 16
