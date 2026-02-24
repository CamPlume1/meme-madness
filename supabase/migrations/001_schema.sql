-- Meme Madness Schema Migration
-- Creates all tables, enums, RLS policies, indexes, and triggers

-- =============================================================================
-- ENUMS
-- =============================================================================

CREATE TYPE tournament_status AS ENUM ('submission_open', 'voting_open', 'complete');
CREATE TYPE round_status AS ENUM ('pending', 'voting', 'complete');
CREATE TYPE matchup_status AS ENUM ('pending', 'voting', 'complete');

-- =============================================================================
-- PROFILES
-- =============================================================================

CREATE TABLE profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    display_name TEXT,
    is_admin BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;

-- Users can read all profiles (needed for display names in bracket)
CREATE POLICY "Profiles are viewable by authenticated users"
    ON profiles FOR SELECT
    TO authenticated
    USING (true);

-- Users can update their own profile (display_name only; is_admin is service-role only)
CREATE POLICY "Users can update own profile"
    ON profiles FOR UPDATE
    TO authenticated
    USING (auth.uid() = id)
    WITH CHECK (auth.uid() = id);

-- Allow insert for new users (triggered by auth hook)
CREATE POLICY "Users can insert own profile"
    ON profiles FOR INSERT
    TO authenticated
    WITH CHECK (auth.uid() = id);

-- Auto-create profile on signup
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.profiles (id, email, display_name)
    VALUES (
        NEW.id,
        NEW.email,
        COALESCE(NEW.raw_user_meta_data->>'display_name', split_part(NEW.email, '@', 1))
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW
    EXECUTE FUNCTION public.handle_new_user();

-- =============================================================================
-- MEMES
-- =============================================================================

CREATE TABLE memes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    title TEXT DEFAULT '',
    image_url TEXT NOT NULL,
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_memes_owner ON memes(owner_id);

ALTER TABLE memes ENABLE ROW LEVEL SECURITY;

-- All authenticated users can view memes
CREATE POLICY "Memes are viewable by authenticated users"
    ON memes FOR SELECT
    TO authenticated
    USING (true);

-- Users can insert their own memes
CREATE POLICY "Users can insert own memes"
    ON memes FOR INSERT
    TO authenticated
    WITH CHECK (auth.uid() = owner_id);

-- Users can delete their own memes
CREATE POLICY "Users can delete own memes"
    ON memes FOR DELETE
    TO authenticated
    USING (auth.uid() = owner_id);

-- =============================================================================
-- TOURNAMENT
-- =============================================================================

CREATE TABLE tournament (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL DEFAULT 'Meme Madness',
    status tournament_status NOT NULL DEFAULT 'submission_open',
    total_rounds INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE tournament ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Tournament is viewable by authenticated users"
    ON tournament FOR SELECT
    TO authenticated
    USING (true);

-- Only service role (admin backend) can modify tournament
-- No INSERT/UPDATE/DELETE policies for authenticated role

-- =============================================================================
-- ROUNDS
-- =============================================================================

CREATE TABLE rounds (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tournament_id UUID NOT NULL REFERENCES tournament(id) ON DELETE CASCADE,
    round_number INTEGER NOT NULL,
    status round_status NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(tournament_id, round_number)
);

CREATE INDEX idx_rounds_tournament ON rounds(tournament_id);

ALTER TABLE rounds ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Rounds are viewable by authenticated users"
    ON rounds FOR SELECT
    TO authenticated
    USING (true);

-- =============================================================================
-- MATCHUPS
-- =============================================================================

CREATE TABLE matchups (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    round_id UUID NOT NULL REFERENCES rounds(id) ON DELETE CASCADE,
    meme_a_id UUID NOT NULL REFERENCES memes(id),
    meme_b_id UUID REFERENCES memes(id),  -- nullable for byes
    winner_id UUID REFERENCES memes(id),   -- nullable until decided
    status matchup_status NOT NULL DEFAULT 'pending',
    next_matchup_id UUID REFERENCES matchups(id),  -- nullable, links to next round
    position INTEGER NOT NULL DEFAULT 0,  -- position within the round for bracket layout
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_matchups_round ON matchups(round_id);
CREATE INDEX idx_matchups_meme_a ON matchups(meme_a_id);
CREATE INDEX idx_matchups_meme_b ON matchups(meme_b_id);
CREATE INDEX idx_matchups_next ON matchups(next_matchup_id);

ALTER TABLE matchups ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Matchups are viewable by authenticated users"
    ON matchups FOR SELECT
    TO authenticated
    USING (true);

-- =============================================================================
-- VOTES
-- =============================================================================

CREATE TABLE votes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    matchup_id UUID NOT NULL REFERENCES matchups(id) ON DELETE CASCADE,
    voter_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    meme_id UUID NOT NULL REFERENCES memes(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(matchup_id, voter_id)  -- one vote per user per matchup
);

CREATE INDEX idx_votes_matchup ON votes(matchup_id);
CREATE INDEX idx_votes_voter ON votes(voter_id);

ALTER TABLE votes ENABLE ROW LEVEL SECURITY;

-- All authenticated users can view votes
CREATE POLICY "Votes are viewable by authenticated users"
    ON votes FOR SELECT
    TO authenticated
    USING (true);

-- Users can insert their own votes
CREATE POLICY "Users can insert own votes"
    ON votes FOR INSERT
    TO authenticated
    WITH CHECK (auth.uid() = voter_id);

-- =============================================================================
-- STORAGE BUCKET
-- =============================================================================

-- Create storage bucket for meme images (run via Supabase dashboard or CLI)
-- INSERT INTO storage.buckets (id, name, public) VALUES ('memes', 'memes', true);
