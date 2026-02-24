from supabase import create_client, Client
from app.config import SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY

# Anon client — used with user JWT for RLS-protected queries
supabase_anon: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# Service role client — bypasses RLS, used for admin operations
supabase_admin: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
