from fastapi import Request, HTTPException
from app.supabase_client import supabase_admin
import httpx
import secrets
import string
from app.config import SUPABASE_URL, SUPABASE_ANON_KEY


def generate_join_code(length: int = 8) -> str:
    """Generate a random uppercase alphanumeric join code."""
    alphabet = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


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


async def require_tournament_admin(request: Request) -> dict:
    """Require the current user to be an admin of the tournament specified
    by the 'tournament_id' path parameter."""
    user = await get_current_user(request)

    tournament_id = request.path_params.get("tournament_id")
    if not tournament_id:
        raise HTTPException(status_code=400, detail="tournament_id path parameter required")

    admin_row = (
        supabase_admin.table("tournament_admins")
        .select("id, role")
        .eq("tournament_id", tournament_id)
        .eq("user_id", user["id"])
        .maybe_single()
        .execute()
    )

    if not admin_row.data:
        raise HTTPException(status_code=403, detail="You are not an admin of this tournament")

    user["tournament_role"] = admin_row.data["role"]
    return user


async def verify_membership(user_id: str, tournament_id: str) -> None:
    """Check that user_id is an admin or member of tournament_id.
    Raises 403 if neither. Used for query-param-based routes."""
    admin_row = (
        supabase_admin.table("tournament_admins")
        .select("id")
        .eq("tournament_id", tournament_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    if admin_row.data:
        return

    member_row = (
        supabase_admin.table("tournament_members")
        .select("id")
        .eq("tournament_id", tournament_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    if member_row.data:
        return

    raise HTTPException(status_code=403, detail="You are not a member of this tournament")


async def require_tournament_member(request: Request) -> dict:
    """FastAPI dependency: require the current user to be a member or admin
    of the tournament specified by the 'tournament_id' path parameter."""
    user = await get_current_user(request)

    tournament_id = request.path_params.get("tournament_id")
    if not tournament_id:
        raise HTTPException(status_code=400, detail="tournament_id path parameter required")

    # Check admin table first (admins are implicit members)
    admin_row = (
        supabase_admin.table("tournament_admins")
        .select("id, role")
        .eq("tournament_id", tournament_id)
        .eq("user_id", user["id"])
        .maybe_single()
        .execute()
    )

    if admin_row.data:
        user["tournament_role"] = admin_row.data["role"]
        return user

    # Check members table
    member_row = (
        supabase_admin.table("tournament_members")
        .select("id")
        .eq("tournament_id", tournament_id)
        .eq("user_id", user["id"])
        .maybe_single()
        .execute()
    )

    if member_row.data:
        user["tournament_role"] = "member"
        return user

    raise HTTPException(status_code=403, detail="You are not a member of this tournament")
