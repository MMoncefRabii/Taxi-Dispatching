import hashlib
import os
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://localhost/test_db")

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient

import main
from app.config import Settings
from app.db import get_db
from app.models import Admin, AdminInvitation, Center, PlatformAuditLog, SuperAdmin
from app.platform.auth import PlatformPrincipal, require_super_admin


def result(value=None, rows=()):
    return SimpleNamespace(
        scalar_one_or_none=lambda: value,
        scalar_one=lambda: value,
        one_or_none=lambda: value,
        scalars=lambda: SimpleNamespace(all=lambda: list(rows)),
    )


@pytest.fixture
def mock_db():
    db = Mock()
    db.execute = AsyncMock(return_value=result())
    db.added = []
    db.add = Mock(side_effect=db.added.append)
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    main.app.dependency_overrides[get_db] = lambda: db
    yield db
    main.app.dependency_overrides.clear()


def use_platform_dependency():
    super_admin = SuperAdmin(
        id=uuid.uuid4(),
        email="owner@example.com",
        password_hash="unused",
        active=True,
    )
    principal = PlatformPrincipal(super_admin=super_admin, session=Mock())
    main.app.dependency_overrides[require_super_admin] = lambda: principal
    return principal


def make_center(*, active=True):
    return Center(
        id=uuid.uuid4(),
        name="Central",
        city="Tunis",
        timezone="Africa/Tunis",
        active=active,
    )


def make_invitation(
    *,
    center_id=None,
    email="invite-test@example.invalid",
    token="one-time-secret-token",
    expires_at=None,
    used_at=None,
    revoked_at=None,
):
    now = datetime.now(timezone.utc)
    return AdminInvitation(
        id=uuid.uuid4(),
        center_id=center_id or uuid.uuid4(),
        email=email,
        token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
        created_at=now,
        expires_at=expires_at or now + timedelta(hours=48),
        used_at=used_at,
        revoked_at=revoked_at,
    )


@pytest.mark.usefixtures("mock_db")
@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        (
            "post",
            f"/platform/centers/{uuid.uuid4()}/invitations",
            {"email": "invitee@example.invalid"},
        ),
        ("get", f"/platform/centers/{uuid.uuid4()}/invitations", None),
        ("post", f"/platform/invitations/{uuid.uuid4()}/revoke", None),
    ],
)
@pytest.mark.parametrize("admin_cookie", [False, True])
def test_private_invitation_routes_require_platform_session(
    method, path, body, admin_cookie
):
    with TestClient(main.app) as client:
        if admin_cookie:
            client.cookies.set(main.ADMIN_SESSION_COOKIE, "center-admin-session")
        response = client.request(method, path, json=body)

    assert response.status_code == 401


@pytest.mark.usefixtures("mock_db")
def test_create_invitation_returns_a_separate_token_once_and_audits(
    mock_db, caplog
):
    principal = use_platform_dependency()
    center = make_center()
    execute_count = 0

    async def execute(statement):
        nonlocal execute_count
        execute_count += 1
        if execute_count == 1:
            return result(center)
        if execute_count in {2, 3}:
            return result()
        invitation_row = next(
            row for row in mock_db.added if isinstance(row, AdminInvitation)
        )
        return result(invitation_row)

    async def flush():
        for row in mock_db.added:
            if isinstance(row, AdminInvitation) and row.id is None:
                row.id = uuid.uuid4()

    mock_db.execute.side_effect = execute
    mock_db.flush.side_effect = flush

    with TestClient(main.app) as client:
        response = client.post(
            f"/platform/centers/{center.id}/invitations",
            json={"email": " Invite-Test@Example.Invalid "},
        )

    assert response.status_code == 201
    assert response.headers["cache-control"] == "no-store"
    payload = response.json()
    assert payload["email"] == "invite-test@example.invalid"
    assert payload["link"] == "http://localhost:5173/invite.html"
    token = payload["token"]
    invitation = next(
        row for row in mock_db.added if isinstance(row, AdminInvitation)
    )
    assert payload["invitation_id"] == str(invitation.id)
    assert invitation.token_hash == hashlib.sha256(token.encode()).hexdigest()
    assert token not in repr(invitation.__dict__)
    assert invitation.expires_at - invitation.created_at == timedelta(hours=48)

    event = next(row for row in mock_db.added if isinstance(row, PlatformAuditLog))
    assert event.action == "invitation_created"
    assert event.target_type == "invitation"
    assert event.target_id == invitation.id
    assert event.super_admin_id == principal.super_admin.id
    assert event.email_hash is None
    assert token not in repr(event.__dict__)
    assert token not in caplog.text
    mock_db.commit.assert_awaited_once()


