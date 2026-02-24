"""Tests for tournament-scoped operations.

Verifies that meme counts, bracket seeding, uploads, and queries
are correctly scoped to individual tournaments (no cross-contamination).
"""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.services.bracket import next_power_of_2


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
def authed_client():
    """Client with auth bypassed as a tournament member."""
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
    """Client with tournament admin auth bypassed."""
    user = _fake_user()
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
# Test: Meme upload scoped per tournament
# ============================================================================

class TestMemeUploadScoping:
    @patch("app.routes.memes.verify_membership")
    @patch("app.routes.memes.supabase_admin")
    def test_meme_limit_scoped_to_tournament(self, mock_sb, mock_verify, authed_client):
        """User at 2-meme limit in tournament A should still be able to submit to tournament B."""
        client, user = authed_client

        call_sequence = []

        def table_side_effect(name):
            m = MagicMock()
            if name == "tournament":
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.maybe_single.return_value = chain
                chain.execute.return_value = _mock_response({
                    "id": "tournament-B",
                    "status": "submission_open",
                })
                m.select.return_value = chain
            elif name == "memes":
                chain = MagicMock()
                chain.eq.return_value = chain
                # Count query: 0 memes in tournament B
                chain.execute.return_value = _mock_response([], count=0)
                m.select.return_value = chain
                # Insert
                ins = MagicMock()
                ins.execute.return_value = _mock_response([{
                    "id": "new-meme",
                    "owner_id": user["id"],
                    "tournament_id": "tournament-B",
                    "title": "Test Meme",
                    "image_url": "http://example.com/meme.png",
                }])
                m.insert.return_value = ins
            return m
        mock_sb.table.side_effect = table_side_effect

        # Mock storage
        mock_sb.storage.from_.return_value.upload.return_value = None

        import io
        resp = client.post(
            "/api/memes/upload",
            data={"title": "Test Meme", "tournament_id": "tournament-B"},
            files={"file": ("test.png", io.BytesIO(b"fake image data"), "image/png")},
        )
        assert resp.status_code == 200
        assert resp.json()["tournament_id"] == "tournament-B"

    @patch("app.routes.memes.verify_membership")
    @patch("app.routes.memes.supabase_admin")
    def test_meme_limit_blocks_at_2_for_same_tournament(self, mock_sb, mock_verify, authed_client):
        """User with 2 memes in tournament A should be blocked from submitting again to tournament A."""
        client, user = authed_client

        def table_side_effect(name):
            m = MagicMock()
            if name == "tournament":
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.maybe_single.return_value = chain
                chain.execute.return_value = _mock_response({
                    "id": "tournament-A",
                    "status": "submission_open",
                })
                m.select.return_value = chain
            elif name == "memes":
                chain = MagicMock()
                chain.eq.return_value = chain
                # Already at limit: 2 memes
                chain.execute.return_value = _mock_response([], count=2)
                m.select.return_value = chain
            return m
        mock_sb.table.side_effect = table_side_effect

        import io
        resp = client.post(
            "/api/memes/upload",
            data={"title": "Too Many", "tournament_id": "tournament-A"},
            files={"file": ("test.png", io.BytesIO(b"fake"), "image/png")},
        )
        assert resp.status_code == 400
        assert "already submitted" in resp.json()["detail"]

    @patch("app.routes.memes.supabase_admin")
    def test_upload_requires_tournament_id(self, mock_sb, authed_client):
        """Upload without tournament_id should fail with 422."""
        client, _ = authed_client
        import io
        resp = client.post(
            "/api/memes/upload",
            data={"title": "No Tournament"},
            files={"file": ("test.png", io.BytesIO(b"fake"), "image/png")},
        )
        assert resp.status_code == 422  # Validation error — tournament_id is required

    @patch("app.routes.memes.supabase_admin")
    def test_upload_closed_tournament_rejected(self, mock_sb, authed_client):
        """Cannot submit to a tournament that's not in submission_open."""
        client, _ = authed_client

        def table_side_effect(name):
            m = MagicMock()
            if name == "tournament":
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.maybe_single.return_value = chain
                chain.execute.return_value = _mock_response({
                    "id": "tournament-C",
                    "status": "voting_open",
                })
                m.select.return_value = chain
            return m
        mock_sb.table.side_effect = table_side_effect

        import io
        resp = client.post(
            "/api/memes/upload",
            data={"title": "Late Meme", "tournament_id": "tournament-C"},
            files={"file": ("test.png", io.BytesIO(b"fake"), "image/png")},
        )
        assert resp.status_code == 400
        assert "not currently open" in resp.json()["detail"]


