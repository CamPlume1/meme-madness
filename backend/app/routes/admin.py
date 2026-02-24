from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.auth import get_current_user, require_tournament_admin, generate_join_code
from app.supabase_client import supabase_admin
from app.services.bracket import seed_bracket, generate_next_round

router = APIRouter()


class TournamentCreate(BaseModel):
    name: str = "Meme Madness"


class TieBreakRequest(BaseModel):
    matchup_id: str
    winner_id: str


class InviteAdminRequest(BaseModel):
    email: str


@router.post("/tournament/create")
async def create_tournament(body: TournamentCreate, user: dict = Depends(get_current_user)):
    """Create a new tournament. The creator becomes the owner/admin."""
    result = supabase_admin.table("tournament").insert({
        "name": body.name,
        "status": "submission_open",
        "created_by": user["id"],
        "join_code": generate_join_code(),
    }).execute()

    tournament = result.data[0]

    # Make creator the tournament owner
    supabase_admin.table("tournament_admins").insert({
        "tournament_id": tournament["id"],
        "user_id": user["id"],
        "role": "owner",
    }).execute()

    return tournament


@router.post("/tournament/{tournament_id}/seed")
async def seed_tournament(tournament_id: str, admin: dict = Depends(require_tournament_admin)):
    """Close submissions and seed round 1 bracket."""
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
async def advance_round(tournament_id: str, admin: dict = Depends(require_tournament_admin)):
    """Close the current voting round and generate the next round."""
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

    tournament = (
        supabase_admin.table("tournament")
        .select("total_rounds")
        .eq("id", tournament_id)
        .single()
        .execute()
    ).data

    if current_round["round_number"] >= tournament["total_rounds"]:
        final_matchup = matchups[0]
        supabase_admin.table("tournament").update({
            "status": "complete"
        }).eq("id", tournament_id).execute()

        supabase_admin.table("rounds").update({
            "status": "complete"
        }).eq("id", current_round["id"]).execute()

        return {
            "tournament_complete": True,
            "winner_meme_id": final_matchup["winner_id"],
        }

    result = generate_next_round(tournament_id, current_round["round_number"])
    return result


@router.post("/tournament/{tournament_id}/tie-break")
async def tie_break(
    tournament_id: str,
    body: TieBreakRequest,
    admin: dict = Depends(require_tournament_admin),
):
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


@router.post("/tournament/{tournament_id}/matchup/{matchup_id}/close")
async def close_matchup(
    tournament_id: str,
    matchup_id: str,
    admin: dict = Depends(require_tournament_admin),
):
    """Close voting on a matchup and determine the winner by vote count."""
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


@router.post("/tournament/{tournament_id}/round/{round_id}/close-all")
async def close_all_matchups_in_round(
    tournament_id: str,
    round_id: str,
    admin: dict = Depends(require_tournament_admin),
):
    """Close all voting matchups in a round."""
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


@router.get("/tournament/{tournament_id}/dashboard")
async def admin_dashboard(tournament_id: str, admin: dict = Depends(require_tournament_admin)):
    """Get admin dashboard summary for a tournament."""
    t = (
        supabase_admin.table("tournament")
        .select("*")
        .eq("id", tournament_id)
        .single()
        .execute()
    ).data

    # Count memes for this tournament
    memes_count = (
        supabase_admin.table("memes")
        .select("id", count="exact")
        .eq("tournament_id", tournament_id)
        .execute()
    ).count

    rounds = (
        supabase_admin.table("rounds")
        .select("*")
        .eq("tournament_id", tournament_id)
        .order("round_number")
        .execute()
    ).data

    current_round = None
    for r in rounds:
        if r["status"] in ("voting", "pending"):
            current_round = r
            break

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


# === Admin management endpoints ===

@router.post("/tournament/{tournament_id}/invite-admin")
async def invite_admin(
    tournament_id: str,
    body: InviteAdminRequest,
    admin: dict = Depends(require_tournament_admin),
):
    """Invite another user as an admin by email."""
    profile = (
        supabase_admin.table("profiles")
        .select("id, email")
        .eq("email", body.email)
        .maybe_single()
        .execute()
    )

    if not profile.data:
        raise HTTPException(status_code=404, detail="No user found with that email")

    existing = (
        supabase_admin.table("tournament_admins")
        .select("id")
        .eq("tournament_id", tournament_id)
        .eq("user_id", profile.data["id"])
        .maybe_single()
        .execute()
    )

    if existing.data:
        raise HTTPException(status_code=400, detail="User is already an admin of this tournament")

    supabase_admin.table("tournament_admins").insert({
        "tournament_id": tournament_id,
        "user_id": profile.data["id"],
        "role": "admin",
        "invited_by": admin["id"],
    }).execute()

    return {"success": True, "invited_email": body.email}


@router.get("/tournament/{tournament_id}/admins")
async def list_tournament_admins(
    tournament_id: str,
    admin: dict = Depends(require_tournament_admin),
):
    """List all admins for a tournament."""
    admins = (
        supabase_admin.table("tournament_admins")
        .select("*, profiles(display_name, email)")
        .eq("tournament_id", tournament_id)
        .order("created_at")
        .execute()
    )
    return admins.data


@router.delete("/tournament/{tournament_id}/admins/{user_id}")
async def remove_tournament_admin(
    tournament_id: str,
    user_id: str,
    admin: dict = Depends(require_tournament_admin),
):
    """Remove an admin from a tournament. Only the owner can do this."""
    if admin.get("tournament_role") != "owner":
        raise HTTPException(status_code=403, detail="Only the tournament owner can remove admins")

    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="Cannot remove yourself")

    supabase_admin.table("tournament_admins").delete().eq(
        "tournament_id", tournament_id
    ).eq("user_id", user_id).execute()

    return {"success": True}


# === Join code management ===

@router.get("/tournament/{tournament_id}/join-code")
async def get_join_code(
    tournament_id: str,
    admin: dict = Depends(require_tournament_admin),
):
    """Get the current join code for a tournament. Admin only."""
    t = (
        supabase_admin.table("tournament")
        .select("join_code")
        .eq("id", tournament_id)
        .single()
        .execute()
    ).data
    return {"join_code": t["join_code"]}


@router.post("/tournament/{tournament_id}/regenerate-code")
async def regenerate_join_code(
    tournament_id: str,
    admin: dict = Depends(require_tournament_admin),
):
    """Generate a new join code for a tournament. Admin only."""
    new_code = generate_join_code()
    supabase_admin.table("tournament").update({
        "join_code": new_code,
    }).eq("id", tournament_id).execute()
    return {"join_code": new_code}


# === Member management ===

@router.get("/tournament/{tournament_id}/members")
async def list_tournament_members(
    tournament_id: str,
    admin: dict = Depends(require_tournament_admin),
):
    """List all members of a tournament. Admin only."""
    members = (
        supabase_admin.table("tournament_members")
        .select("*, profiles(display_name, email)")
        .eq("tournament_id", tournament_id)
        .order("joined_at")
        .execute()
    )
    return members.data


@router.delete("/tournament/{tournament_id}/members/{user_id}")
async def remove_tournament_member(
    tournament_id: str,
    user_id: str,
    admin: dict = Depends(require_tournament_admin),
):
    """Remove a member from a tournament. Admin only."""
    supabase_admin.table("tournament_members").delete().eq(
        "tournament_id", tournament_id
    ).eq("user_id", user_id).execute()
    return {"success": True}