@pytest.mark.usefixtures("mock_db")
def test_new_invitation_revokes_older_unused_invitation(mock_db):
    use_platform_dependency()
    center = make_center()
    invitation = make_invitation(center_id=center.id)
    mock_db.execute.side_effect = [
        result(center),
        result(),
        result(),
        result(invitation),
    ]

    with TestClient(main.app) as client:
        response = client.post(
            f"/platform/centers/{center.id}/invitations",
            json={"email": "invite-test@example.invalid"},
        )

    assert response.status_code == 201
    revoke_statement = mock_db.execute.await_args_list[2].args[0]
    compiled = str(revoke_statement)
    assert "UPDATE admin_invitations" in compiled
    assert "admin_invitations.center_id" in compiled
    assert "admin_invitations.email" in compiled
    assert "admin_invitations.used_at IS NULL" in compiled
    assert "admin_invitations.revoked_at IS NULL" in compiled


@pytest.mark.usefixtures("mock_db")
def test_create_invitation_rejects_unknown_inactive_center_and_existing_admin(mock_db):
    use_platform_dependency()
    center_id = uuid.uuid4()
    mock_db.execute.side_effect = None
    mock_db.execute.return_value = result(None)
    with TestClient(main.app) as client:
        missing = client.post(
            f"/platform/centers/{center_id}/invitations",
            json={"email": "invitee@example.invalid"},
        )
    assert missing.status_code == 404

    inactive = make_center(active=False)
    mock_db.execute.return_value = result(inactive)
    with TestClient(main.app) as client:
        inactive_response = client.post(
            f"/platform/centers/{inactive.id}/invitations",
            json={"email": "invitee@example.invalid"},
        )
    assert inactive_response.status_code == 409

    active = make_center()
    mock_db.execute.side_effect = [result(active), result(uuid.uuid4())]
    with TestClient(main.app) as client:
        existing_response = client.post(
            f"/platform/centers/{active.id}/invitations",
            json={"email": "invitee@example.invalid"},
        )
    assert existing_response.status_code == 409
    assert mock_db.add.call_count == 0


@pytest.mark.usefixtures("mock_db")
def test_create_invitation_rejects_invalid_email_and_extra_fields(mock_db):
    use_platform_dependency()
    with TestClient(main.app) as client:
        invalid = client.post(
            f"/platform/centers/{uuid.uuid4()}/invitations",
            json={"email": "not-an-email"},
        )
        extra = client.post(
            f"/platform/centers/{uuid.uuid4()}/invitations",
            json={"email": "invitee@example.invalid", "center_id": str(uuid.uuid4())},
        )

    assert invalid.status_code == 422
    assert extra.status_code == 422
    assert "invitee@example.invalid" not in extra.text
    mock_db.execute.assert_not_awaited()