# ============================================================================
# Test: Meme listing scoped per tournament
# ============================================================================

class TestMemeListingScoping:
    @patch("app.routes.memes.verify_membership")
    @patch("app.routes.memes.supabase_admin")
    def test_list_memes_with_tournament_filter(self, mock_sb, mock_verify, authed_client):
        """GET /memes?tournament_id= should filter by tournament."""
        client, _ = authed_client

        memes = [
            {"id": "m1", "tournament_id": "t-A", "title": "A meme"},
        ]

        chain = MagicMock()
        chain.eq.return_value = chain
        chain.order.return_value = chain
        chain.execute.return_value = _mock_response(memes)
        mock_sb.table.return_value.select.return_value = chain

        resp = client.get("/api/memes/?tournament_id=t-A")
        assert resp.status_code == 200
        result = resp.json()
        assert len(result) == 1
        assert result[0]["tournament_id"] == "t-A"

    @patch("app.routes.memes.verify_membership")
    @patch("app.routes.memes.supabase_admin")
    def test_my_memes_with_tournament_filter(self, mock_sb, mock_verify, authed_client):
        client, user = authed_client

        memes = [{"id": "m2", "tournament_id": "t-B", "title": "My meme", "owner_id": user["id"]}]

        def table_side_effect(name):
            m = MagicMock()
            if name == "memes":
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.order.return_value = chain
                chain.execute.return_value = _mock_response(memes)
                m.select.return_value = chain
            elif name == "matchups":
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.execute.return_value = _mock_response([])
                m.select.return_value = chain
            return m
        mock_sb.table.side_effect = table_side_effect

        resp = client.get("/api/memes/mine?tournament_id=t-B")
        assert resp.status_code == 200
        result = resp.json()
        assert len(result) == 1


# ============================================================================
# Test: Bracket seeding scoped per tournament
# ============================================================================

class TestBracketSeedingScoping:
    @patch("app.services.bracket.supabase_admin")
    def test_seed_bracket_uses_tournament_memes_only(self, mock_sb):
        """seed_bracket() should only fetch memes with matching tournament_id."""
        from app.services.bracket import seed_bracket

        # 4 memes for this tournament
        memes = [{"id": f"meme-{i}"} for i in range(4)]

        call_tracker = {"table_calls": []}

        def table_side_effect(name):
            call_tracker["table_calls"].append(name)
            m = MagicMock()
            if name == "memes":
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.execute.return_value = _mock_response(memes)
                m.select.return_value = chain
            elif name == "tournament":
                update = MagicMock()
                update.eq.return_value = update
                update.execute.return_value = _mock_response([])
                m.update.return_value = update
            elif name == "rounds":
                ins = MagicMock()
                ins.execute.return_value = _mock_response([{"id": "round-1"}])
                m.insert.return_value = ins
            elif name == "matchups":
                ins = MagicMock()
                ins.execute.return_value = _mock_response([])
                m.insert.return_value = ins
            return m
        mock_sb.table.side_effect = table_side_effect

        result = seed_bracket("tournament-X")
        assert result["bracket_size"] == 4  # next_power_of_2(4) = 4
        assert result["num_byes"] == 0
        assert result["total_rounds"] == 2

        # Verify memes table was queried
        assert "memes" in call_tracker["table_calls"]

    @patch("app.services.bracket.supabase_admin")
    def test_seed_bracket_too_few_memes_raises(self, mock_sb):
        """seed_bracket() with < 2 memes should raise ValueError."""
        from app.services.bracket import seed_bracket

        chain = MagicMock()
        chain.eq.return_value = chain
        chain.execute.return_value = _mock_response([{"id": "only-one"}])
        mock_sb.table.return_value.select.return_value = chain

        with pytest.raises(ValueError, match="at least 2 memes"):
            seed_bracket("tournament-lonely")


