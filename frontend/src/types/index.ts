export interface Profile {
  id: string;
  email: string;
  display_name: string;
}

export interface Meme {
  id: string;
  owner_id: string;
  title: string;
  image_url: string;
  submitted_at: string;
  tournament_id?: string;
  tournament_status?: string;
  profiles?: { display_name: string };
}

export interface Tournament {
  id: string;
  name: string;
  status: 'submission_open' | 'voting_open' | 'complete';
  total_rounds: number | null;
  created_at: string;
  created_by?: string;
  user_role?: 'owner' | 'admin' | 'member' | null;
  join_code?: string;
}

export interface Round {
  id: string;
  tournament_id: string;
  round_number: number;
  status: 'pending' | 'voting' | 'complete';
}

export interface Matchup {
  id: string;
  round_id: string;
  meme_a_id: string;
  meme_b_id: string | null;
  winner_id: string | null;
  status: 'pending' | 'voting' | 'complete';
  next_matchup_id: string | null;
  position: number;
  meme_a?: Meme;
  meme_b?: Meme | null;
  votes_a?: number;
  votes_b?: number;
  total_votes?: number;
}

export interface Vote {
  id: string;
  matchup_id: string;
  voter_id: string;
  meme_id: string;
}

export interface BracketRound {
  round: Round;
  matchups: Matchup[];
}

export interface BracketData {
  tournament: Tournament;
  rounds: BracketRound[];
}

export interface TournamentAdmin {
  id: string;
  tournament_id: string;
  user_id: string;
  role: 'owner' | 'admin';
  invited_by: string | null;
  created_at: string;
  profiles?: { display_name: string; email: string };
}

export interface AdminDashboard {
  tournament: Tournament;
  memes_count: number;
  bracket_size: number;
  num_byes: number;
  total_rounds: number | null;
  current_round: {
    round_number: number;
    total_matchups: number;
    voting: number;
    complete: number;
    pending: number;
  } | null;
  rounds: Round[];
}

export interface TournamentMember {
  id: string;
  tournament_id: string;
  user_id: string;
  joined_at: string;
  profiles?: { display_name: string; email: string };
}

export interface JoinResult {
  tournament_id: string;
  name: string;
  already_member: boolean;
}
