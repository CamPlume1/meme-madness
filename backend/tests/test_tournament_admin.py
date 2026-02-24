"""Tests for per-tournament admin authentication and authorization.

Tests verify:
- Tournament creator gets 'owner' role
- Invited user gets 'admin' role
- Non-admin is rejected from admin endpoints
- Cross-tournament admin isolation
- Owner can remove admins; non-owners cannot
- Cannot remove yourself
- Duplicate invite prevented
- Invite of nonexistent email rejected
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient

from app.main import app


# ============================================================================
# Mock helpers
# ============================================================================

def _mock_response(data, count=None):
    """Create a mock Supabase response object."""
    resp = MagicMock()
    resp.data = data
    resp.count = count
    return resp


def _fake_user(user_id="user-1", email="alice@example.com", display_name="Alice"):
    return {
        "id": user_id,
        "email": email,
        "display_name": display_name,
    }


def _fake_admin_row(role="owner"):
    return {"id": "admin-row-1", "role": role}


# Patch get_current_user globally for these tests
@pytest.fixture
def client_as_user():
    """Returns a (client, user) tuple with auth bypassed."""
    user = _fake_user()

    async def override_get_current_user(request=None):
        return user

    from app.auth import get_current_user
    app.dependency_overrides[get_current_user] = override_get_current_user
    client = TestClient(app)
    yield client, user
    app.dependency_overrides.clear()


@pytest.fixture
def client_as_owner():
    """Returns a (client, user) tuple where user is a tournament owner."""
    user = _fake_user()
    user["tournament_role"] = "owner"

    async def override_get_current_user(request=None):
        return user

    async def override_require_tournament_admin(request=None):
        return user

    from app.auth import get_current_user, require_tournament_admin
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[require_tournament_admin] = override_require_tournament_admin
    client = TestClient(app)
    yield client, user
    app.dependency_overrides.clear()


@pytest.fixture
def client_as_admin():
    """Returns a (client, user) tuple where user is a tournament admin (not owner)."""
    user = _fake_user(user_id="user-2", email="bob@example.com", display_name="Bob")
    user["tournament_role"] = "admin"

    async def override_get_current_user(request=None):
        return user

    async def override_require_tournament_admin(request=None):
        return user

    from app.auth import get_current_user, require_tournament_admin
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[require_tournament_admin] = override_require_tournament_admin
    client = TestClient(app)
    yield client, user
    app.dependency_overrides.clear()


# ============================================================================
# Test: Tournament creation assigns owner role
# ============================================================================

class TestTournamentCreation:
    @patch("app.routes.admin.supabase_admin")
    def test_creator_becomes_owner(self, mock_sb, client_as_user):
        client, user = client_as_user
        tournament_data = {
            "id": "t-1",
            "name": "Meme Madness 2026",
            "status": "submission_open",
            "created_by": user["id"],
        }

        # Mock tournament insert
        mock_insert = MagicMock()
        mock_insert.execute.return_value = _mock_response([tournament_data])
        mock_sb.table.return_value.insert.return_value = mock_insert

        resp = client.post("/api/admin/tournament/create", json={"name": "Meme Madness 2026"})
        assert resp.status_code == 200
        result = resp.json()
        assert result["name"] == "Meme Madness 2026"
        assert result["created_by"] == user["id"]

        # Verify tournament_admins insert was called with owner role
        calls = mock_sb.table.return_value.insert.call_args_list
        # Second insert call should be to tournament_admins
        assert len(calls) == 2
        admin_insert = calls[1][0][0]
        assert admin_insert["role"] == "owner"
        assert admin_insert["user_id"] == user["id"]
        assert admin_insert["tournament_id"] == "t-1"

    @patch("app.routes.admin.supabase_admin")
    def test_create_tournament_default_name(self, mock_sb, client_as_user):
        client, user = client_as_user
        tournament_data = {
            "id": "t-2",
            "name": "Meme Madness",
            "status": "submission_open",
            "created_by": user["id"],
        }

        mock_insert = MagicMock()
        mock_insert.execute.return_value = _mock_response([tournament_data])
        mock_sb.table.return_value.insert.return_value = mock_insert

        resp = client.post("/api/admin/tournament/create", json={})
        assert resp.status_code == 200
        result = resp.json()
        assert result["name"] == "Meme Madness"


# ============================================================================
# Test: Admin invite system
# ============================================================================

class TestAdminInvite:
    @patch("app.routes.admin.supabase_admin")
    def test_invite_creates_admin_role(self, mock_sb, client_as_owner):
        client, user = client_as_owner
        tid = "tournament-1"

        # Profile lookup returns a user
        mock_table = MagicMock()
        def table_side_effect(name):
            m = MagicMock()
            if name == "profiles":
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.maybe_single.return_value = chain
                chain.execute.return_value = _mock_response({"id": "user-invited", "email": "newadmin@example.com"})
                m.select.return_value = chain
            elif name == "tournament_admins":
                # For checking existing: no existing admin
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.maybe_single.return_value = chain
                chain.execute.return_value = _mock_response(None)
                m.select.return_value = chain
                # For insert
                ins = MagicMock()
                ins.execute.return_value = _mock_response([{"id": "ta-new"}])
                m.insert.return_value = ins
            return m
        mock_sb.table.side_effect = table_side_effect

        resp = client.post(
            f"/api/admin/tournament/{tid}/invite-admin",
            json={"email": "newadmin@example.com"},
        )
        assert resp.status_code == 200
        result = resp.json()
        assert result["success"] is True
        assert result["invited_email"] == "newadmin@example.com"

    @patch("app.routes.admin.supabase_admin")
    def test_invite_nonexistent_email_returns_404(self, mock_sb, client_as_owner):
        client, _ = client_as_owner
        tid = "tournament-1"

        mock_table = MagicMock()
        chain = MagicMock()
        chain.eq.return_value = chain
        chain.maybe_single.return_value = chain
        chain.execute.return_value = _mock_response(None)
        mock_table.select.return_value = chain
        mock_sb.table.return_value = mock_table

        resp = client.post(
            f"/api/admin/tournament/{tid}/invite-admin",
            json={"email": "nobody@example.com"},
        )
        assert resp.status_code == 404
        assert "No user found" in resp.json()["detail"]

    @patch("app.routes.admin.supabase_admin")
    def test_invite_duplicate_returns_400(self, mock_sb, client_as_owner):
        client, _ = client_as_owner
        tid = "tournament-1"

        call_count = {"profiles": 0, "tournament_admins": 0}

        def table_side_effect(name):
            m = MagicMock()
            if name == "profiles":
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.maybe_single.return_value = chain
                chain.execute.return_value = _mock_response({"id": "user-dup", "email": "dup@example.com"})
                m.select.return_value = chain
            elif name == "tournament_admins":
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.maybe_single.return_value = chain
                # Already exists
                chain.execute.return_value = _mock_response({"id": "existing-admin"})
                m.select.return_value = chain
            return m
        mock_sb.table.side_effect = table_side_effect

        resp = client.post(
            f"/api/admin/tournament/{tid}/invite-admin",
            json={"email": "dup@example.com"},
        )
        assert resp.status_code == 400
        assert "already an admin" in resp.json()["detail"]


# ============================================================================
# Test: Non-admin rejection
# ============================================================================

class TestNonAdminRejection:
    def _make_non_admin_client(self):
        """Create a client where user is authenticated but NOT a tournament admin.
        Patches get_current_user as both a DI override and a function mock, then
        mocks tournament_admins lookup to return None."""
        user = _fake_user()

        async def fake_get_user(request=None):
            return user

        from app.auth import get_current_user, require_tournament_admin
        # Override get_current_user at the DI level
        app.dependency_overrides[get_current_user] = fake_get_user
        # Do NOT override require_tournament_admin so its real logic runs
        client = TestClient(app)
        return client, user

    def test_non_admin_cannot_access_dashboard(self):
        """A regular user without admin role should be rejected (403)."""
        client, user = self._make_non_admin_client()
        tid = "tournament-1"

        try:
            # Patch get_current_user as a coroutine AND the supabase_admin call
            with patch("app.auth.get_current_user", return_value=user) as mock_gcu, \
                 patch("app.auth.supabase_admin") as mock_sb:
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.maybe_single.return_value = chain
                chain.execute.return_value = _mock_response(None)  # No admin row
                mock_sb.table.return_value.select.return_value = chain

                resp = client.get(f"/api/admin/tournament/{tid}/dashboard")
                assert resp.status_code == 403
                assert "not an admin" in resp.json()["detail"]
        finally:
            app.dependency_overrides.clear()

    def test_non_admin_cannot_seed(self):
        client, user = self._make_non_admin_client()
        tid = "tournament-1"

        try:
            with patch("app.auth.get_current_user", return_value=user), \
                 patch("app.auth.supabase_admin") as mock_sb:
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.maybe_single.return_value = chain
                chain.execute.return_value = _mock_response(None)
                mock_sb.table.return_value.select.return_value = chain

                resp = client.post(f"/api/admin/tournament/{tid}/seed")
                assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    def test_non_admin_cannot_invite(self):
        client, user = self._make_non_admin_client()
        tid = "tournament-1"

        try:
            with patch("app.auth.get_current_user", return_value=user), \
                 patch("app.auth.supabase_admin") as mock_sb:
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.maybe_single.return_value = chain
                chain.execute.return_value = _mock_response(None)
                mock_sb.table.return_value.select.return_value = chain

                resp = client.post(
                    f"/api/admin/tournament/{tid}/invite-admin",
                    json={"email": "test@example.com"},
                )
                assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()


# ============================================================================
# Test: Cross-tournament admin isolation
# ============================================================================

class TestCrossTournamentIsolation:
    def test_admin_of_one_tournament_rejected_from_another(self):
        """Admin of tournament A cannot access tournament B's admin panel."""
        user = _fake_user()

        async def fake_get_user(request=None):
            return user

        from app.auth import get_current_user
        app.dependency_overrides[get_current_user] = fake_get_user

        try:
            client = TestClient(app)
            with patch("app.auth.get_current_user", return_value=user), \
                 patch("app.auth.supabase_admin") as mock_sb:
                # require_tournament_admin queries tournament_admins for tournament B
                # and finds no match even though user is admin of tournament A
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.maybe_single.return_value = chain
                chain.execute.return_value = _mock_response(None)
                mock_sb.table.return_value.select.return_value = chain

                resp = client.get("/api/admin/tournament/tournament-B/dashboard")
                assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    def test_admin_of_tournament_can_access_own(self):
        """Admin of tournament A can access tournament A's admin panel."""
        user = _fake_user()
        user["tournament_role"] = "admin"

        async def override(request=None):
            return user

        from app.auth import require_tournament_admin, get_current_user
        app.dependency_overrides[require_tournament_admin] = override
        app.dependency_overrides[get_current_user] = override

        try:
            client = TestClient(app)
            with patch("app.routes.admin.supabase_admin") as mock_sb:
                t_data = {
                    "id": "tournament-A",
                    "name": "Test",
                    "status": "submission_open",
                    "total_rounds": None,
                }

                # Dashboard queries
                def table_side_effect(name):
                    m = MagicMock()
                    if name == "tournament":
                        chain = MagicMock()
                        chain.eq.return_value = chain
                        chain.single.return_value = chain
                        chain.execute.return_value = _mock_response(t_data)
                        m.select.return_value = chain
                    elif name == "memes":
                        chain = MagicMock()
                        chain.eq.return_value = chain
                        chain.execute.return_value = _mock_response([], count=5)
                        m.select.return_value = chain
                    elif name == "rounds":
                        chain = MagicMock()
                        chain.eq.return_value = chain
                        chain.order.return_value = chain
                        chain.execute.return_value = _mock_response([])
                        m.select.return_value = chain
                    return m
                mock_sb.table.side_effect = table_side_effect

                resp = client.get("/api/admin/tournament/tournament-A/dashboard")
                assert resp.status_code == 200
                result = resp.json()
                assert result["tournament"]["id"] == "tournament-A"
        finally:
            app.dependency_overrides.clear()


