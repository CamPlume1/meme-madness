from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from app.auth import get_current_user
from app.supabase_client import supabase_admin
from app.config import SUPABASE_URL
import uuid

router = APIRouter()

MAX_MEMES_PER_USER = 2


@router.get("/")
async def list_memes(user: dict = Depends(get_current_user)):
    """List all submitted memes."""
    result = supabase_admin.table("memes").select(
        "*, profiles(display_name)"
    ).order("submitted_at", desc=True).execute()
    return result.data


@router.get("/mine")
async def my_memes(user: dict = Depends(get_current_user)):
    """List memes submitted by the current user, with tournament status."""
    memes = (
        supabase_admin.table("memes")
        .select("*")
        .eq("owner_id", user["id"])
        .order("submitted_at", desc=True)
        .execute()
    ).data

    # For each meme, check if it's active in the tournament
    for meme in memes:
        # Check if the meme has any active (non-complete with loss) matchups
        as_a = (
            supabase_admin.table("matchups")
            .select("id, status, winner_id")
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
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    """Upload a meme image. Max 2 per user."""
    # Check tournament status
    tournament = (
        supabase_admin.table("tournament")
        .select("*")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    ).data

    if not tournament or tournament[0]["status"] != "submission_open":
        raise HTTPException(status_code=400, detail="Submissions are not currently open")

    # Check meme count
    count = (
        supabase_admin.table("memes")
        .select("id", count="exact")
        .eq("owner_id", user["id"])
        .execute()
    )
    if count.count >= MAX_MEMES_PER_USER:
        raise HTTPException(
            status_code=400,
            detail=f"You've already submitted {MAX_MEMES_PER_USER} memes"
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

    # Insert meme record
    meme = supabase_admin.table("memes").insert({
        "owner_id": user["id"],
        "title": title,
        "image_url": image_url,
    }).execute()

    return meme.data[0]
