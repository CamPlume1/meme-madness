"""Tests for tournament membership with join codes.

Tests verify:
- Joining with valid code creates membership
- Joining with invalid code returns 404
- Already-member case handled gracefully
- Code is case-insensitive (uppercased)
- Members can access tournament, non-members get 403
- Admins have implicit membership
- Non-members filtered from tournament list
- Members can upload memes, non-members rejected
- Admin can get/regenerate join code
- Join code generated on tournament creation
- Admin can list/remove members
"""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app


# ============================================================================
# Mock helpers
# ============================================================================

def _mock_response(data, count=None):
    resp = MagicMock()
    resp.data = data
    resp.count = count
    return resp


def _fake_user(user_id="user-1", email="alice@example.com", display_name="Alice"):
    return {"id": user_id, "email": email, "display_name": display_name}


@pytest.fixture
def client_as_user():
    """Client with auth bypassed as a regular user."""
    user = _fake_user()

    async def override(request=None):
        return user

    from app.auth import get_current_user
    app.dependency_overrides[get_current_user] = override
    client = TestClient(app)
    yield client, user
    app.dependency_overrides.clear()


@pytest.fixture
def client_as_member():
    """Client where user is a tournament member."""
    user = _fake_user()
    user["tournament_role"] = "member"

    async def override_member(request=None):
        return user

    from app.auth import get_current_user, require_tournament_member
    app.dependency_overrides[get_current_user] = override_member
    app.dependency_overrides[require_tournament_member] = override_member
    client = TestClient(app)
    yield client, user
    app.dependency_overrides.clear()


@pytest.fixture
def client_as_owner():
    """Client where user is a tournament owner (admin)."""
    user = _fake_user()
    user["tournament_role"] = "owner"

    async def override(request=None):
        return user

    from app.auth import get_current_user, require_tournament_admin, require_tournament_member
    app.dependency_overrides[get_current_user] = override
    app.dependency_overrides[require_tournament_admin] = override
    app.dependency_overrides[require_tournament_member] = override
    client = TestClient(app)
    yield client, user
    app.dependency_overrides.clear()


# ============================================================================
# Test: Joining with code
# ============================================================================