# ============================================================================
# Test: Admin removal permissions
# ============================================================================

class TestAdminRemoval:
    @patch("app.routes.admin.supabase_admin")
    def test_owner_can_remove_admin(self, mock_sb, client_as_owner):
        client, user = client_as_owner
        tid = "tournament-1"
        target_user_id = "user-to-remove"

        mock_delete = MagicMock()
        mock_delete.eq.return_value = mock_delete
        mock_delete.execute.return_value = _mock_response([])
        mock_sb.table.return_value.delete.return_value = mock_delete

        resp = client.delete(f"/api/admin/tournament/{tid}/admins/{target_user_id}")
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    @patch("app.routes.admin.supabase_admin")
    def test_non_owner_cannot_remove_admin(self, mock_sb, client_as_admin):
        """Admin (not owner) should not be able to remove other admins."""
        client, user = client_as_admin
        tid = "tournament-1"

        resp = client.delete(f"/api/admin/tournament/{tid}/admins/user-to-remove")
        assert resp.status_code == 403
        assert "Only the tournament owner" in resp.json()["detail"]

    @patch("app.routes.admin.supabase_admin")
    def test_owner_cannot_remove_self(self, mock_sb, client_as_owner):
        client, user = client_as_owner
        tid = "tournament-1"

        resp = client.delete(f"/api/admin/tournament/{tid}/admins/{user['id']}")
        assert resp.status_code == 400
        assert "Cannot remove yourself" in resp.json()["detail"]


