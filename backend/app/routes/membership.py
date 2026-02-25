from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.auth import get_current_user
from app.supabase_client import supabase_admin

router = APIRouter()


class JoinRequest(BaseModel):
    join_code: str


@router.post("/join")
async def join_tournament(body: JoinRequest, user: dict = Depends(get_current_user)):
    """Join a tournament using a join code."""
    code = body.join_code.strip().upper()

    # Look up tournament by join code
    t_result = (
        supabase_admin.table("tournament")
        .select("id, name")
        .eq("join_code", code)
        .maybe_single()
        .execute()
    )
    t_data = t_result.data if t_result else None

    if not t_data:
        raise HTTPException(status_code=404, detail="Invalid join code")

    tournament_id = t_data["id"]

    # Check if already an admin (implicit member)
    admin_result = (
        supabase_admin.table("tournament_admins")
        .select("id")
        .eq("tournament_id", tournament_id)
        .eq("user_id", user["id"])
        .maybe_single()
        .execute()
    )
    if admin_result and admin_result.data:
        return {"tournament_id": tournament_id, "name": t_data["name"], "already_member": True}

    # Check if already a member
    existing_result = (
        supabase_admin.table("tournament_members")
        .select("id")
        .eq("tournament_id", tournament_id)
        .eq("user_id", user["id"])
        .maybe_single()
        .execute()
    )
    if existing_result and existing_result.data:
        return {"tournament_id": tournament_id, "name": t_data["name"], "already_member": True}

    # Insert membership
    supabase_admin.table("tournament_members").insert({
        "tournament_id": tournament_id,
        "user_id": user["id"],
    }).execute()

    return {"tournament_id": tournament_id, "name": t_data["name"], "already_member": False}
