from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import memes, tournament, voting, admin, membership

app = FastAPI(title="Meme Madness API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(memes.router, prefix="/api/memes", tags=["memes"])
app.include_router(tournament.router, prefix="/api/tournament", tags=["tournament"])
app.include_router(voting.router, prefix="/api/voting", tags=["voting"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(membership.router, prefix="/api/membership", tags=["membership"])


@app.get("/api/health")
async def health():
    return {"status": "ok"}