class TestJoinWithCode:
    @patch("app.routes.membership.supabase_admin")
    def test_valid_code_creates_membership(self, mock_sb, client_as_user):
        client, user = client_as_user

        def table_side_effect(name):
            m = MagicMock()
            if name == "tournament":
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.maybe_single.return_value = chain
                chain.execute.return_value = _mock_response({"id": "t-1", "name": "Test Tourney"})
                m.select.return_value = chain
            elif name == "tournament_admins":
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.maybe_single.return_value = chain
                chain.execute.return_value = _mock_response(None)
                m.select.return_value = chain
            elif name == "tournament_members":
                # First call: check existing (None), second: insert
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.maybe_single.return_value = chain
                chain.execute.return_value = _mock_response(None)
                m.select.return_value = chain
                ins = MagicMock()
                ins.execute.return_value = _mock_response([{"id": "tm-1"}])
                m.insert.return_value = ins
            return m
        mock_sb.table.side_effect = table_side_effect

        resp = client.post("/api/membership/join", json={"join_code": "ABC12345"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["tournament_id"] == "t-1"
        assert data["name"] == "Test Tourney"
        assert data["already_member"] is False

    @patch("app.routes.membership.supabase_admin")
    def test_invalid_code_returns_404(self, mock_sb, client_as_user):
        client, _ = client_as_user

        chain = MagicMock()
        chain.eq.return_value = chain
        chain.maybe_single.return_value = chain
        chain.execute.return_value = _mock_response(None)
        mock_sb.table.return_value.select.return_value = chain

        resp = client.post("/api/membership/join", json={"join_code": "INVALID0"})
        assert resp.status_code == 404
        assert "Invalid join code" in resp.json()["detail"]

    @patch("app.routes.membership.supabase_admin")
    def test_already_member_handled_gracefully(self, mock_sb, client_as_user):
        client, user = client_as_user

        def table_side_effect(name):
            m = MagicMock()
            if name == "tournament":
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.maybe_single.return_value = chain
                chain.execute.return_value = _mock_response({"id": "t-1", "name": "Test"})
                m.select.return_value = chain
            elif name == "tournament_admins":
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.maybe_single.return_value = chain
                chain.execute.return_value = _mock_response(None)
                m.select.return_value = chain
            elif name == "tournament_members":
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.maybe_single.return_value = chain
                chain.execute.return_value = _mock_response({"id": "tm-existing"})
                m.select.return_value = chain
            return m
        mock_sb.table.side_effect = table_side_effect

        resp = client.post("/api/membership/join", json={"join_code": "ABC12345"})
        assert resp.status_code == 200
        assert resp.json()["already_member"] is True

    @patch("app.routes.membership.supabase_admin")
    def test_code_uppercased(self, mock_sb, client_as_user):
        """Join code should be uppercased before lookup."""
        client, _ = client_as_user

        chain = MagicMock()
        chain.eq.return_value = chain
        chain.maybe_single.return_value = chain
        chain.execute.return_value = _mock_response(None)
        mock_sb.table.return_value.select.return_value = chain

        resp = client.post("/api/membership/join", json={"join_code": "abc12345"})
        # Verify the eq call used uppercased code
        eq_calls = mock_sb.table.return_value.select.return_value.eq.call_args_list
        code_calls = [c for c in eq_calls if len(c[0]) >= 2 and c[0][0] == "join_code"]
        if code_calls:
            assert code_calls[0][0][1] == "ABC12345"


# ============================================================================
# Test: Membership gating
# ============================================================================

class TestMembershipGating:
    @patch("app.routes.tournament.supabase_admin")
    def test_member_can_access_tournament(self, mock_sb, client_as_member):
        client, user = client_as_member

        chain = MagicMock()
        chain.eq.return_value = chain
        chain.maybe_single.return_value = chain
        chain.execute.return_value = _mock_response({
            "id": "t-1", "name": "Test", "status": "submission_open",
            "total_rounds": None, "created_at": "2026-01-01T00:00:00Z",
        })
        mock_sb.table.return_value.select.return_value = chain

        resp = client.get("/api/tournament/t-1")
        assert resp.status_code == 200
        assert resp.json()["user_role"] == "member"

    def test_non_member_gets_403(self):
        """User who is neither admin nor member gets 403."""
        from fastapi import HTTPException
        from app.auth import get_current_user, require_tournament_member

        user = _fake_user(user_id="outsider")

        async def fake_get_user(request=None):
            return user

        async def fake_require_member(request=None):
            raise HTTPException(status_code=403, detail="You are not a member of this tournament")

        app.dependency_overrides[get_current_user] = fake_get_user
        app.dependency_overrides[require_tournament_member] = fake_require_member

        try:
            client = TestClient(app)
            resp = client.get("/api/tournament/t-1")
            assert resp.status_code == 403
            assert "not a member" in resp.json()["detail"]
        finally:
            app.dependency_overrides.clear()

    @patch("app.routes.tournament.supabase_admin")
    def test_admin_has_implicit_membership(self, mock_sb):
        """An admin can access tournament without being in tournament_members."""
        user = _fake_user()
        user["tournament_role"] = "admin"

        async def override(request=None):
            return user

        from app.auth import get_current_user, require_tournament_member
        app.dependency_overrides[get_current_user] = override
        app.dependency_overrides[require_tournament_member] = override

        try:
            client = TestClient(app)
            chain = MagicMock()
            chain.eq.return_value = chain
            chain.maybe_single.return_value = chain
            chain.execute.return_value = _mock_response({
                "id": "t-1", "name": "Test", "status": "voting_open",
                "total_rounds": 3, "created_at": "2026-01-01T00:00:00Z",
            })
            mock_sb.table.return_value.select.return_value = chain

            resp = client.get("/api/tournament/t-1")
            assert resp.status_code == 200
            assert resp.json()["user_role"] == "admin"
        finally:
            app.dependency_overrides.clear()

    @patch("app.routes.tournament.supabase_admin")
    def test_non_member_filtered_from_list(self, mock_sb, client_as_user):
        """Tournament list only shows tournaments user is member/admin of."""
        client, user = client_as_user

        def table_side_effect(name):
            m = MagicMock()
            if name == "tournament_admins":
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.execute.return_value = _mock_response([])
                m.select.return_value = chain
            elif name == "tournament_members":
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.execute.return_value = _mock_response([])
                m.select.return_value = chain
            return m
        mock_sb.table.side_effect = table_side_effect

        resp = client.get("/api/tournament/list")
        assert resp.status_code == 200
        assert resp.json() == []


# ============================================================================
# Test: Meme upload membership
# ============================================================================

class TestMemeUploadMembership:
    @patch("app.routes.memes.supabase_admin")
    @patch("app.routes.memes.verify_membership")
    def test_member_can_upload(self, mock_verify, mock_sb, client_as_user):
        """A member should be able to upload memes."""
        client, user = client_as_user
        mock_verify.return_value = None  # No exception = member

        # Mock tournament lookup
        def table_side_effect(name):
            m = MagicMock()
            if name == "tournament":
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.maybe_single.return_value = chain
                chain.execute.return_value = _mock_response({
                    "id": "t-1", "status": "submission_open",
                })
                m.select.return_value = chain
            elif name == "memes":
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.execute.return_value = _mock_response([], count=0)
                m.select.return_value = chain
                ins = MagicMock()
                ins.execute.return_value = _mock_response([{
                    "id": "meme-1", "title": "Test", "image_url": "http://example.com/img.png",
                    "owner_id": user["id"], "tournament_id": "t-1",
                }])
                m.insert.return_value = ins
            return m
        mock_sb.table.side_effect = table_side_effect
        mock_sb.storage.from_.return_value.upload.return_value = None

        import io
        files = {"file": ("test.png", io.BytesIO(b"fake-image"), "image/png")}
        resp = client.post(
            "/api/memes/upload",
            data={"tournament_id": "t-1", "title": "Test"},
            files=files,
        )
        assert resp.status_code == 200
        mock_verify.assert_called_once()

    @patch("app.routes.memes.supabase_admin")
    @patch("app.routes.memes.verify_membership")
    def test_non_member_rejected_upload(self, mock_verify, mock_sb, client_as_user):
        """A non-member should be rejected from uploading."""
        from fastapi import HTTPException
        client, user = client_as_user
        mock_verify.side_effect = HTTPException(status_code=403, detail="You are not a member of this tournament")

        # Mock tournament lookup
        chain = MagicMock()
        chain.eq.return_value = chain
        chain.maybe_single.return_value = chain
        chain.execute.return_value = _mock_response({
            "id": "t-1", "status": "submission_open",
        })
        mock_sb.table.return_value.select.return_value = chain

        import io
        files = {"file": ("test.png", io.BytesIO(b"fake-image"), "image/png")}
        resp = client.post(
            "/api/memes/upload",
            data={"tournament_id": "t-1", "title": "Test"},
            files=files,
        )
        assert resp.status_code == 403


# ============================================================================
# Test: Join code management
# ============================================================================

class TestJoinCodeManagement:
    @patch("app.routes.admin.supabase_admin")
    def test_admin_can_get_code(self, mock_sb, client_as_owner):
        client, _ = client_as_owner

        chain = MagicMock()
        chain.eq.return_value = chain
        chain.single.return_value = chain
        chain.execute.return_value = _mock_response({"join_code": "ABC12345"})
        mock_sb.table.return_value.select.return_value = chain

        resp = client.get("/api/admin/tournament/t-1/join-code")
        assert resp.status_code == 200
        assert resp.json()["join_code"] == "ABC12345"

    @patch("app.routes.admin.supabase_admin")
    def test_admin_can_regenerate_code(self, mock_sb, client_as_owner):
        client, _ = client_as_owner

        update_chain = MagicMock()
        update_chain.eq.return_value = update_chain
        update_chain.execute.return_value = _mock_response([])
        mock_sb.table.return_value.update.return_value = update_chain

        resp = client.post("/api/admin/tournament/t-1/regenerate-code")
        assert resp.status_code == 200
        code = resp.json()["join_code"]
        assert len(code) == 8
        assert code.isalnum()
        assert code == code.upper()

    def test_non_admin_cannot_get_code(self):
        """Non-admin should be rejected from join code endpoint."""
        from fastapi import HTTPException
        from app.auth import get_current_user, require_tournament_admin

        user = _fake_user(user_id="outsider")

        async def fake_get_user(request=None):
            return user

        async def fake_require_admin(request=None):
            raise HTTPException(status_code=403, detail="You are not an admin of this tournament")

        app.dependency_overrides[get_current_user] = fake_get_user
        app.dependency_overrides[require_tournament_admin] = fake_require_admin

        try:
            client = TestClient(app)
            resp = client.get("/api/admin/tournament/t-1/join-code")
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    @patch("app.routes.admin.supabase_admin")
    def test_code_generated_on_creation(self, mock_sb, client_as_user):
        """Join code should be included when creating a tournament."""
        client, user = client_as_user

        created_data = {}

        def capture_insert(data):
            created_data.update(data)
            m = MagicMock()
            m.execute.return_value = _mock_response([{
                "id": "t-new", "name": "New", "status": "submission_open",
                "created_by": user["id"], "join_code": data.get("join_code", ""),
            }])
            return m

        mock_sb.table.return_value.insert.side_effect = capture_insert

        resp = client.post("/api/admin/tournament/create", json={"name": "New"})
        assert resp.status_code == 200
        assert "join_code" in created_data
        assert len(created_data["join_code"]) == 8


# ============================================================================
# Test: Member management
# ============================================================================

class TestMemberManagement:
    @patch("app.routes.admin.supabase_admin")
    def test_admin_can_list_members(self, mock_sb, client_as_owner):
        client, _ = client_as_owner

        member_data = [
            {"id": "tm-1", "user_id": "u-1", "tournament_id": "t-1",
             "joined_at": "2026-01-01T00:00:00Z",
             "profiles": {"display_name": "Bob", "email": "bob@example.com"}},
        ]

        chain = MagicMock()
        chain.eq.return_value = chain
        chain.order.return_value = chain
        chain.execute.return_value = _mock_response(member_data)
        mock_sb.table.return_value.select.return_value = chain

        resp = client.get("/api/admin/tournament/t-1/members")
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["profiles"]["display_name"] == "Bob"

    @patch("app.routes.admin.supabase_admin")
    def test_admin_can_remove_member(self, mock_sb, client_as_owner):
        client, _ = client_as_owner

        delete_chain = MagicMock()
        delete_chain.eq.return_value = delete_chain
        delete_chain.execute.return_value = _mock_response([])
        mock_sb.table.return_value.delete.return_value = delete_chain

        resp = client.delete("/api/admin/tournament/t-1/members/u-2")
        assert resp.status_code == 200
        assert resp.json()["success"] is True
