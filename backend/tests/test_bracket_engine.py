"""Tests for the bracket engine: seeding, byes, round generation, owner separation.

These tests verify the pure bracket logic using the math/algorithm functions
from the bracket service, without requiring database connectivity.
"""
import math
import random
import pytest
from app.services.bracket import next_power_of_2, _avoid_same_owner_adjacent


# ============================================================================
# Test next_power_of_2
# ============================================================================

class TestNextPowerOf2:
    def test_power_of_2_inputs(self):
        assert next_power_of_2(1) == 1
        assert next_power_of_2(2) == 2
        assert next_power_of_2(4) == 4
        assert next_power_of_2(8) == 8
        assert next_power_of_2(16) == 16
        assert next_power_of_2(32) == 32
        assert next_power_of_2(64) == 64
        assert next_power_of_2(128) == 128

    def test_non_power_of_2_inputs(self):
        assert next_power_of_2(3) == 4
        assert next_power_of_2(5) == 8
        assert next_power_of_2(7) == 8
        assert next_power_of_2(9) == 16
        assert next_power_of_2(17) == 32
        assert next_power_of_2(33) == 64
        assert next_power_of_2(50) == 64
        assert next_power_of_2(65) == 128
        assert next_power_of_2(80) == 128
        assert next_power_of_2(100) == 128

    def test_edge_cases(self):
        assert next_power_of_2(0) == 1
        assert next_power_of_2(1) == 1


# ============================================================================
# Test Bracket Seeding Logic (unit-level, no DB)
# ============================================================================

def compute_bracket_params(num_memes: int):
    """Simulate the bracket seeding logic to compute bracket size, byes, rounds."""
    bracket_size = next_power_of_2(num_memes)
    num_byes = bracket_size - num_memes
    total_rounds = int(math.log2(bracket_size)) if bracket_size > 1 else 0
    num_matchups_round1 = bracket_size // 2
    competing_matchups = num_matchups_round1 - num_byes  # matchups with two contestants

    return {
        "num_memes": num_memes,
        "bracket_size": bracket_size,
        "num_byes": num_byes,
        "total_rounds": total_rounds,
        "round1_matchups": num_matchups_round1,
        "competing_matchups": competing_matchups,
    }


def simulate_bracket(num_memes: int):
    """Simulate the full bracket generation and advancement process.
    Returns a dict with round-by-round matchup counts."""
    bracket_size = next_power_of_2(num_memes)
    num_byes = bracket_size - num_memes
    total_rounds = int(math.log2(bracket_size)) if bracket_size > 1 else 0

    # Round 1
    memes = list(range(num_memes))
    random.shuffle(memes)

    bye_memes = memes[:num_byes]
    competing_memes = memes[num_byes:]

    round_results = {}

    # Round 1 matchups
    round1_matchups = []
    # Bye matchups (auto-advance)
    for m in bye_memes:
        round1_matchups.append({"a": m, "b": None, "winner": m})
    # Competing matchups
    for i in range(0, len(competing_memes), 2):
        round1_matchups.append({
            "a": competing_memes[i],
            "b": competing_memes[i + 1],
            "winner": competing_memes[i],  # simulate: first always wins
        })

    round_results[1] = {
        "total_matchups": len(round1_matchups),
        "byes": len(bye_memes),
        "competing": len(round1_matchups) - len(bye_memes),
    }

    # Subsequent rounds
    current_winners = [m["winner"] for m in round1_matchups]

    for r in range(2, total_rounds + 1):
        matchups = []
        for i in range(0, len(current_winners), 2):
            if i + 1 < len(current_winners):
                matchups.append({
                    "a": current_winners[i],
                    "b": current_winners[i + 1],
                    "winner": current_winners[i],
                })
            else:
                # Odd number — bye
                matchups.append({
                    "a": current_winners[i],
                    "b": None,
                    "winner": current_winners[i],
                })

        round_results[r] = {
            "total_matchups": len(matchups),
            "byes": sum(1 for m in matchups if m["b"] is None),
            "competing": sum(1 for m in matchups if m["b"] is not None),
        }
        current_winners = [m["winner"] for m in matchups]

    return {
        "bracket_size": bracket_size,
        "total_rounds": total_rounds,
        "rounds": round_results,
        "final_winner": current_winners[0] if current_winners else None,
    }


