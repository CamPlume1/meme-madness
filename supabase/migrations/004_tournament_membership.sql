-- Migration 004: Private tournament membership with join codes
-- Adds join_code to tournament, creates tournament_members table,
-- replaces open-read RLS policies with membership-gated policies.

-- =============================================================================
-- ADD join_code TO tournament
-- =============================================================================

ALTER TABLE tournament ADD COLUMN join_code TEXT UNIQUE;

-- Backfill existing tournaments with random 8-char codes
UPDATE tournament
SET join_code = upper(substr(md5(random()::text || id::text), 1, 8))
WHERE join_code IS NULL;

-- Now make it NOT NULL
ALTER TABLE tournament ALTER COLUMN join_code SET NOT NULL;

-- =============================================================================
-- TOURNAMENT_MEMBERS table
-- =============================================================================

CREATE TABLE tournament_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tournament_id UUID NOT NULL REFERENCES tournament(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    joined_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(tournament_id, user_id)
);

CREATE INDEX idx_tournament_members_tournament ON tournament_members(tournament_id);
CREATE INDEX idx_tournament_members_user ON tournament_members(user_id);

ALTER TABLE tournament_members ENABLE ROW LEVEL SECURITY;

-- Members/admins of a tournament can see co-members
CREATE POLICY "Tournament members can view co-members"
    ON tournament_members FOR SELECT
    TO authenticated
    USING (
        tournament_id IN (
            SELECT tm.tournament_id FROM tournament_members tm WHERE tm.user_id = auth.uid()
            UNION
            SELECT ta.tournament_id FROM tournament_admins ta WHERE ta.user_id = auth.uid()
        )
    );

-- =============================================================================
-- REPLACE tournament RLS: membership OR admin required to view
-- =============================================================================

DROP POLICY IF EXISTS "Tournament is viewable by authenticated users" ON tournament;

CREATE POLICY "Tournament viewable by members or admins"
    ON tournament FOR SELECT
    TO authenticated
    USING (
        id IN (
            SELECT tm.tournament_id FROM tournament_members tm WHERE tm.user_id = auth.uid()
            UNION
            SELECT ta.tournament_id FROM tournament_admins ta WHERE ta.user_id = auth.uid()
        )
    );

-- =============================================================================
-- REPLACE memes RLS: membership-gated
-- =============================================================================

DROP POLICY IF EXISTS "Memes are viewable by authenticated users" ON memes;

CREATE POLICY "Memes viewable by tournament members or admins"
    ON memes FOR SELECT
    TO authenticated
    USING (
        tournament_id IN (
            SELECT tm.tournament_id FROM tournament_members tm WHERE tm.user_id = auth.uid()
            UNION
            SELECT ta.tournament_id FROM tournament_admins ta WHERE ta.user_id = auth.uid()
        )
        OR tournament_id IS NULL
    );

-- =============================================================================
-- REPLACE rounds RLS: membership-gated
-- =============================================================================

DROP POLICY IF EXISTS "Rounds are viewable by authenticated users" ON rounds;

CREATE POLICY "Rounds viewable by tournament members or admins"
    ON rounds FOR SELECT
    TO authenticated
    USING (
        tournament_id IN (
            SELECT tm.tournament_id FROM tournament_members tm WHERE tm.user_id = auth.uid()
            UNION
            SELECT ta.tournament_id FROM tournament_admins ta WHERE ta.user_id = auth.uid()
        )
    );

-- =============================================================================
-- REPLACE matchups RLS: membership-gated via round -> tournament
-- =============================================================================

DROP POLICY IF EXISTS "Matchups are viewable by authenticated users" ON matchups;

CREATE POLICY "Matchups viewable by tournament members or admins"
    ON matchups FOR SELECT
    TO authenticated
    USING (
        round_id IN (
            SELECT r.id FROM rounds r WHERE r.tournament_id IN (
                SELECT tm.tournament_id FROM tournament_members tm WHERE tm.user_id = auth.uid()
                UNION
                SELECT ta.tournament_id FROM tournament_admins ta WHERE ta.user_id = auth.uid()
            )
        )
    );

-- =============================================================================
-- REPLACE votes RLS: membership-gated via matchup -> round -> tournament
-- =============================================================================

DROP POLICY IF EXISTS "Votes are viewable by authenticated users" ON votes;

CREATE POLICY "Votes viewable by tournament members or admins"
    ON votes FOR SELECT
    TO authenticated
    USING (
        matchup_id IN (
            SELECT m.id FROM matchups m
            JOIN rounds r ON r.id = m.round_id
            WHERE r.tournament_id IN (
                SELECT tm.tournament_id FROM tournament_members tm WHERE tm.user_id = auth.uid()
                UNION
                SELECT ta.tournament_id FROM tournament_admins ta WHERE ta.user_id = auth.uid()
            )
        )
    );
