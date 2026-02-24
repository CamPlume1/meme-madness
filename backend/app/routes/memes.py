from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from app.auth import get_current_user
from app.supabase_client import supabase_admin
from app.config import SUPABASE_URL
import uuid

router = APIRouter()

MAX_MEMES_PER_USER = 2


@router.get("/")
async def list_memes(
    user: dict = Depends(get_current_user),
    tournament_id: str = Query(None),
):
    """List submitted memes, optionally filtered by tournament."""
    query = supabase_admin.table("memes").select("*, profiles(display_name)")
    if tournament_id:
        query = query.eq("tournament_id", tournament_id)
    result = query.order("submitted_at", desc=True).execute()
    return result.data


@router.get("/mine")
async def my_memes(
    user: dict = Depends(get_current_user),
    tournament_id: str = Query(None),
):
    """List memes submitted by the current user, with tournament status."""
    query = supabase_admin.table("memes").select("*").eq("owner_id", user["id"])
    if tournament_id:
        query = query.eq("tournament_id", tournament_id)
    memes = query.order("submitted_at", desc=True).execute().data

    # For each meme, check tournament status via matchups
    for meme in memes:
        as_a = (
            supabase_admin.table("matchups")
            .select("id, status, winner_id, meme_b_id")
            .eq("meme_a_id", meme["id"])
            .execute()
        ).data
        as_b = (
            supabase_admin.table("matchups")
            .select("id, status, winner_id")
            .eq("meme_b_id", meme["id"])
            .execute()
        ).data

        all_matchups = as_a + as_b
        if not all_matchups:
            meme["tournament_status"] = "not_in_bracket"
        else:
            eliminated = any(
                m["status"] == "complete" and m["winner_id"] != meme["id"]
                for m in all_matchups
            )
            has_bye = any(
                m["status"] == "complete" and m["winner_id"] == meme["id"]
                and m.get("meme_b_id") is None
                for m in all_matchups if meme["id"] == m.get("meme_a_id")
            )
            if eliminated:
                meme["tournament_status"] = "eliminated"
            elif has_bye:
                meme["tournament_status"] = "bye_advanced"
            else:
                active = any(m["status"] in ("pending", "voting") for m in all_matchups)
                if active:
                    meme["tournament_status"] = "active"
                else:
                    meme["tournament_status"] = "advanced"

    return memes


@router.post("/upload")
async def upload_meme(
    title: str = Form(""),
    tournament_id: str = Form(...),
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    """Upload a meme image to a specific tournament. Max 2 per user per tournament."""
    # Check tournament status
    tournament = (
        supabase_admin.table("tournament")
        .select("*")
        .eq("id", tournament_id)
        .maybe_single()
        .execute()
    ).data

    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")

    if tournament["status"] != "submission_open":
        raise HTTPException(status_code=400, detail="Submissions are not currently open")

    # Check meme count for THIS tournament
    count = (
        supabase_admin.table("memes")
        .select("id", count="exact")
        .eq("owner_id", user["id"])
        .eq("tournament_id", tournament_id)
        .execute()
    )
    if count.count >= MAX_MEMES_PER_USER:
        raise HTTPException(
            status_code=400,
            detail=f"You've already submitted {MAX_MEMES_PER_USER} memes for this tournament"
        )

    # Upload to Supabase Storage
    file_ext = file.filename.split(".")[-1] if file.filename else "png"
    file_path = f"{user['id']}/{uuid.uuid4()}.{file_ext}"
    file_bytes = await file.read()

    supabase_admin.storage.from_("memes").upload(
        file_path,
        file_bytes,
        file_options={"content-type": file.content_type or "image/png"},
    )

    image_url = f"{SUPABASE_URL}/storage/v1/object/public/memes/{file_path}"

    # Insert meme record with tournament_id
    meme = supabase_admin.table("memes").insert({
        "owner_id": user["id"],
        "title": title,
        "image_url": image_url,
        "tournament_id": tournament_id,
    }).execute()

    return meme.data[0]
