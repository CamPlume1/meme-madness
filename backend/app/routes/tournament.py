from fastapi import APIRouter, Depends, HTTPException, Query
from app.auth import get_current_user, require_tournament_member
from app.supabase_client import supabase_admin

router = APIRouter()


@router.get("/list")
async def list_tournaments(user: dict = Depends(get_current_user)):
    """List tournaments the user is a member or admin of."""
    # Get user's admin roles
    admin_roles = (
        supabase_admin.table("tournament_admins")
        .select("tournament_id, role")
        .eq("user_id", user["id"])
        .execute()
    ).data
    admin_map = {r["tournament_id"]: r["role"] for r in admin_roles}

    # Get user's memberships
    member_rows = (
        supabase_admin.table("tournament_members")
        .select("tournament_id")
        .eq("user_id", user["id"])
        .execute()
    ).data
    member_ids = {r["tournament_id"] for r in member_rows}

    # Union of all tournament IDs the user can see
    visible_ids = list(set(admin_map.keys()) | member_ids)
    if not visible_ids:
        return []

    tournaments = (
        supabase_admin.table("tournament")
        .select("*")
        .in_("id", visible_ids)
        .order("created_at", desc=True)
        .execute()
    ).data

    for t in tournaments:
        t["user_role"] = admin_map.get(t["id"], "member" if t["id"] in member_ids else None)

    return tournaments


@router.get("/{tournament_id}")
async def get_tournament(tournament_id: str, user: dict = Depends(require_tournament_member)):
    """Get a specific tournament. Requires membership."""
    result = (
        supabase_admin.table("tournament")
        .select("*")
        .eq("id", tournament_id)
        .maybe_single()
        .execute()
    )
    t_data = result.data if result else None
    if not t_data:
        raise HTTPException(status_code=404, detail="Tournament not found")

    t = t_data
    t["user_role"] = user.get("tournament_role")
    return t


@router.get("/{tournament_id}/rounds")
async def get_rounds(tournament_id: str, user: dict = Depends(require_tournament_member)):
    """Get all rounds for a tournament."""
    rounds = (
        supabase_admin.table("rounds")
        .select("*")
        .eq("tournament_id", tournament_id)
        .order("round_number")
        .execute()
    )
    return rounds.data


@router.get("/{tournament_id}/rounds/{round_number}/matchups")
async def get_round_matchups(
    tournament_id: str,
    round_number: int,
    user: dict = Depends(require_tournament_member),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    """Get matchups for a specific round, with pagination.
    Includes meme details and vote counts."""
    round_result = (
        supabase_admin.table("rounds")
        .select("id, status")
        .eq("tournament_id", tournament_id)
        .eq("round_number", round_number)
        .maybe_single()
        .execute()
    )
    round_data = round_result.data if round_result else None

    if not round_data:
        raise HTTPException(status_code=404, detail="Round not found")

    matchups = (
        supabase_admin.table("matchups")
        .select("*, meme_a:memes!matchups_meme_a_id_fkey(id, title, image_url, owner_id), meme_b:memes!matchups_meme_b_id_fkey(id, title, image_url, owner_id)")
        .eq("round_id", round_data["id"])
        .order("position")
        .range(offset, offset + limit - 1)
        .execute()
    )

    count_result = (
        supabase_admin.table("matchups")
        .select("id", count="exact")
        .eq("round_id", round_data["id"])
        .execute()
    )

    # Attach vote counts
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
        "round_status": round_data["status"],
        "matchups": matchups.data,
        "total": count_result.count,
        "offset": offset,
        "limit": limit,
    }


@router.get("/{tournament_id}/bracket")
async def get_bracket(tournament_id: str, user: dict = Depends(require_tournament_member)):
    """Get the full bracket structure for a tournament."""
    t_result = (
        supabase_admin.table("tournament")
        .select("*")
        .eq("id", tournament_id)
        .maybe_single()
        .execute()
    )
    t_data = t_result.data if t_result else None
    if not t_data:
        raise HTTPException(status_code=404, detail="Tournament not found")

    t = t_data

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
