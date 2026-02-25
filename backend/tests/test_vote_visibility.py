"""Tests for vote count visibility rules.

Non-admin users should NOT see vote counts during active voting.
Admins can always see counts. Everyone can see counts after matchup is complete.
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


@pytest.fixture
def member_client():
    """Client with auth bypassed — regular tournament member."""
    user = _fake_user()
    user["tournament_role"] = "member"

    async def override(request=None):
        return user

    from app.auth import get_current_user, require_tournament_member
    app.dependency_overrides[get_current_user] = override
    app.dependency_overrides[require_tournament_member] = override
    client = TestClient(app)
    yield client, user
    app.dependency_overrides.clear()


@pytest.fixture
def admin_client():
    """Client with auth bypassed — tournament admin."""
    user = _fake_user(user_id="user-admin", email="admin@example.com")
    user["tournament_role"] = "owner"

    async def override_user(request=None):
        return user

    async def override_admin(request=None):
        return user

    from app.auth import get_current_user, require_tournament_admin, require_tournament_member
    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[require_tournament_admin] = override_admin
    app.dependency_overrides[require_tournament_member] = override_admin
    client = TestClient(app)
    yield client, user
    app.dependency_overrides.clear()


# ============================================================================
# Tests: /voting/matchup/{id}/results
# ============================================================================

class TestMatchupResultsVisibility:
    @patch("app.routes.voting._get_tournament_from_matchup", return_value="t-1")
    @patch("app.routes.voting.verify_membership")
    @patch("app.routes.voting.supabase_admin")
    def test_non_admin_cannot_see_results_during_voting(
        self, mock_sb, mock_verify, mock_get_t, member_client
    ):
        """Regular member should NOT see vote counts while matchup is voting."""
        client, user = member_client

        def table_side_effect(name):
            m = MagicMock()
            if name == "matchups":
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.single.return_value = chain
                chain.execute.return_value = _mock_response({
                    "meme_a_id": "meme-a",
                    "meme_b_id": "meme-b",
                    "status": "voting",
                    "winner_id": None,
                })
                m.select.return_value = chain
            elif name == "tournament_admins":
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.maybe_single.return_value = chain
                chain.execute.return_value = _mock_response(None)
                m.select.return_value = chain
            return m
        mock_sb.table.side_effect = table_side_effect

        resp = client.get("/api/voting/matchup/m1/results")
        assert resp.status_code == 200
        result = resp.json()
        assert result["can_see_results"] is False
        assert "votes_a" not in result

    @patch("app.routes.voting._get_tournament_from_matchup", return_value="t-1")
    @patch("app.routes.voting.verify_membership")
    @patch("app.routes.voting.supabase_admin")
    def test_non_admin_can_see_results_after_complete(
        self, mock_sb, mock_verify, mock_get_t, member_client
    ):
        """Regular member should see vote counts once matchup is complete."""
        client, user = member_client

        def table_side_effect(name):
            m = MagicMock()
            if name == "matchups":
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.single.return_value = chain
                chain.execute.return_value = _mock_response({
                    "meme_a_id": "meme-a",
                    "meme_b_id": "meme-b",
                    "status": "complete",
                    "winner_id": "meme-a",
                })
                m.select.return_value = chain
            elif name == "tournament_admins":
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.maybe_single.return_value = chain
                chain.execute.return_value = _mock_response(None)
                m.select.return_value = chain
            elif name == "votes":
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.execute.return_value = _mock_response([
                    {"meme_id": "meme-a"},
                    {"meme_id": "meme-a"},
                    {"meme_id": "meme-b"},
                ])
                m.select.return_value = chain
            return m
        mock_sb.table.side_effect = table_side_effect

        resp = client.get("/api/voting/matchup/m1/results")
        assert resp.status_code == 200
        result = resp.json()
        assert result["can_see_results"] is True
        assert result["votes_a"] == 2
        assert result["votes_b"] == 1

    @patch("app.routes.voting._get_tournament_from_matchup", return_value="t-1")
    @patch("app.routes.voting.verify_membership")
    @patch("app.routes.voting.supabase_admin")
    def test_admin_can_see_results_during_voting(
        self, mock_sb, mock_verify, mock_get_t, member_client
    ):
        """Admin should see vote counts even while matchup is still voting."""
        client, user = member_client

        def table_side_effect(name):
            m = MagicMock()
            if name == "matchups":
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.single.return_value = chain
                chain.execute.return_value = _mock_response({
                    "meme_a_id": "meme-a",
                    "meme_b_id": "meme-b",
                    "status": "voting",
                    "winner_id": None,
                })
                m.select.return_value = chain
            elif name == "tournament_admins":
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.maybe_single.return_value = chain
                # User IS an admin
                chain.execute.return_value = _mock_response({"id": "admin-row"})
                m.select.return_value = chain
            elif name == "votes":
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.execute.return_value = _mock_response([
                    {"meme_id": "meme-a"},
                    {"meme_id": "meme-b"},
                ])
                m.select.return_value = chain
            return m
        mock_sb.table.side_effect = table_side_effect

        resp = client.get("/api/voting/matchup/m1/results")
        assert resp.status_code == 200
        result = resp.json()
        assert result["can_see_results"] is True
        assert result["votes_a"] == 1
        assert result["votes_b"] == 1


# ============================================================================
# Tests: /tournament/{id}/rounds/{num}/matchups vote count visibility
# ============================================================================

class TestRoundMatchupsVoteVisibility:
    @patch("app.routes.tournament.supabase_admin")
    def test_member_gets_null_votes_for_voting_matchup(self, mock_sb, member_client):
        """Regular member should get null vote counts for matchups in voting status."""
        client, _ = member_client

        def table_side_effect(name):
            m = MagicMock()
            if name == "rounds":
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.maybe_single.return_value = chain
                chain.execute.return_value = _mock_response({"id": "r1", "status": "voting"})
                m.select.return_value = chain
            elif name == "matchups":
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.order.return_value = chain
                chain.range.return_value = chain
                chain.execute.return_value = _mock_response([{
                    "id": "m1",
                    "meme_a_id": "meme-a",
                    "meme_b_id": "meme-b",
                    "status": "voting",
                    "winner_id": None,
                    "meme_a": {"id": "meme-a", "title": "A"},
                    "meme_b": {"id": "meme-b", "title": "B"},
                }])
                # count query
                count_chain = MagicMock()
                count_chain.eq.return_value = count_chain
                count_chain.execute.return_value = _mock_response([], count=1)
                m.select.side_effect = [chain, count_chain]
            return m
        mock_sb.table.side_effect = table_side_effect

        resp = client.get("/api/tournament/t-1/rounds/1/matchups")
        assert resp.status_code == 200
        matchup = resp.json()["matchups"][0]
        assert matchup["votes_a"] is None
        assert matchup["votes_b"] is None
        assert matchup["total_votes"] is None

    @patch("app.routes.tournament.supabase_admin")
    def test_admin_gets_real_votes_for_voting_matchup(self, mock_sb, admin_client):
        """Admin should get real vote counts even for matchups still in voting."""
        client, _ = admin_client

        def table_side_effect(name):
            m = MagicMock()
            if name == "rounds":
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.maybe_single.return_value = chain
                chain.execute.return_value = _mock_response({"id": "r1", "status": "voting"})
                m.select.return_value = chain
            elif name == "matchups":
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.order.return_value = chain
                chain.range.return_value = chain
                chain.execute.return_value = _mock_response([{
                    "id": "m1",
                    "meme_a_id": "meme-a",
                    "meme_b_id": "meme-b",
                    "status": "voting",
                    "winner_id": None,
                    "meme_a": {"id": "meme-a", "title": "A"},
                    "meme_b": {"id": "meme-b", "title": "B"},
                }])
                count_chain = MagicMock()
                count_chain.eq.return_value = count_chain
                count_chain.execute.return_value = _mock_response([], count=1)
                m.select.side_effect = [chain, count_chain]
            elif name == "votes":
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.execute.return_value = _mock_response([
                    {"meme_id": "meme-a"},
                    {"meme_id": "meme-a"},
                    {"meme_id": "meme-b"},
                ])
                m.select.return_value = chain
            return m
        mock_sb.table.side_effect = table_side_effect

        resp = client.get("/api/tournament/t-1/rounds/1/matchups")
        assert resp.status_code == 200
        matchup = resp.json()["matchups"][0]
        assert matchup["votes_a"] == 2
        assert matchup["votes_b"] == 1
        assert matchup["total_votes"] == 3

    @patch("app.routes.tournament.supabase_admin")
    def test_member_gets_real_votes_for_complete_matchup(self, mock_sb, member_client):
        """Regular member should get real vote counts for completed matchups."""
        client, _ = member_client

        def table_side_effect(name):
            m = MagicMock()
            if name == "rounds":
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.maybe_single.return_value = chain
                chain.execute.return_value = _mock_response({"id": "r1", "status": "complete"})
                m.select.return_value = chain
            elif name == "matchups":
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.order.return_value = chain
                chain.range.return_value = chain
                chain.execute.return_value = _mock_response([{
                    "id": "m1",
                    "meme_a_id": "meme-a",
                    "meme_b_id": "meme-b",
                    "status": "complete",
                    "winner_id": "meme-a",
                    "meme_a": {"id": "meme-a", "title": "A"},
                    "meme_b": {"id": "meme-b", "title": "B"},
                }])
                count_chain = MagicMock()
                count_chain.eq.return_value = count_chain
                count_chain.execute.return_value = _mock_response([], count=1)
                m.select.side_effect = [chain, count_chain]
            elif name == "votes":
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.execute.return_value = _mock_response([
                    {"meme_id": "meme-a"},
                    {"meme_id": "meme-b"},
                ])
                m.select.return_value = chain
            return m
        mock_sb.table.side_effect = table_side_effect

        resp = client.get("/api/tournament/t-1/rounds/1/matchups")
        assert resp.status_code == 200
        matchup = resp.json()["matchups"][0]
        assert matchup["votes_a"] == 1
        assert matchup["votes_b"] == 1
        assert matchup["total_votes"] == 2
