import pytest

pytestmark = pytest.mark.django_db


def test_login_returns_tokens_and_profile(api, manager):
    res = api().post("/api/auth/login/", {"username": "manager", "password": "Test@12345"})
    assert res.status_code == 200
    assert {"access", "refresh", "user"} <= set(res.data)
    assert res.data["user"]["role"] == "BRANCH_MANAGER"

    client = api()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {res.data['access']}")
    assert client.get("/api/auth/me/").data["username"] == "manager"


def test_wrong_password_uses_error_envelope(api, manager):
    res = api().post("/api/auth/login/", {"username": "manager", "password": "nope"})
    assert res.status_code == 401
    assert res.data["error"]["code"]


def test_logout_blacklists_refresh(api, manager):
    tokens = api().post("/api/auth/login/", {"username": "manager", "password": "Test@12345"}).data
    assert api(manager).post("/api/auth/logout/", {"refresh": tokens["refresh"]}).status_code == 205
    assert api().post("/api/auth/refresh/", {"refresh": tokens["refresh"]}).status_code == 401


def test_anonymous_is_rejected(api):
    assert api().get("/api/collections/").status_code == 401


def test_only_admin_manages_users(api, manager, admin, branch):
    payload = {"username": "new.agent", "password": "Str0ng!Pass", "role": "AGENT", "branch": branch.id}
    assert api(manager).post("/api/users/", payload).status_code == 403
    assert api(admin).post("/api/users/", payload).status_code == 201
    no_branch = {**payload, "username": "x", "branch": ""}
    assert api(admin).post("/api/users/", no_branch).status_code == 400


def test_api_docs_are_public(api, db):
    assert api().get("/api/schema/").status_code == 200