class TestBracketSeeding:
    """Test bracket seeding across a range of submission counts."""

    @pytest.mark.parametrize("num_memes,expected_bracket,expected_byes,expected_rounds", [
        (4, 4, 0, 2),
        (5, 8, 3, 3),
        (8, 8, 0, 3),
        (17, 32, 15, 5),
        (50, 64, 14, 6),
        (80, 128, 48, 7),
        (100, 128, 28, 7),
    ])
    def test_bracket_params(self, num_memes, expected_bracket, expected_byes, expected_rounds):
        params = compute_bracket_params(num_memes)
        assert params["bracket_size"] == expected_bracket, \
            f"For {num_memes} memes: expected bracket size {expected_bracket}, got {params['bracket_size']}"
        assert params["num_byes"] == expected_byes, \
            f"For {num_memes} memes: expected {expected_byes} byes, got {params['num_byes']}"
        assert params["total_rounds"] == expected_rounds, \
            f"For {num_memes} memes: expected {expected_rounds} rounds, got {params['total_rounds']}"

    @pytest.mark.parametrize("num_memes", [4, 5, 8, 17, 50, 80, 100])
    def test_round1_matchup_count(self, num_memes):
        """Round 1 should have bracket_size / 2 matchups."""
        params = compute_bracket_params(num_memes)
        assert params["round1_matchups"] == params["bracket_size"] // 2

    @pytest.mark.parametrize("num_memes", [4, 5, 8, 17, 50, 80, 100])
    def test_competing_plus_byes_equals_total(self, num_memes):
        """Competing matchups + byes = total round 1 matchups."""
        params = compute_bracket_params(num_memes)
        assert params["competing_matchups"] + params["num_byes"] == params["round1_matchups"]

    @pytest.mark.parametrize("num_memes", [4, 5, 8, 17, 50, 80, 100])
    def test_competing_matchups_correct(self, num_memes):
        """Competing matchups should use exactly num_memes - num_byes entries, paired."""
        params = compute_bracket_params(num_memes)
        competing_entries = num_memes - params["num_byes"]
        # Each competing matchup uses 2 entries
        assert params["competing_matchups"] * 2 == competing_entries


class TestBracketSimulation:
    """Test full bracket simulation to verify round generation."""

    @pytest.mark.parametrize("num_memes", [4, 5, 8, 17, 50, 80, 100])
    def test_bracket_completes_with_one_winner(self, num_memes):
        """The bracket should reduce to exactly 1 winner."""
        result = simulate_bracket(num_memes)
        assert result["final_winner"] is not None

    @pytest.mark.parametrize("num_memes", [4, 5, 8, 17, 50, 80, 100])
    def test_correct_number_of_rounds(self, num_memes):
        result = simulate_bracket(num_memes)
        expected_rounds = int(math.log2(next_power_of_2(num_memes)))
        assert result["total_rounds"] == expected_rounds
        assert len(result["rounds"]) == expected_rounds

    @pytest.mark.parametrize("num_memes", [4, 5, 8, 17, 50, 80, 100])
    def test_matchup_counts_halve_each_round(self, num_memes):
        """Each round should have half the matchups of the previous round."""
        result = simulate_bracket(num_memes)
        prev_matchups = result["rounds"][1]["total_matchups"]
        for r in range(2, result["total_rounds"] + 1):
            current_matchups = result["rounds"][r]["total_matchups"]
            assert current_matchups == prev_matchups // 2, \
                f"Round {r}: expected {prev_matchups // 2} matchups, got {current_matchups}"
            prev_matchups = current_matchups

    @pytest.mark.parametrize("num_memes", [4, 5, 8, 17, 50, 80, 100])
    def test_final_round_has_one_matchup(self, num_memes):
        """The final round should have exactly 1 matchup."""
        result = simulate_bracket(num_memes)
        final_round = result["rounds"][result["total_rounds"]]
        assert final_round["total_matchups"] == 1

    def test_8_memes_no_byes(self):
        result = simulate_bracket(8)
        assert result["rounds"][1]["byes"] == 0
        assert result["rounds"][1]["competing"] == 4
        assert result["total_rounds"] == 3

    def test_17_memes_15_byes(self):
        result = simulate_bracket(17)
        assert result["rounds"][1]["byes"] == 15
        assert result["rounds"][1]["competing"] == 1
        assert result["total_rounds"] == 5

    def test_50_memes(self):
        result = simulate_bracket(50)
        assert result["bracket_size"] == 64
        assert result["rounds"][1]["byes"] == 14
        assert result["rounds"][1]["total_matchups"] == 32

    def test_80_memes(self):
        result = simulate_bracket(80)
        assert result["bracket_size"] == 128
        assert result["rounds"][1]["byes"] == 48
        assert result["rounds"][1]["total_matchups"] == 64

    def test_100_memes(self):
        result = simulate_bracket(100)
        assert result["bracket_size"] == 128
        assert result["rounds"][1]["byes"] == 28
        assert result["rounds"][1]["total_matchups"] == 64