# ============================================================================
# Test: Admin list
# ============================================================================

class TestAdminList:
    @patch("app.routes.admin.supabase_admin")
    def test_list_admins_returns_all(self, mock_sb, client_as_owner):
        client, _ = client_as_owner
        tid = "tournament-1"

        admin_data = [
            {"id": "ta-1", "user_id": "user-1", "role": "owner", "profiles": {"display_name": "Alice", "email": "alice@example.com"}},
            {"id": "ta-2", "user_id": "user-2", "role": "admin", "profiles": {"display_name": "Bob", "email": "bob@example.com"}},
        ]

        chain = MagicMock()
        chain.eq.return_value = chain
        chain.order.return_value = chain
        chain.execute.return_value = _mock_response(admin_data)
        mock_sb.table.return_value.select.return_value = chain

        resp = client.get(f"/api/admin/tournament/{tid}/admins")
        assert resp.status_code == 200
        result = resp.json()
        assert len(result) == 2
        assert result[0]["role"] == "owner"
        assert result[1]["role"] == "admin"


# ============================================================================
# Test: Tie-break authorization and validation
# ============================================================================

class TestTieBreak:
    @patch("app.routes.admin.supabase_admin")
    def test_tie_break_valid_winner(self, mock_sb, client_as_owner):
        client, _ = client_as_owner
        tid = "tournament-1"

        matchup_data = {
            "id": "m-1",
            "meme_a_id": "meme-a",
            "meme_b_id": "meme-b",
            "status": "voting",
            "winner_id": None,
        }

        def table_side_effect(name):
            m = MagicMock()
            if name == "matchups":
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.single.return_value = chain
                chain.execute.return_value = _mock_response(matchup_data)
                m.select.return_value = chain
                # Update chain
                update = MagicMock()
                update.eq.return_value = update
                update.execute.return_value = _mock_response([])
                m.update.return_value = update
            return m
        mock_sb.table.side_effect = table_side_effect

        resp = client.post(
            f"/api/admin/tournament/{tid}/tie-break",
            json={"matchup_id": "m-1", "winner_id": "meme-a"},
        )
        assert resp.status_code == 200
        assert resp.json()["winner_id"] == "meme-a"

    @patch("app.routes.admin.supabase_admin")
    def test_tie_break_invalid_winner_rejected(self, mock_sb, client_as_owner):
        client, _ = client_as_owner
        tid = "tournament-1"

        matchup_data = {
            "id": "m-1",
            "meme_a_id": "meme-a",
            "meme_b_id": "meme-b",
            "status": "voting",
            "winner_id": None,
        }

        chain = MagicMock()
        chain.eq.return_value = chain
        chain.single.return_value = chain
        chain.execute.return_value = _mock_response(matchup_data)
        mock_sb.table.return_value.select.return_value = chain

        resp = client.post(
            f"/api/admin/tournament/{tid}/tie-break",
            json={"matchup_id": "m-1", "winner_id": "meme-invalid"},
        )
        assert resp.status_code == 400
        assert "one of the competitors" in resp.json()["detail"]

    @patch("app.routes.admin.supabase_admin")
    def test_tie_break_already_complete_rejected(self, mock_sb, client_as_owner):
        client, _ = client_as_owner
        tid = "tournament-1"

        matchup_data = {
            "id": "m-1",
            "meme_a_id": "meme-a",
            "meme_b_id": "meme-b",
            "status": "complete",
            "winner_id": "meme-a",
        }

        chain = MagicMock()
        chain.eq.return_value = chain
        chain.single.return_value = chain
        chain.execute.return_value = _mock_response(matchup_data)
        mock_sb.table.return_value.select.return_value = chain

        resp = client.post(
            f"/api/admin/tournament/{tid}/tie-break",
            json={"matchup_id": "m-1", "winner_id": "meme-b"},
        )
        assert resp.status_code == 400
        assert "already resolved" in resp.json()["detail"]