# ============================================================================
# Test: Tournament list annotated with user roles
# ============================================================================

class TestTournamentListScoping:
    @patch("app.routes.tournament.supabase_admin")
    def test_tournament_list_includes_user_role(self, mock_sb, authed_client):
        """GET /tournament/list should annotate each tournament with user's role."""
        client, user = authed_client

        tournaments = [
            {"id": "t-1", "name": "Tournament A", "status": "voting_open", "created_at": "2026-01-01T00:00:00Z"},
            {"id": "t-2", "name": "Tournament B", "status": "complete", "created_at": "2026-01-02T00:00:00Z"},
            {"id": "t-3", "name": "Tournament C", "status": "submission_open", "created_at": "2026-01-03T00:00:00Z"},
        ]

        admin_roles = [
            {"tournament_id": "t-1", "role": "owner"},
            {"tournament_id": "t-3", "role": "admin"},
        ]

        member_rows = [
            {"tournament_id": "t-2"},
        ]

        def table_side_effect(name):
            m = MagicMock()
            if name == "tournament_admins":
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.execute.return_value = _mock_response(admin_roles)
                m.select.return_value = chain
            elif name == "tournament_members":
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.execute.return_value = _mock_response(member_rows)
                m.select.return_value = chain
            elif name == "tournament":
                chain = MagicMock()
                chain.in_.return_value = chain
                chain.order.return_value = chain
                chain.execute.return_value = _mock_response(tournaments)
                m.select.return_value = chain
            return m
        mock_sb.table.side_effect = table_side_effect

        resp = client.get("/api/tournament/list")
        assert resp.status_code == 200
        result = resp.json()

        assert len(result) == 3
        role_map = {t["id"]: t.get("user_role") for t in result}
        assert role_map["t-1"] == "owner"
        assert role_map["t-2"] == "member"
        assert role_map["t-3"] == "admin"


# ============================================================================
# Test: Round and bracket queries scoped per tournament
# ============================================================================

class TestRoundAndBracketScoping:
    @patch("app.routes.tournament.supabase_admin")
    def test_get_rounds_uses_tournament_id(self, mock_sb, authed_client):
        """GET /tournament/{id}/rounds should filter by tournament_id."""
        client, _ = authed_client

        rounds = [
            {"id": "r1", "round_number": 1, "status": "complete", "tournament_id": "t-1"},
            {"id": "r2", "round_number": 2, "status": "voting", "tournament_id": "t-1"},
        ]

        chain = MagicMock()
        chain.eq.return_value = chain
        chain.order.return_value = chain
        chain.execute.return_value = _mock_response(rounds)
        mock_sb.table.return_value.select.return_value = chain

        resp = client.get("/api/tournament/t-1/rounds")
        assert resp.status_code == 200
        result = resp.json()
        assert len(result) == 2
        assert result[0]["round_number"] == 1
        assert result[1]["round_number"] == 2

    @patch("app.routes.tournament.supabase_admin")
    def test_get_bracket_filters_by_tournament(self, mock_sb, authed_client):
        """GET /tournament/{id}/bracket should return bracket for specific tournament."""
        client, _ = authed_client

        t_data = {"id": "t-1", "name": "Test", "status": "voting_open", "total_rounds": 2}

        def table_side_effect(name):
            m = MagicMock()
            if name == "tournament":
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.maybe_single.return_value = chain
                chain.execute.return_value = _mock_response(t_data)
                m.select.return_value = chain
            elif name == "rounds":
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.order.return_value = chain
                chain.execute.return_value = _mock_response([
                    {"id": "r1", "round_number": 1, "status": "complete", "tournament_id": "t-1"},
                ])
                m.select.return_value = chain
            elif name == "matchups":
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.order.return_value = chain
                chain.execute.return_value = _mock_response([
                    {"id": "m1", "meme_a_id": "a", "meme_b_id": "b", "winner_id": "a",
                     "status": "complete", "position": 0, "next_matchup_id": None,
                     "meme_a": {"id": "a", "title": "A", "image_url": "url", "owner_id": "u1"},
                     "meme_b": {"id": "b", "title": "B", "image_url": "url", "owner_id": "u2"}},
                ])
                m.select.return_value = chain
            return m
        mock_sb.table.side_effect = table_side_effect

        resp = client.get("/api/tournament/t-1/bracket")
        assert resp.status_code == 200
        result = resp.json()
        assert result["tournament"]["id"] == "t-1"
        assert len(result["rounds"]) == 1
        assert len(result["rounds"][0]["matchups"]) == 1

    @patch("app.routes.tournament.supabase_admin")
    def test_get_nonexistent_tournament_returns_404(self, mock_sb, authed_client):
        """GET /tournament/{id} for nonexistent tournament returns 404 (member bypassed)."""
        client, _ = authed_client

        chain = MagicMock()
        chain.eq.return_value = chain
        chain.maybe_single.return_value = chain
        chain.execute.return_value = _mock_response(None)
        mock_sb.table.return_value.select.return_value = chain

        resp = client.get("/api/tournament/nonexistent-id")
        # With require_tournament_member overridden, we reach the 404 path
        assert resp.status_code == 404