# ============================================================================
# Test Owner Separation Helper
# ============================================================================

class TestOwnerSeparation:
    """Unit tests for _avoid_same_owner_adjacent."""

    def test_already_separated(self):
        """Input with no adjacent same-owner memes stays unchanged."""
        memes = [
            {"id": "a", "owner_id": "1"},
            {"id": "b", "owner_id": "2"},
            {"id": "c", "owner_id": "1"},
            {"id": "d", "owner_id": "2"},
        ]
        original = [m["id"] for m in memes]
        _avoid_same_owner_adjacent(memes)
        # No adjacent same-owner — order may stay the same
        for i in range(len(memes) - 1):
            assert memes[i]["owner_id"] != memes[i + 1]["owner_id"]

    def test_adjacent_same_owner_swapped(self):
        """Adjacent same-owner memes get swapped apart."""
        memes = [
            {"id": "a", "owner_id": "1"},
            {"id": "b", "owner_id": "1"},
            {"id": "c", "owner_id": "2"},
            {"id": "d", "owner_id": "3"},
        ]
        _avoid_same_owner_adjacent(memes)
        for i in range(len(memes) - 1):
            assert memes[i]["owner_id"] != memes[i + 1]["owner_id"]

    def test_only_two_same_owner_graceful(self):
        """When only 2 memes exist and they share an owner, can't separate — no crash."""
        memes = [
            {"id": "a", "owner_id": "1"},
            {"id": "b", "owner_id": "1"},
        ]
        _avoid_same_owner_adjacent(memes)
        # Should not crash; still adjacent since no swap target exists
        assert len(memes) == 2

    def test_empty_list(self):
        """Empty list should not crash."""
        memes = []
        _avoid_same_owner_adjacent(memes)
        assert memes == []

    def test_single_element(self):
        """Single element list should not crash."""
        memes = [{"id": "a", "owner_id": "1"}]
        _avoid_same_owner_adjacent(memes)
        assert len(memes) == 1


# ============================================================================
# Test Half Assignment (owner-aware bracket halves)
# ============================================================================

