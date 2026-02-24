from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.auth import require_admin
from app.supabase_client import supabase_admin
from app.services.bracket import seed_bracket, generate_next_round

router = APIRouter()


class TournamentCreate(BaseModel):
    name: str = "Meme Madness"


class TieBreakRequest(BaseModel):
    matchup_id: str
    winner_id: str


@router.post("/tournament/create")
async def create_tournament(body: TournamentCreate, admin: dict = Depends(require_admin)):
    """Create a new tournament (submission_open by default)."""
    result = supabase_admin.table("tournament").insert({
        "name": body.name,
        "status": "submission_open",
    }).execute()
    return result.data[0]


@router.post("/tournament/{tournament_id}/seed")
async def seed_tournament(tournament_id: str, admin: dict = Depends(require_admin)):
    """Close submissions and seed round 1 bracket."""
    # Verify tournament exists and is in submission_open
    t = (
        supabase_admin.table("tournament")
        .select("*")
        .eq("id", tournament_id)
        .single()
        .execute()
    ).data

    if t["status"] != "submission_open":
        raise HTTPException(status_code=400, detail="Tournament is not in submission phase")

    result = seed_bracket(tournament_id)
    return result


@router.post("/tournament/{tournament_id}/advance-round")
async def advance_round(tournament_id: str, admin: dict = Depends(require_admin)):
    """Close the current voting round and generate the next round."""
    # Find the current active round
    rounds = (
        supabase_admin.table("rounds")
        .select("*")
        .eq("tournament_id", tournament_id)
        .order("round_number", desc=True)
        .limit(1)
        .execute()
    ).data

    if not rounds:
        raise HTTPException(status_code=400, detail="No rounds found")

    current_round = rounds[0]

    if current_round["status"] == "complete":
        raise HTTPException(status_code=400, detail="Current round is already complete")

    # Check all matchups in this round are complete
    matchups = (
        supabase_admin.table("matchups")
        .select("id, status, winner_id")
        .eq("round_id", current_round["id"])
        .execute()
    ).data

    incomplete = [m for m in matchups if m["status"] != "complete"]
    if incomplete:
        raise HTTPException(
            status_code=400,
            detail=f"{len(incomplete)} matchups still need resolution. Use tie-break to resolve tied matchups."
        )

    # Check if this is the final round
    tournament = (
        supabase_admin.table("tournament")
        .select("total_rounds")
        .eq("id", tournament_id)
        .single()
        .execute()
    ).data

    if current_round["round_number"] >= tournament["total_rounds"]:
        # This was the final round — the winner is the winner of the sole matchup
        final_matchup = matchups[0]  # Should only be one
        supabase_admin.table("tournament").update({
            "status": "complete"
        }).eq("id", tournament_id).execute()

        # Mark round as complete
        supabase_admin.table("rounds").update({
            "status": "complete"
        }).eq("id", current_round["id"]).execute()

        return {
            "tournament_complete": True,
            "winner_meme_id": final_matchup["winner_id"],
        }

    result = generate_next_round(tournament_id, current_round["round_number"])
    return result


@router.post("/tournament/tie-break")
async def tie_break(body: TieBreakRequest, admin: dict = Depends(require_admin)):
    """Admin breaks a tie by selecting the winner."""
    matchup = (
        supabase_admin.table("matchups")
        .select("*")
        .eq("id", body.matchup_id)
        .single()
        .execute()
    ).data

    if matchup["status"] == "complete":
        raise HTTPException(status_code=400, detail="Matchup already resolved")

    if body.winner_id not in (matchup["meme_a_id"], matchup["meme_b_id"]):
        raise HTTPException(status_code=400, detail="Winner must be one of the competitors")

    supabase_admin.table("matchups").update({
        "winner_id": body.winner_id,
        "status": "complete",
    }).eq("id", body.matchup_id).execute()

    return {"success": True, "winner_id": body.winner_id}


