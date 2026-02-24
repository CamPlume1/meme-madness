-- Multi-tournament support migration
-- Adds tournament_admins junction table, tournament_id to memes, created_by to tournament

-- =============================================================================
-- TOURNAMENT_ADMINS — per-tournament admin roles
-- =============================================================================

CREATE TABLE tournament_admins (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tournament_id UUID NOT NULL REFERENCES tournament(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'admin',  -- 'owner' for creator, 'admin' for invited
    invited_by UUID REFERENCES profiles(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(tournament_id, user_id)
);

CREATE INDEX idx_tournament_admins_tournament ON tournament_admins(tournament_id);
CREATE INDEX idx_tournament_admins_user ON tournament_admins(user_id);

ALTER TABLE tournament_admins ENABLE ROW LEVEL SECURITY;

-- Admins of a tournament can see co-admins of that tournament
CREATE POLICY "Tournament admins can view co-admins"
    ON tournament_admins FOR SELECT
    TO authenticated
    USING (
        tournament_id IN (
            SELECT ta.tournament_id FROM tournament_admins ta WHERE ta.user_id = auth.uid()
        )
    );

-- =============================================================================
-- ADD tournament_id TO memes
-- =============================================================================

ALTER TABLE memes ADD COLUMN tournament_id UUID REFERENCES tournament(id) ON DELETE CASCADE;
CREATE INDEX idx_memes_tournament ON memes(tournament_id);

-- Backfill: assign any existing memes to the earliest tournament (if any exist)
UPDATE memes
SET tournament_id = (SELECT id FROM tournament ORDER BY created_at ASC LIMIT 1)
WHERE tournament_id IS NULL
  AND EXISTS (SELECT 1 FROM tournament);

-- =============================================================================
-- ADD created_by TO tournament
-- =============================================================================

ALTER TABLE tournament ADD COLUMN created_by UUID REFERENCES profiles(id);
