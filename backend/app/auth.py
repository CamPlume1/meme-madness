from fastapi import Request, HTTPException
from app.supabase_client import supabase_admin
import httpx
from app.config import SUPABASE_URL, SUPABASE_ANON_KEY


async def get_current_user(request: Request) -> dict:
    """Extract and verify the JWT from the Authorization header.
    Returns the user's profile row from the profiles table."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    token = auth_header.split(" ", 1)[1]

    # Verify the token with Supabase
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{SUPABASE_URL}/auth/v1/user",
            headers={
                "Authorization": f"Bearer {token}",
                "apikey": SUPABASE_ANON_KEY,
            },
        )

    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid token")

    user_data = resp.json()
    user_id = user_data["id"]

    # Fetch the profile
    profile = (
        supabase_admin.table("profiles")
        .select("*")
        .eq("id", user_id)
        .maybe_single()
        .execute()
    )

    if not profile.data:
        raise HTTPException(status_code=404, detail="Profile not found")

    return profile.data


async def require_admin(request: Request) -> dict:
    """Require the current user to be an admin."""
    user = await get_current_user(request)
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