@pytest.mark.usefixtures("mock_db")
def test_list_invitations_limits_fields_and_serializes_statuses(mock_db):
    use_platform_dependency()
    center = make_center()
    now = datetime.now(timezone.utc)
    invitations = [
        make_invitation(center_id=center.id),
        make_invitation(
            center_id=center.id,
            used_at=now,
        ),
        make_invitation(
            center_id=center.id,
            expires_at=now - timedelta(minutes=1),
        ),
        make_invitation(
            center_id=center.id,
            revoked_at=now,
        ),
    ]
    mock_db.execute.return_value = result(rows=invitations)

    with TestClient(main.app) as client:
        response = client.get(
            f"/platform/centers/{center.id}/invitations?limit=7&offset=3"
        )

    assert response.status_code == 200
    payload = response.json()
    assert [item["status"] for item in payload] == [
        "pending",
        "used",
        "expired",
        "revoked",
    ]
    assert all("token_hash" not in item for item in payload)
    query = mock_db.execute.await_args.args[0]
    assert query._limit_clause.value == 7
    assert query._offset_clause.value == 3


@pytest.mark.usefixtures("mock_db")
def test_list_invitations_rejects_limit_above_max(mock_db):
    use_platform_dependency()
    with TestClient(main.app) as client:
        response = client.get(
            f"/platform/centers/{uuid.uuid4()}/invitations?limit=201"
        )
    assert response.status_code == 422
    mock_db.execute.assert_not_awaited()


@pytest.mark.usefixtures("mock_db")
def test_revoke_invitation_is_audited_and_unknown_id_is_generic_404(mock_db):
    principal = use_platform_dependency()
    invitation = make_invitation()
    mock_db.execute.side_effect = [
        result(invitation),
        result(invitation.id),
    ]

    with TestClient(main.app) as client:
        revoked = client.post(f"/platform/invitations/{invitation.id}/revoke")
    assert revoked.status_code == 200
    event = next(row for row in mock_db.added if isinstance(row, PlatformAuditLog))
    assert event.action == "invitation_revoked"
    assert event.target_type == "invitation"
    assert event.target_id == invitation.id
    assert event.super_admin_id == principal.super_admin.id
    mock_db.commit.assert_awaited_once()

    invitation.revoked_at = datetime.now(timezone.utc)
    mock_db.execute.side_effect = None
    mock_db.execute.return_value = result(invitation)
    with TestClient(main.app) as client:
        repeated = client.post(f"/platform/invitations/{invitation.id}/revoke")
    assert repeated.status_code == 200
    assert repeated.json() == {"ok": True}
    assert sum(isinstance(row, PlatformAuditLog) for row in mock_db.added) == 1

    mock_db.execute.side_effect = None
    mock_db.execute.return_value = result(None)
    with TestClient(main.app) as client:
        missing = client.post(f"/platform/invitations/{uuid.uuid4()}/revoke")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Invitation not found"


@pytest.mark.usefixtures("mock_db")
def test_accept_invitation_creates_admin_in_invited_center_and_audits(
    mock_db, caplog
):
    center_id = uuid.uuid4()
    token = "one-time-secret-token"
    email = "invite-test@example.invalid"
    mock_db.execute.side_effect = [
        result((center_id, email)),
        result(),
    ]

    with TestClient(main.app) as client:
        response = client.post(
            "/invitations/accept",
            json={"token": token, "password": "correct horse battery staple"},
        )

    assert response.status_code == 201
    assert response.json() == {"ok": True}
    admin = next(row for row in mock_db.added if isinstance(row, Admin))
    assert admin.center_id == center_id
    assert admin.email == email
    assert PasswordHasher().verify(admin.password_hash, "correct horse battery staple")
    claim = mock_db.execute.await_args_list[0].args[0]
    assert token not in str(claim.compile().params)
    assert hashlib.sha256(token.encode()).hexdigest() in str(claim.compile().params)

    event = next(row for row in mock_db.added if isinstance(row, PlatformAuditLog))
    assert event.action == "invitation_accepted"
    assert event.super_admin_id is None
    assert event.target_type == "center"
    assert event.target_id == center_id
    assert event.email_hash is None
    assert token not in repr(event.__dict__)
    assert email not in repr(event.__dict__)
    assert token not in caplog.text
    assert "correct horse battery staple" not in caplog.text
    mock_db.commit.assert_awaited_once()


