"""Bracket engine: seeding, bye distribution, round generation, advancement."""
import math
import random
from collections import defaultdict
from uuid import uuid4
from app.supabase_client import supabase_admin


def next_power_of_2(n: int) -> int:
    """Return the smallest power of 2 >= n."""
    if n <= 1:
        return 1
    return 1 << (n - 1).bit_length()


def _avoid_same_owner_adjacent(memes: list) -> None:
    """In-place greedy pass: if memes[i] and memes[i+1] share an owner,
    swap memes[i+1] with the first later entry that has a different owner."""
    for i in range(len(memes) - 1):
        if memes[i]["owner_id"] == memes[i + 1]["owner_id"]:
            for j in range(i + 2, len(memes)):
                if memes[j]["owner_id"] != memes[i]["owner_id"]:
                    memes[i + 1], memes[j] = memes[j], memes[i + 1]
                    break


def _build_half_matchups(half_memes, half_capacity, round1_id, start_position):
    """Build matchups for one half of the bracket.

    Returns (matchups_list, next_position).
    """
    num_byes = half_capacity - len(half_memes)

    # Identify same-owner pairs within this half
    owner_counts = defaultdict(list)
    for m in half_memes:
        owner_counts[m["owner_id"]].append(m)

    bye_memes = []
    compete_pool = []

    # Bye trick: for same-owner pairs, give one member a bye so they don't
    # face each other in round 1
    for owner_id, owned in owner_counts.items():
        if len(owned) == 2 and num_byes > 0:
            bye_memes.append(owned[0])
            compete_pool.append(owned[1])
            num_byes -= 1
        else:
            compete_pool.extend(owned)

    # Fill remaining bye slots from the compete pool
    random.shuffle(compete_pool)
    while num_byes > 0 and compete_pool:
        bye_memes.append(compete_pool.pop(0))
        num_byes -= 1

    # Separate same-owner adjacencies in compete pool
    _avoid_same_owner_adjacent(compete_pool)

    matchups = []
    position = start_position

    # Bye matchups
    for meme in bye_memes:
        matchups.append({
            "id": str(uuid4()),
            "round_id": round1_id,
            "meme_a_id": meme["id"],
            "meme_b_id": None,
            "winner_id": meme["id"],
            "status": "complete",
            "position": position,
        })
        position += 1

    # Competing matchups
    for i in range(0, len(compete_pool), 2):
        matchups.append({
            "id": str(uuid4()),
            "round_id": round1_id,
            "meme_a_id": compete_pool[i]["id"],
            "meme_b_id": compete_pool[i + 1]["id"],
            "winner_id": None,
            "status": "voting",
            "position": position,
        })
        position += 1

    return matchups, position


def seed_bracket(tournament_id: str) -> dict:
    """Seed round 1 from memes submitted to this tournament.
    Returns info about the bracket (size, byes, round 1 matchups)."""

    # Get memes for THIS tournament
    memes_resp = (
        supabase_admin.table("memes")
        .select("id, owner_id")
        .eq("tournament_id", tournament_id)
        .execute()
    )
    memes = memes_resp.data
    num_memes = len(memes)

    if num_memes < 4:
        raise ValueError("Need at least 4 memes to seed a bracket")

    bracket_size = next_power_of_2(num_memes)
    num_byes = bracket_size - num_memes
    total_rounds = int(math.log2(bracket_size))

    # Update tournament with total rounds
    supabase_admin.table("tournament").update({
        "total_rounds": total_rounds,
        "status": "voting_open",
    }).eq("id", tournament_id).execute()

    # Create round 1
    round1_id = str(uuid4())
    supabase_admin.table("rounds").insert({
        "id": round1_id,
        "tournament_id": tournament_id,
        "round_number": 1,
        "status": "voting",
    }).execute()

    # --- Owner-aware half assignment ---
    # Group memes by owner_id into pairs (owner has 2) and singles (owner has 1)
    owner_map = defaultdict(list)
    for m in memes:
        owner_map[m["owner_id"]].append(m)

    pairs = []   # list of [meme, meme] for owners with exactly 2
    singles = [] # list of meme dicts for owners with 1
    for owner_id, owned in owner_map.items():
        if len(owned) == 2:
            pairs.append(owned)
        else:
            singles.extend(owned)

    random.shuffle(pairs)
    random.shuffle(singles)

    half_capacity = bracket_size // 2
    half_a_capacity = half_capacity // 2
    half_b_capacity = half_capacity - half_a_capacity

    half_a = []
    half_b = []

    # Distribute pairs: both memes go to the same half, balancing sizes
    for pair in pairs:
        if len(half_a) + 2 <= half_a_capacity:
            half_a.extend(pair)
        elif len(half_b) + 2 <= half_b_capacity:
            half_b.extend(pair)
        elif len(half_a) <= len(half_b):
            half_a.extend(pair)
        else:
            half_b.extend(pair)

    # Fill remaining capacity with singles, balancing sizes
    for meme in singles:
        if len(half_a) < half_a_capacity:
            half_a.append(meme)
        elif len(half_b) < half_b_capacity:
            half_b.append(meme)
        elif len(half_a) <= len(half_b):
            half_a.append(meme)
        else:
            half_b.append(meme)

    # Build matchups per half
    matchups_a, next_pos = _build_half_matchups(half_a, half_a_capacity, round1_id, 0)
    matchups_b, _ = _build_half_matchups(half_b, half_b_capacity, round1_id, next_pos)

    matchups = matchups_a + matchups_b

    # Batch insert matchups
    if matchups:
        supabase_admin.table("matchups").insert(matchups).execute()

    return {
        "bracket_size": bracket_size,
        "num_byes": num_byes,
        "total_rounds": total_rounds,
        "round1_matchups": len(matchups),
    }


