from fastapi import APIRouter, Depends, HTTPException, Query
from app.auth import get_current_user
from app.supabase_client import supabase_admin

router = APIRouter()


@router.get("/")
async def get_tournament(user: dict = Depends(get_current_user)):
    """Get the current tournament info."""
    result = (
        supabase_admin.table("tournament")
        .select("*")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not result.data:
        return None
    return result.data[0]


@router.get("/rounds")
async def get_rounds(user: dict = Depends(get_current_user)):
    """Get all rounds for the current tournament."""
    tournament = (
        supabase_admin.table("tournament")
        .select("id")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not tournament.data:
        return []

    rounds = (
        supabase_admin.table("rounds")
        .select("*")
        .eq("tournament_id", tournament.data[0]["id"])
        .order("round_number")
        .execute()
    )
    return rounds.data


@router.get("/rounds/{round_number}/matchups")
async def get_round_matchups(
    round_number: int,
    user: dict = Depends(get_current_user),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    """Get matchups for a specific round, with pagination.
    Includes meme details and vote counts."""
    tournament = (
        supabase_admin.table("tournament")
        .select("id")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not tournament.data:
        raise HTTPException(status_code=404, detail="No tournament found")

    round_row = (
        supabase_admin.table("rounds")
        .select("id, status")
        .eq("tournament_id", tournament.data[0]["id"])
        .eq("round_number", round_number)
        .single()
        .execute()
    )

    matchups = (
        supabase_admin.table("matchups")
        .select("*, meme_a:memes!matchups_meme_a_id_fkey(id, title, image_url, owner_id), meme_b:memes!matchups_meme_b_id_fkey(id, title, image_url, owner_id)")
        .eq("round_id", round_row.data["id"])
        .order("position")
        .range(offset, offset + limit - 1)
        .execute()
    )

    # Get total count
    count_result = (
        supabase_admin.table("matchups")
        .select("id", count="exact")
        .eq("round_id", round_row.data["id"])
        .execute()
    )

    # Attach vote counts to each matchup
    for matchup in matchups.data:
        votes = (
            supabase_admin.table("votes")
            .select("meme_id")
            .eq("matchup_id", matchup["id"])
            .execute()
        ).data
        votes_a = sum(1 for v in votes if v["meme_id"] == matchup["meme_a_id"])
        votes_b = sum(1 for v in votes if matchup["meme_b_id"] and v["meme_id"] == matchup["meme_b_id"])
        matchup["votes_a"] = votes_a
        matchup["votes_b"] = votes_b
        matchup["total_votes"] = len(votes)

    return {
        "round_number": round_number,
        "round_status": round_row.data["status"],
        "matchups": matchups.data,
        "total": count_result.count,
        "offset": offset,
        "limit": limit,
    }


@router.get("/bracket")
async def get_bracket(user: dict = Depends(get_current_user)):
    """Get the full bracket structure (rounds and matchup IDs with progression links).
    For rendering the bracket view — loads lightweight data per round."""
    tournament = (
        supabase_admin.table("tournament")
        .select("*")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not tournament.data:
        raise HTTPException(status_code=404, detail="No tournament found")

    t = tournament.data[0]

    rounds = (
        supabase_admin.table("rounds")
        .select("*")
        .eq("tournament_id", t["id"])
        .order("round_number")
        .execute()
    ).data

    bracket = {
        "tournament": t,
        "rounds": [],
    }

    for r in rounds:
        matchups = (
            supabase_admin.table("matchups")
            .select("id, meme_a_id, meme_b_id, winner_id, status, next_matchup_id, position, meme_a:memes!matchups_meme_a_id_fkey(id, title, image_url, owner_id), meme_b:memes!matchups_meme_b_id_fkey(id, title, image_url, owner_id)")
            .eq("round_id", r["id"])
            .order("position")
            .execute()
        ).data

        bracket["rounds"].append({
            "round": r,
            "matchups": matchups,
        })

    return bracket