@pytest.mark.usefixtures("mock_db")
@pytest.mark.parametrize("state", ["wrong", "expired", "used", "revoked"])
def test_invalid_invitation_states_share_generic_400(mock_db, state):
    mock_db.execute.return_value = result(None)
    token = f"{state}-secret-token"

    with TestClient(main.app) as client:
        response = client.post(
            "/invitations/accept",
            json={"token": token, "password": "correct horse battery staple"},
        )

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid or expired invitation"}
    assert token not in response.text
    mock_db.rollback.assert_awaited_once()


@pytest.mark.usefixtures("mock_db")
def test_existing_admin_rolls_back_claim_and_returns_generic_400(mock_db):
    mock_db.execute.side_effect = [
        result((uuid.uuid4(), "invite-test@example.invalid")),
        result(uuid.uuid4()),
    ]

    with TestClient(main.app) as client:
        response = client.post(
            "/invitations/accept",
            json={
                "token": "one-time-secret-token",
                "password": "correct horse battery staple",
            },
        )

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid or expired invitation"}
    assert response.json().get("token") is None
    assert not any(isinstance(row, Admin) for row in mock_db.added)
    mock_db.rollback.assert_awaited_once()
    mock_db.commit.assert_not_awaited()


@pytest.mark.usefixtures("mock_db")
def test_second_accept_with_same_token_fails(mock_db):
    mock_db.execute.side_effect = [
        result((uuid.uuid4(), "invite-test@example.invalid")),
        result(),
        result(None),
    ]

    with TestClient(main.app) as client:
        accepted = client.post(
            "/invitations/accept",
            json={
                "token": "one-time-secret-token",
                "password": "correct horse battery staple",
            },
        )
        repeated = client.post(
            "/invitations/accept",
            json={
                "token": "one-time-secret-token",
                "password": "correct horse battery staple",
            },
        )

    assert accepted.status_code == 201
    assert repeated.status_code == 400
    assert repeated.json() == {"detail": "Invalid or expired invitation"}
    assert sum(isinstance(row, Admin) for row in mock_db.added) == 1


@pytest.mark.usefixtures("mock_db")
@pytest.mark.parametrize(
    "body",
    [
        {"token": "must-not-be-echoed-secret", "password": "short"},
        {
            "token": "must-not-be-echoed-secret",
            "password": "correct horse battery staple",
            "center_id": str(uuid.uuid4()),
        },
        {
            "token": "must-not-be-echoed-secret",
            "password": "correct horse battery staple",
            "email": "attacker@example.invalid",
        },
    ],
)
def test_accept_validation_rejects_short_password_and_client_account_fields(
    mock_db, body
):
    with TestClient(main.app) as client:
        response = client.post("/invitations/accept", json=body)

    assert response.status_code == 422
    assert "must-not-be-echoed-secret" not in response.text
    assert "attacker@example.invalid" not in response.text
    mock_db.execute.assert_not_awaited()
    mock_db.add.assert_not_called()


def test_public_accept_cors_allows_only_configured_origin():
    with TestClient(main.app) as client:
        allowed = client.options(
            "/invitations/accept",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        denied = client.options(
            "/invitations/accept",
            headers={
                "Origin": "https://attacker.example",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert allowed.headers["access-control-allow-credentials"] == "true"
    assert not any(
        header.lower().startswith("access-control-")
        for header in denied.headers
    )


@pytest.mark.parametrize(
    "base_url",
    [
        "ftp://frontend.example",
        "https://frontend.example/",
        "https://user:password@frontend.example",
        "https://frontend.example?token=bad",
    ],
)
def test_frontend_base_url_must_be_http_without_trailing_slash(base_url):
    with pytest.raises(ValueError):
        Settings(DATABASE_URL="postgresql://localhost/test", FRONTEND_BASE_URL=base_url)