@router.post("/matchup/{matchup_id}/close")
async def close_matchup(matchup_id: str, admin: dict = Depends(require_admin)):
    """Close voting on a matchup and determine the winner by vote count.
    Returns a tie if counts are equal (admin must then tie-break)."""
    matchup = (
        supabase_admin.table("matchups")
        .select("*")
        .eq("id", matchup_id)
        .single()
        .execute()
    ).data

    if matchup["status"] == "complete":
        raise HTTPException(status_code=400, detail="Matchup already complete")

    votes = (
        supabase_admin.table("votes")
        .select("meme_id")
        .eq("matchup_id", matchup_id)
        .execute()
    ).data

    votes_a = sum(1 for v in votes if v["meme_id"] == matchup["meme_a_id"])
    votes_b = sum(1 for v in votes if v["meme_id"] == matchup["meme_b_id"])

    if votes_a > votes_b:
        winner_id = matchup["meme_a_id"]
    elif votes_b > votes_a:
        winner_id = matchup["meme_b_id"]
    else:
        # Tie — admin needs to break it
        return {
            "tie": True,
            "votes_a": votes_a,
            "votes_b": votes_b,
            "message": "Tied! Use tie-break endpoint to select winner.",
        }

    supabase_admin.table("matchups").update({
        "winner_id": winner_id,
        "status": "complete",
    }).eq("id", matchup_id).execute()

    return {"winner_id": winner_id, "votes_a": votes_a, "votes_b": votes_b}


@router.post("/round/{round_id}/close-all")
async def close_all_matchups_in_round(round_id: str, admin: dict = Depends(require_admin)):
    """Close all voting matchups in a round. Returns list of results including ties."""
    matchups = (
        supabase_admin.table("matchups")
        .select("*")
        .eq("round_id", round_id)
        .eq("status", "voting")
        .execute()
    ).data

    results = []
    ties = []

    for matchup in matchups:
        votes = (
            supabase_admin.table("votes")
            .select("meme_id")
            .eq("matchup_id", matchup["id"])
            .execute()
        ).data

        votes_a = sum(1 for v in votes if v["meme_id"] == matchup["meme_a_id"])
        votes_b = sum(1 for v in votes if v["meme_id"] == matchup["meme_b_id"])

        if votes_a > votes_b:
            winner_id = matchup["meme_a_id"]
        elif votes_b > votes_a:
            winner_id = matchup["meme_b_id"]
        else:
            ties.append({
                "matchup_id": matchup["id"],
                "votes_a": votes_a,
                "votes_b": votes_b,
            })
            continue

        supabase_admin.table("matchups").update({
            "winner_id": winner_id,
            "status": "complete",
        }).eq("id", matchup["id"]).execute()

        results.append({
            "matchup_id": matchup["id"],
            "winner_id": winner_id,
            "votes_a": votes_a,
            "votes_b": votes_b,
        })

    return {
        "resolved": results,
        "ties": ties,
        "message": f"Resolved {len(results)} matchups. {len(ties)} ties need admin decision."
    }


@router.get("/dashboard")
async def admin_dashboard(admin: dict = Depends(require_admin)):
    """Get admin dashboard summary."""
    tournament = (
        supabase_admin.table("tournament")
        .select("*")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    ).data

    if not tournament:
        return {"tournament": None}

    t = tournament[0]

    # Count memes
    memes_count = (
        supabase_admin.table("memes")
        .select("id", count="exact")
        .execute()
    ).count

    # Get rounds info
    rounds = (
        supabase_admin.table("rounds")
        .select("*")
        .eq("tournament_id", t["id"])
        .order("round_number")
        .execute()
    ).data

    current_round = None
    for r in rounds:
        if r["status"] in ("voting", "pending"):
            current_round = r
            break

    # If there's a current round, get matchup stats
    round_stats = None
    if current_round:
        matchups = (
            supabase_admin.table("matchups")
            .select("id, status, winner_id, meme_a_id, meme_b_id")
            .eq("round_id", current_round["id"])
            .execute()
        ).data

        voting_count = sum(1 for m in matchups if m["status"] == "voting")
        complete_count = sum(1 for m in matchups if m["status"] == "complete")
        pending_count = sum(1 for m in matchups if m["status"] == "pending")

        round_stats = {
            "round_number": current_round["round_number"],
            "total_matchups": len(matchups),
            "voting": voting_count,
            "complete": complete_count,
            "pending": pending_count,
        }

    from app.services.bracket import next_power_of_2
    bracket_size = next_power_of_2(memes_count) if memes_count > 0 else 0
    num_byes = bracket_size - memes_count if memes_count > 0 else 0

    return {
        "tournament": t,
        "memes_count": memes_count,
        "bracket_size": bracket_size,
        "num_byes": num_byes,
        "total_rounds": t.get("total_rounds"),
        "current_round": round_stats,
        "rounds": rounds,
    }
