import { supabase } from './supabase';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

async function getAuthHeaders(): Promise<Record<string, string>> {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  if (!token) throw new Error('Not authenticated');
  return {
    Authorization: `Bearer ${token}`,
  };
}

async function apiFetch(path: string, options: RequestInit = {}) {
  const headers = await getAuthHeaders();
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      ...headers,
      ...options.headers,
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'API error');
  }
  return res.json();
}

// Memes
export const fetchAllMemes = () => apiFetch('/memes/');
export const fetchMyMemes = () => apiFetch('/memes/mine');
export const uploadMeme = (formData: FormData) =>
  apiFetch('/memes/upload', { method: 'POST', body: formData });

// Tournament
export const fetchTournament = () => apiFetch('/tournament/');
export const fetchRounds = () => apiFetch('/tournament/rounds');
export const fetchRoundMatchups = (roundNumber: number, offset = 0, limit = 50) =>
  apiFetch(`/tournament/rounds/${roundNumber}/matchups?offset=${offset}&limit=${limit}`);
export const fetchBracket = () => apiFetch('/tournament/bracket');

// Voting
export const castVote = (matchupId: string, memeId: string) =>
  apiFetch('/voting/vote', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ matchup_id: matchupId, meme_id: memeId }),
  });
export const fetchMyVote = (matchupId: string) =>
  apiFetch(`/voting/matchup/${matchupId}/my-vote`);
export const fetchMatchupResults = (matchupId: string) =>
  apiFetch(`/voting/matchup/${matchupId}/results`);

// Admin
export const fetchAdminDashboard = () => apiFetch('/admin/dashboard');
export const createTournament = (name = 'Meme Madness') =>
  apiFetch('/admin/tournament/create', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  });
export const seedTournament = (tournamentId: string) =>
  apiFetch(`/admin/tournament/${tournamentId}/seed`, { method: 'POST' });
export const advanceRound = (tournamentId: string) =>
  apiFetch(`/admin/tournament/${tournamentId}/advance-round`, { method: 'POST' });
export const tieBreak = (matchupId: string, winnerId: string) =>
  apiFetch('/admin/tournament/tie-break', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ matchup_id: matchupId, winner_id: winnerId }),
  });
export const closeMatchup = (matchupId: string) =>
  apiFetch(`/admin/matchup/${matchupId}/close`, { method: 'POST' });
export const closeAllMatchups = (roundId: string) =>
  apiFetch(`/admin/round/${roundId}/close-all`, { method: 'POST' });