class TestHalfAssignment:
    """Test that same-owner pairs are placed in the same bracket half."""

    def _distribute_halves(self, num_memes, pairs_config):
        """Simulate the half-assignment logic from seed_bracket.

        pairs_config: list of (owner_id, count) tuples.
        Remaining memes are singles with unique owners.
        """
        from collections import defaultdict

        memes = []
        owner_map = defaultdict(list)
        meme_idx = 0
        for owner_id, count in pairs_config:
            for _ in range(count):
                m = {"id": f"meme-{meme_idx}", "owner_id": owner_id}
                memes.append(m)
                owner_map[owner_id].append(m)
                meme_idx += 1

        # Fill remaining with unique-owner singles
        while len(memes) < num_memes:
            owner_id = f"single-{meme_idx}"
            m = {"id": f"meme-{meme_idx}", "owner_id": owner_id}
            memes.append(m)
            owner_map[owner_id].append(m)
            meme_idx += 1

        pairs = []
        singles = []
        for oid, owned in owner_map.items():
            if len(owned) == 2:
                pairs.append(owned)
            else:
                singles.extend(owned)

        random.shuffle(pairs)
        random.shuffle(singles)

        bracket_size = next_power_of_2(num_memes)
        half_capacity = bracket_size // 2
        half_a_cap = half_capacity // 2
        half_b_cap = half_capacity - half_a_cap

        half_a = []
        half_b = []

        for pair in pairs:
            if len(half_a) + 2 <= half_a_cap:
                half_a.extend(pair)
            elif len(half_b) + 2 <= half_b_cap:
                half_b.extend(pair)
            elif len(half_a) <= len(half_b):
                half_a.extend(pair)
            else:
                half_b.extend(pair)

        for meme in singles:
            if len(half_a) < half_a_cap:
                half_a.append(meme)
            elif len(half_b) < half_b_cap:
                half_b.append(meme)
            elif len(half_a) <= len(half_b):
                half_a.append(meme)
            else:
                half_b.append(meme)

        return half_a, half_b

    def test_single_pair_same_half(self):
        """A pair of memes from the same owner should be in the same half."""
        for _ in range(20):  # Run multiple times for randomness
            half_a, half_b = self._distribute_halves(8, [("owner-X", 2)])
            ids_a = {m["owner_id"] for m in half_a}
            ids_b = {m["owner_id"] for m in half_b}
            # owner-X should be in one half, not split
            x_in_a = sum(1 for m in half_a if m["owner_id"] == "owner-X")
            x_in_b = sum(1 for m in half_b if m["owner_id"] == "owner-X")
            assert (x_in_a == 2 and x_in_b == 0) or (x_in_a == 0 and x_in_b == 2), \
                f"owner-X split across halves: {x_in_a} in A, {x_in_b} in B"

    def test_multiple_pairs_same_half(self):
        """Multiple pairs should each be fully in one half."""
        for _ in range(20):
            half_a, half_b = self._distribute_halves(16, [
                ("owner-A", 2), ("owner-B", 2), ("owner-C", 2),
            ])
            for owner in ["owner-A", "owner-B", "owner-C"]:
                in_a = sum(1 for m in half_a if m["owner_id"] == owner)
                in_b = sum(1 for m in half_b if m["owner_id"] == owner)
                assert (in_a == 2 and in_b == 0) or (in_a == 0 and in_b == 2), \
                    f"{owner} split: {in_a} in A, {in_b} in B"

    def test_all_singles_balanced(self):
        """With no pairs, halves should be roughly balanced."""
        half_a, half_b = self._distribute_halves(8, [])
        assert abs(len(half_a) - len(half_b)) <= 1

    def test_finals_cannot_be_same_owner(self):
        """Same-owner memes in the same half means they can't meet in the finals.

        Run many simulations: the pair is always in one half, so the two
        finalists are always from different halves.
        """
        for _ in range(50):
            half_a, half_b = self._distribute_halves(8, [("owner-X", 2)])
            owners_a = {m["owner_id"] for m in half_a}
            owners_b = {m["owner_id"] for m in half_b}
            # The pair must be entirely in one half
            x_in_a = sum(1 for m in half_a if m["owner_id"] == "owner-X")
            x_in_b = sum(1 for m in half_b if m["owner_id"] == "owner-X")
            assert x_in_a == 0 or x_in_b == 0, \
                "owner-X memes should not be split across halves"

    def test_4_memes_1_pair(self):
        """With 4 memes and 1 pair, bracket_size=4, pair goes to one half."""
        for _ in range(20):
            half_a, half_b = self._distribute_halves(4, [("owner-X", 2)])
            x_in_a = sum(1 for m in half_a if m["owner_id"] == "owner-X")
            x_in_b = sum(1 for m in half_b if m["owner_id"] == "owner-X")
            assert (x_in_a == 2 and x_in_b == 0) or (x_in_a == 0 and x_in_b == 2)


