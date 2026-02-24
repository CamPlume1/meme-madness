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

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
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
    throw new ApiError(err.detail || 'API error', res.status);
  }
  return res.json();
}

// Tournament list
export const fetchTournaments = () => apiFetch('/tournament/list');
export const fetchTournament = (tournamentId: string) =>
  apiFetch(`/tournament/${tournamentId}`);

// Tournament-scoped endpoints
export const fetchRounds = (tournamentId: string) =>
  apiFetch(`/tournament/${tournamentId}/rounds`);
export const fetchRoundMatchups = (tournamentId: string, roundNumber: number, offset = 0, limit = 50) =>
  apiFetch(`/tournament/${tournamentId}/rounds/${roundNumber}/matchups?offset=${offset}&limit=${limit}`);
export const fetchBracket = (tournamentId: string) =>
  apiFetch(`/tournament/${tournamentId}/bracket`);

// Memes
export const fetchAllMemes = (tournamentId?: string) =>
  apiFetch(`/memes/${tournamentId ? `?tournament_id=${tournamentId}` : ''}`);
export const fetchMyMemes = (tournamentId?: string) =>
  apiFetch(`/memes/mine${tournamentId ? `?tournament_id=${tournamentId}` : ''}`);
export const uploadMeme = (formData: FormData) =>
  apiFetch('/memes/upload', { method: 'POST', body: formData });

// Voting (matchup-level, no tournament ID needed)
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

// Admin — tournament creation (any authenticated user)
export const createTournament = (name = 'Meme Madness') =>
  apiFetch('/admin/tournament/create', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  });

// Admin — tournament-scoped
export const fetchAdminDashboard = (tournamentId: string) =>
  apiFetch(`/admin/tournament/${tournamentId}/dashboard`);
export const seedTournament = (tournamentId: string) =>
  apiFetch(`/admin/tournament/${tournamentId}/seed`, { method: 'POST' });
export const advanceRound = (tournamentId: string) =>
  apiFetch(`/admin/tournament/${tournamentId}/advance-round`, { method: 'POST' });
export const tieBreak = (tournamentId: string, matchupId: string, winnerId: string) =>
  apiFetch(`/admin/tournament/${tournamentId}/tie-break`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ matchup_id: matchupId, winner_id: winnerId }),
  });
export const closeMatchup = (tournamentId: string, matchupId: string) =>
  apiFetch(`/admin/tournament/${tournamentId}/matchup/${matchupId}/close`, { method: 'POST' });
export const closeAllMatchups = (tournamentId: string, roundId: string) =>
  apiFetch(`/admin/tournament/${tournamentId}/round/${roundId}/close-all`, { method: 'POST' });

// Admin — invite management
export const inviteAdmin = (tournamentId: string, email: string) =>
  apiFetch(`/admin/tournament/${tournamentId}/invite-admin`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email }),
  });
export const fetchTournamentAdmins = (tournamentId: string) =>
  apiFetch(`/admin/tournament/${tournamentId}/admins`);
export const removeAdmin = (tournamentId: string, userId: string) =>
  apiFetch(`/admin/tournament/${tournamentId}/admins/${userId}`, { method: 'DELETE' });

// Membership
export const joinTournament = (joinCode: string) =>
  apiFetch('/membership/join', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ join_code: joinCode }),
  });

// Admin — join code management
export const getJoinCode = (tournamentId: string) =>
  apiFetch(`/admin/tournament/${tournamentId}/join-code`);
export const regenerateJoinCode = (tournamentId: string) =>
  apiFetch(`/admin/tournament/${tournamentId}/regenerate-code`, { method: 'POST' });

// Admin — member management
export const fetchTournamentMembers = (tournamentId: string) =>
  apiFetch(`/admin/tournament/${tournamentId}/members`);
export const removeMember = (tournamentId: string, userId: string) =>
  apiFetch(`/admin/tournament/${tournamentId}/members/${userId}`, { method: 'DELETE' });
