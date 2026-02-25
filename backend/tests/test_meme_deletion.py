"""Tests for meme deletion (DELETE /api/memes/{meme_id}).

Covers: owner delete, admin delete, non-owner rejection, not-found,
status-gate (only submission_open), and resubmission after delete.
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


def _fake_user(user_id="user-1", email="alice@example.com"):
    return {"id": user_id, "email": email, "display_name": "Alice"}


def _make_meme(meme_id="meme-1", owner_id="user-1", tournament_id="t-1"):
    return {
        "id": meme_id,
        "owner_id": owner_id,
        "tournament_id": tournament_id,
        "title": "Test Meme",
        "image_url": "https://example.supabase.co/storage/v1/object/public/memes/user-1/abc.png",
    }


@pytest.fixture
def authed_client():
    """Client with auth bypassed — regular user."""
    user = _fake_user()

    async def override(request=None):
        return user

    from app.auth import get_current_user
    app.dependency_overrides[get_current_user] = override
    client = TestClient(app)
    yield client, user
    app.dependency_overrides.clear()


@pytest.fixture
def other_user_client():
    """Client with auth bypassed — different user (user-2)."""
    user = _fake_user(user_id="user-2", email="bob@example.com")

    async def override(request=None):
        return user

    from app.auth import get_current_user
    app.dependency_overrides[get_current_user] = override
    client = TestClient(app)
    yield client, user
    app.dependency_overrides.clear()


@pytest.fixture
def admin_client():
    """Client with auth bypassed — tournament admin (user-admin)."""
    user = _fake_user(user_id="user-admin", email="admin@example.com")

    async def override(request=None):
        return user

    from app.auth import get_current_user
    app.dependency_overrides[get_current_user] = override
    client = TestClient(app)
    yield client, user
    app.dependency_overrides.clear()


# ============================================================================
# Tests
# ============================================================================

class TestMemeDeletion:
    @patch("app.routes.memes.supabase_admin")
    def test_owner_can_delete_own_meme(self, mock_sb, authed_client):
        """Owner should be able to delete their own meme when submissions are open."""
        client, user = authed_client
        meme = _make_meme(owner_id=user["id"])

        def table_side_effect(name):
            m = MagicMock()
            if name == "memes":
                # select (fetch meme)
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.maybe_single.return_value = chain
                chain.execute.return_value = _mock_response(meme)
                m.select.return_value = chain
                # delete
                delete_chain = MagicMock()
                delete_chain.eq.return_value = delete_chain
                delete_chain.execute.return_value = _mock_response([])
                m.delete.return_value = delete_chain
            elif name == "tournament":
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.maybe_single.return_value = chain
                chain.execute.return_value = _mock_response({"id": "t-1", "status": "submission_open"})
                m.select.return_value = chain
            return m
        mock_sb.table.side_effect = table_side_effect
        mock_sb.storage.from_.return_value.remove.return_value = None

        resp = client.delete("/api/memes/meme-1?tournament_id=t-1")
        assert resp.status_code == 200
        assert resp.json()["deleted_id"] == "meme-1"

    @patch("app.routes.memes.supabase_admin")
    def test_non_owner_non_admin_rejected(self, mock_sb, other_user_client):
        """Non-owner who is not an admin should get 403."""
        client, user = other_user_client
        meme = _make_meme(owner_id="user-1")  # owned by user-1, not user-2

        def table_side_effect(name):
            m = MagicMock()
            if name == "memes":
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.maybe_single.return_value = chain
                chain.execute.return_value = _mock_response(meme)
                m.select.return_value = chain
            elif name == "tournament":
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.maybe_single.return_value = chain
                chain.execute.return_value = _mock_response({"id": "t-1", "status": "submission_open"})
                m.select.return_value = chain
            elif name == "tournament_admins":
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.maybe_single.return_value = chain
                chain.execute.return_value = _mock_response(None)
                m.select.return_value = chain
            return m
        mock_sb.table.side_effect = table_side_effect

        resp = client.delete("/api/memes/meme-1?tournament_id=t-1")
        assert resp.status_code == 403
        assert "only delete your own" in resp.json()["detail"]

    @patch("app.routes.memes.supabase_admin")
    def test_admin_can_delete_any_meme(self, mock_sb, admin_client):
        """Tournament admin should be able to delete any meme."""
        client, user = admin_client
        meme = _make_meme(owner_id="user-1")  # owned by someone else

        def table_side_effect(name):
            m = MagicMock()
            if name == "memes":
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.maybe_single.return_value = chain
                chain.execute.return_value = _mock_response(meme)
                m.select.return_value = chain
                delete_chain = MagicMock()
                delete_chain.eq.return_value = delete_chain
                delete_chain.execute.return_value = _mock_response([])
                m.delete.return_value = delete_chain
            elif name == "tournament":
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.maybe_single.return_value = chain
                chain.execute.return_value = _mock_response({"id": "t-1", "status": "submission_open"})
                m.select.return_value = chain
            elif name == "tournament_admins":
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.maybe_single.return_value = chain
                chain.execute.return_value = _mock_response({"id": "admin-row"})
                m.select.return_value = chain
            return m
        mock_sb.table.side_effect = table_side_effect
        mock_sb.storage.from_.return_value.remove.return_value = None

        resp = client.delete("/api/memes/meme-1?tournament_id=t-1")
        assert resp.status_code == 200
        assert resp.json()["deleted_id"] == "meme-1"

    @patch("app.routes.memes.supabase_admin")
    def test_meme_not_found_returns_404(self, mock_sb, authed_client):
        """Deleting a non-existent meme should return 404."""
        client, _ = authed_client

        chain = MagicMock()
        chain.eq.return_value = chain
        chain.maybe_single.return_value = chain
        chain.execute.return_value = _mock_response(None)
        mock_sb.table.return_value.select.return_value = chain

        resp = client.delete("/api/memes/nonexistent?tournament_id=t-1")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    @patch("app.routes.memes.supabase_admin")
    def test_deletion_blocked_when_not_submission_open(self, mock_sb, authed_client):
        """Deleting a meme should fail when tournament is not in submission_open."""
        client, user = authed_client
        meme = _make_meme(owner_id=user["id"])

        def table_side_effect(name):
            m = MagicMock()
            if name == "memes":
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.maybe_single.return_value = chain
                chain.execute.return_value = _mock_response(meme)
                m.select.return_value = chain
            elif name == "tournament":
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.maybe_single.return_value = chain
                chain.execute.return_value = _mock_response({"id": "t-1", "status": "voting_open"})
                m.select.return_value = chain
            return m
        mock_sb.table.side_effect = table_side_effect

        resp = client.delete("/api/memes/meme-1?tournament_id=t-1")
        assert resp.status_code == 400
        assert "submissions are open" in resp.json()["detail"].lower()

    @patch("app.routes.memes.verify_membership")
    @patch("app.routes.memes.supabase_admin")
    def test_resubmit_after_delete(self, mock_sb, mock_verify, authed_client):
        """After deleting a meme, user's count should drop, allowing resubmission."""
        client, user = authed_client

        # Simulate: user had 2, deleted 1, now count=1 — upload should succeed
        def table_side_effect(name):
            m = MagicMock()
            if name == "tournament":
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.maybe_single.return_value = chain
                chain.execute.return_value = _mock_response({
                    "id": "t-1",
                    "status": "submission_open",
                })
                m.select.return_value = chain
            elif name == "memes":
                chain = MagicMock()
                chain.eq.return_value = chain
                # Count: 1 meme remaining after deletion
                chain.execute.return_value = _mock_response([], count=1)
                m.select.return_value = chain
                ins = MagicMock()
                ins.execute.return_value = _mock_response([{
                    "id": "new-meme",
                    "owner_id": user["id"],
                    "tournament_id": "t-1",
                    "title": "Replacement",
                    "image_url": "http://example.com/meme.png",
                }])
                m.insert.return_value = ins
            return m
        mock_sb.table.side_effect = table_side_effect
        mock_sb.storage.from_.return_value.upload.return_value = None

        import io
        resp = client.post(
            "/api/memes/upload",
            data={"title": "Replacement", "tournament_id": "t-1"},
            files={"file": ("test.png", io.BytesIO(b"fake image"), "image/png")},
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "Replacement"
