from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.auth import get_current_user, verify_membership
from app.supabase_client import supabase_admin

router = APIRouter()


async def _get_tournament_from_matchup(matchup_id: str) -> str:
    """Resolve matchup -> round -> tournament_id."""
    matchup = (
        supabase_admin.table("matchups")
        .select("round_id")
        .eq("id", matchup_id)
        .maybe_single()
        .execute()
    )
    if not matchup.data:
        raise HTTPException(status_code=404, detail="Matchup not found")

    round_row = (
        supabase_admin.table("rounds")
        .select("tournament_id")
        .eq("id", matchup.data["round_id"])
        .single()
        .execute()
    )
    return round_row.data["tournament_id"]


class VoteRequest(BaseModel):
    matchup_id: str
    meme_id: str


@router.post("/vote")
async def cast_vote(vote: VoteRequest, user: dict = Depends(get_current_user)):
    """Cast a vote for a meme in a matchup."""
    # Verify tournament membership
    tournament_id = await _get_tournament_from_matchup(vote.matchup_id)
    await verify_membership(user["id"], tournament_id)

    # Get the matchup
    matchup = (
        supabase_admin.table("matchups")
        .select("*")
        .eq("id", vote.matchup_id)
        .single()
        .execute()
    ).data

    if not matchup:
        raise HTTPException(status_code=404, detail="Matchup not found")

    if matchup["status"] != "voting":
        raise HTTPException(status_code=400, detail="This matchup is not currently accepting votes")

    # Verify the meme_id is one of the two competitors
    if vote.meme_id not in (matchup["meme_a_id"], matchup["meme_b_id"]):
        raise HTTPException(status_code=400, detail="Invalid meme for this matchup")

    # Check no self-voting: user cannot vote on matchup containing their own meme
    meme_a = supabase_admin.table("memes").select("owner_id").eq("id", matchup["meme_a_id"]).single().execute().data
    if matchup["meme_b_id"]:
        meme_b = supabase_admin.table("memes").select("owner_id").eq("id", matchup["meme_b_id"]).single().execute().data
    else:
        meme_b = None

    if meme_a["owner_id"] == user["id"] or (meme_b and meme_b["owner_id"] == user["id"]):
        raise HTTPException(status_code=403, detail="You cannot vote on a matchup containing your own meme")

    # Check for existing vote
    existing = (
        supabase_admin.table("votes")
        .select("id")
        .eq("matchup_id", vote.matchup_id)
        .eq("voter_id", user["id"])
        .execute()
    ).data

    if existing:
        raise HTTPException(status_code=400, detail="You have already voted on this matchup")

    # Cast the vote
    result = supabase_admin.table("votes").insert({
        "matchup_id": vote.matchup_id,
        "voter_id": user["id"],
        "meme_id": vote.meme_id,
    }).execute()

    return {"success": True, "vote": result.data[0]}


@router.get("/matchup/{matchup_id}/my-vote")
async def get_my_vote(matchup_id: str, user: dict = Depends(get_current_user)):
    """Check if the current user has voted on a matchup."""
    tournament_id = await _get_tournament_from_matchup(matchup_id)
    await verify_membership(user["id"], tournament_id)

    vote = (
        supabase_admin.table("votes")
        .select("*")
        .eq("matchup_id", matchup_id)
        .eq("voter_id", user["id"])
        .maybe_single()
        .execute()
    )
    return {"voted": vote.data is not None, "vote": vote.data}


@router.get("/matchup/{matchup_id}/results")
async def get_matchup_results(matchup_id: str, user: dict = Depends(get_current_user)):
    """Get vote counts for a matchup. Only returns counts if user has voted."""
    tournament_id = await _get_tournament_from_matchup(matchup_id)
    await verify_membership(user["id"], tournament_id)

    # Check if user has voted
    my_vote = (
        supabase_admin.table("votes")
        .select("id")
        .eq("matchup_id", matchup_id)
        .eq("voter_id", user["id"])
        .maybe_single()
        .execute()
    )

    matchup = (
        supabase_admin.table("matchups")
        .select("meme_a_id, meme_b_id, status, winner_id")
        .eq("id", matchup_id)
        .single()
        .execute()
    ).data

    # Check if user owns one of the memes (owners can see counts)
    meme_a = supabase_admin.table("memes").select("owner_id").eq("id", matchup["meme_a_id"]).single().execute().data
    is_owner = meme_a["owner_id"] == user["id"]
    if not is_owner and matchup["meme_b_id"]:
        meme_b = supabase_admin.table("memes").select("owner_id").eq("id", matchup["meme_b_id"]).single().execute().data
        is_owner = meme_b["owner_id"] == user["id"]

    has_voted = my_vote.data is not None
    is_complete = matchup["status"] == "complete"

    if not has_voted and not is_complete and not is_owner:
        return {"can_see_results": False, "message": "Vote first to see results"}

    votes = (
        supabase_admin.table("votes")
        .select("meme_id")
        .eq("matchup_id", matchup_id)
        .execute()
    ).data

    votes_a = sum(1 for v in votes if v["meme_id"] == matchup["meme_a_id"])
    votes_b = sum(1 for v in votes if v["meme_id"] == matchup["meme_b_id"])

    return {
        "can_see_results": True,
        "votes_a": votes_a,
        "votes_b": votes_b,
        "total": len(votes),
        "winner_id": matchup["winner_id"],
    }