def generate_next_round(tournament_id: str, current_round_number: int) -> dict:
    """Generate the next round's matchups from the winners of the current round."""

    # Get current round
    round_resp = (
        supabase_admin.table("rounds")
        .select("*")
        .eq("tournament_id", tournament_id)
        .eq("round_number", current_round_number)
        .single()
        .execute()
    )
    current_round = round_resp.data

    # Get all matchups for this round, ordered by position
    matchups_resp = (
        supabase_admin.table("matchups")
        .select("*")
        .eq("round_id", current_round["id"])
        .order("position")
        .execute()
    )
    matchups = matchups_resp.data

    # Verify all matchups are complete
    incomplete = [m for m in matchups if m["status"] != "complete"]
    if incomplete:
        raise ValueError(f"{len(incomplete)} matchups still incomplete in round {current_round_number}")

    # Collect winners
    winners = [m["winner_id"] for m in matchups]

    if len(winners) < 2:
        raise ValueError("Not enough winners to generate next round")

    # Create next round
    next_round_number = current_round_number + 1
    next_round_id = str(uuid4())
    supabase_admin.table("rounds").insert({
        "id": next_round_id,
        "tournament_id": tournament_id,
        "round_number": next_round_number,
        "status": "voting",
    }).execute()

    # Create matchups for next round, pairing winners in order
    next_matchups = []
    for i in range(0, len(winners), 2):
        matchup_id = str(uuid4())
        if i + 1 < len(winners):
            next_matchups.append({
                "id": matchup_id,
                "round_id": next_round_id,
                "meme_a_id": winners[i],
                "meme_b_id": winners[i + 1],
                "winner_id": None,
                "status": "voting",
                "position": i // 2,
            })
        else:
            # Odd number of winners — give a bye
            next_matchups.append({
                "id": matchup_id,
                "round_id": next_round_id,
                "meme_a_id": winners[i],
                "meme_b_id": None,
                "winner_id": winners[i],
                "status": "complete",
                "position": i // 2,
            })

    supabase_admin.table("matchups").insert(next_matchups).execute()

    # Link current round's matchups to next round's matchups
    for i, next_matchup in enumerate(next_matchups):
        idx1 = i * 2
        idx2 = i * 2 + 1
        if idx1 < len(matchups):
            supabase_admin.table("matchups").update({
                "next_matchup_id": next_matchup["id"]
            }).eq("id", matchups[idx1]["id"]).execute()
        if idx2 < len(matchups):
            supabase_admin.table("matchups").update({
                "next_matchup_id": next_matchup["id"]
            }).eq("id", matchups[idx2]["id"]).execute()

    # Mark current round as complete
    supabase_admin.table("rounds").update({
        "status": "complete"
    }).eq("id", current_round["id"]).execute()

    return {
        "round_number": next_round_number,
        "matchups_created": len(next_matchups),
    }