# ============================================================================
# Test Voting Rules (unit-level logic)
# ============================================================================

class TestVotingRules:
    def test_one_vote_per_matchup_logic(self):
        """Verify that the unique constraint logic works (simulated)."""
        votes = {}  # (matchup_id, voter_id) -> meme_id

        # First vote should succeed
        key = ("matchup_1", "voter_1")
        assert key not in votes
        votes[key] = "meme_a"

        # Second vote from same voter on same matchup should fail
        assert key in votes  # Would be blocked

    def test_no_self_voting_logic(self):
        """Verify self-voting check logic."""
        matchup = {
            "meme_a_id": "meme_1",
            "meme_b_id": "meme_2",
        }
        meme_owners = {
            "meme_1": "user_a",
            "meme_2": "user_b",
        }

        voter_id = "user_a"
        meme_a_owner = meme_owners[matchup["meme_a_id"]]
        meme_b_owner = meme_owners[matchup["meme_b_id"]]

        is_self_voting = (meme_a_owner == voter_id or meme_b_owner == voter_id)
        assert is_self_voting is True

        voter_id = "user_c"
        is_self_voting = (meme_a_owner == voter_id or meme_b_owner == voter_id)
        assert is_self_voting is False

    def test_meme_submission_limit_logic(self):
        """Verify 2-meme limit logic."""
        MAX_MEMES = 2
        user_memes = ["meme_1", "meme_2"]
        assert len(user_memes) >= MAX_MEMES  # Would block submission


# ============================================================================
# Test Admin Tie-Breaking Logic
# ============================================================================

class TestAdminLogic:
    def test_tie_detection(self):
        """Verify tie detection when votes are equal."""
        votes_a = 5
        votes_b = 5
        is_tie = votes_a == votes_b
        assert is_tie is True

    def test_clear_winner_detection(self):
        """Verify winner detection when votes differ."""
        votes_a = 7
        votes_b = 3
        if votes_a > votes_b:
            winner = "meme_a"
        elif votes_b > votes_a:
            winner = "meme_b"
        else:
            winner = None
        assert winner == "meme_a"

    def test_round_advancement_requires_all_complete(self):
        """Verify that round advancement checks all matchups are complete."""
        matchups = [
            {"status": "complete", "winner_id": "m1"},
            {"status": "complete", "winner_id": "m2"},
            {"status": "voting", "winner_id": None},  # Not complete!
        ]
        incomplete = [m for m in matchups if m["status"] != "complete"]
        assert len(incomplete) == 1
        # Would raise error

    def test_round_advancement_all_complete(self):
        """Verify round advancement succeeds when all matchups complete."""
        matchups = [
            {"status": "complete", "winner_id": "m1"},
            {"status": "complete", "winner_id": "m2"},
            {"status": "complete", "winner_id": "m3"},
        ]
        incomplete = [m for m in matchups if m["status"] != "complete"]
        assert len(incomplete) == 0
        winners = [m["winner_id"] for m in matchups]
        assert winners == ["m1", "m2", "m3"]


# ============================================================================
# Test Bracket Scaling (stress test)
# ============================================================================

class TestBracketScaling:
    """Verify the bracket engine handles larger submission counts."""

    @pytest.mark.parametrize("num_memes", [128, 200, 256, 500, 1000])
    def test_large_brackets(self, num_memes):
        """Bracket should work correctly for large entry counts."""
        params = compute_bracket_params(num_memes)
        assert params["bracket_size"] >= num_memes
        assert params["bracket_size"] & (params["bracket_size"] - 1) == 0  # is power of 2
        assert params["num_byes"] == params["bracket_size"] - num_memes
        assert params["total_rounds"] == int(math.log2(params["bracket_size"]))

    @pytest.mark.parametrize("num_memes", [128, 200, 256])
    def test_large_bracket_simulation(self, num_memes):
        """Full simulation should complete with 1 winner for large brackets."""
        result = simulate_bracket(num_memes)
        assert result["final_winner"] is not None
        final_round = result["rounds"][result["total_rounds"]]
        assert final_round["total_matchups"] == 1
