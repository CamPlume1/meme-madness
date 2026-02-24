"""Bracket engine: seeding, bye distribution, round generation, advancement."""
import math
import random
from uuid import uuid4
from app.supabase_client import supabase_admin


def next_power_of_2(n: int) -> int:
    """Return the smallest power of 2 >= n."""
    if n <= 1:
        return 1
    return 1 << (n - 1).bit_length()


def seed_bracket(tournament_id: str) -> dict:
    """Seed round 1 from all submitted memes.
    Returns info about the bracket (size, byes, round 1 matchups)."""

    # Get all memes
    memes_resp = supabase_admin.table("memes").select("id").execute()
    memes = memes_resp.data
    num_memes = len(memes)

    if num_memes < 2:
        raise ValueError("Need at least 2 memes to seed a bracket")

    # Shuffle for random seeding
    random.shuffle(memes)

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

    # Distribute byes evenly: place byes at the end to spread them out
    # Bye memes get auto-advanced, so they go first in the list
    # We'll pair: first `num_byes` memes get byes, rest get paired
    bye_memes = memes[:num_byes]
    competing_memes = memes[num_byes:]

    matchups = []
    position = 0

    # Create bye matchups first
    for meme in bye_memes:
        matchup_id = str(uuid4())
        matchups.append({
            "id": matchup_id,
            "round_id": round1_id,
            "meme_a_id": meme["id"],
            "meme_b_id": None,
            "winner_id": meme["id"],  # Auto-advance
            "status": "complete",
            "position": position,
        })
        position += 1

    # Create competing matchups
    for i in range(0, len(competing_memes), 2):
        matchup_id = str(uuid4())
        matchups.append({
            "id": matchup_id,
            "round_id": round1_id,
            "meme_a_id": competing_memes[i]["id"],
            "meme_b_id": competing_memes[i + 1]["id"],
            "winner_id": None,
            "status": "voting",
            "position": position,
        })
        position += 1

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

    # Now link the current round's matchups to the next round's matchups
    # Every pair of current matchups feeds into one next matchup
    for i, next_matchup in enumerate(next_matchups):
        # Two matchups from current round feed into this next matchup
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