# ============================================================================
# Test: Close matchup vote counting
# ============================================================================

class TestCloseMatchupVoteCounting:
    @patch("app.routes.admin.supabase_admin")
    def test_close_matchup_determines_winner(self, mock_sb, admin_client):
        """Closing a matchup should count votes and pick the winner."""
        client, _ = admin_client

        matchup_data = {
            "id": "m1", "meme_a_id": "meme-a", "meme_b_id": "meme-b",
            "status": "voting", "winner_id": None,
        }
        votes = [
            {"meme_id": "meme-a"},
            {"meme_id": "meme-a"},
            {"meme_id": "meme-b"},
        ]

        def table_side_effect(name):
            m = MagicMock()
            if name == "matchups":
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.single.return_value = chain
                chain.execute.return_value = _mock_response(matchup_data)
                m.select.return_value = chain
                update = MagicMock()
                update.eq.return_value = update
                update.execute.return_value = _mock_response([])
                m.update.return_value = update
            elif name == "votes":
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.execute.return_value = _mock_response(votes)
                m.select.return_value = chain
            return m
        mock_sb.table.side_effect = table_side_effect

        resp = client.post("/api/admin/tournament/t-1/matchup/m1/close")
        assert resp.status_code == 200
        result = resp.json()
        assert result["winner_id"] == "meme-a"
        assert result["votes_a"] == 2
        assert result["votes_b"] == 1

    @patch("app.routes.admin.supabase_admin")
    def test_close_matchup_tie_returns_tie(self, mock_sb, admin_client):
        """Closing a tied matchup should return tie indication."""
        client, _ = admin_client

        matchup_data = {
            "id": "m1", "meme_a_id": "meme-a", "meme_b_id": "meme-b",
            "status": "voting", "winner_id": None,
        }
        votes = [
            {"meme_id": "meme-a"},
            {"meme_id": "meme-b"},
        ]

        def table_side_effect(name):
            m = MagicMock()
            if name == "matchups":
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.single.return_value = chain
                chain.execute.return_value = _mock_response(matchup_data)
                m.select.return_value = chain
            elif name == "votes":
                chain = MagicMock()
                chain.eq.return_value = chain
                chain.execute.return_value = _mock_response(votes)
                m.select.return_value = chain
            return m
        mock_sb.table.side_effect = table_side_effect

        resp = client.post("/api/admin/tournament/t-1/matchup/m1/close")
        assert resp.status_code == 200
        result = resp.json()
        assert result["tie"] is True
        assert result["votes_a"] == 1
        assert result["votes_b"] == 1


# ============================================================================
# Test: Seeding blocks on wrong status
# ============================================================================

class TestSeedingStatusCheck:
    @patch("app.routes.admin.supabase_admin")
    def test_seed_fails_if_not_submission_open(self, mock_sb, admin_client):
        """Seeding should fail if tournament is not in submission_open status."""
        client, _ = admin_client

        chain = MagicMock()
        chain.eq.return_value = chain
        chain.single.return_value = chain
        chain.execute.return_value = _mock_response({
            "id": "t-1", "status": "voting_open",
        })
        mock_sb.table.return_value.select.return_value = chain

        resp = client.post("/api/admin/tournament/t-1/seed")
        assert resp.status_code == 400
        assert "not in submission phase" in resp.json()["detail"]
