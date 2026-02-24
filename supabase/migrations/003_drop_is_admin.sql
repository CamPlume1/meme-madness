-- Migration 003: Drop legacy is_admin column from profiles
-- Admin status is now managed per-tournament via the tournament_admins table.

ALTER TABLE profiles DROP COLUMN IF EXISTS is_admin;
