import { useParams, Routes, Route, Navigate } from 'react-router-dom';
import { useState, useEffect, createContext, useContext } from 'react';
import { fetchTournament, fetchAdminDashboard, joinTournament, ApiError } from '../lib/api';
import { Tournament } from '../types';
import SubmitPage from './SubmitPage';
import BracketPage from './BracketPage';
import VotingPage from './VotingPage';
import AdminPage from './AdminPage';
import TournamentHeader from '../components/TournamentHeader';

interface TournamentContextType {
  tournament: Tournament;
  tournamentId: string;
  isAdmin: boolean;
  isMember: boolean;
  userRole: 'owner' | 'admin' | 'member' | null;
  reload: () => Promise<void>;
}

const TournamentContext = createContext<TournamentContextType | null>(null);

export function useTournament() {
  const ctx = useContext(TournamentContext);
  if (!ctx) throw new Error('useTournament must be used within TournamentLayout');
  return ctx;
}

export default function TournamentLayout() {
  const { tournamentId } = useParams<{ tournamentId: string }>();
  const [tournament, setTournament] = useState<Tournament | null>(null);
  const [isAdmin, setIsAdmin] = useState(false);
  const [isMember, setIsMember] = useState(false);
  const [userRole, setUserRole] = useState<'owner' | 'admin' | 'member' | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [errorStatus, setErrorStatus] = useState<number | null>(null);
  const [joinCode, setJoinCode] = useState('');
  const [joining, setJoining] = useState(false);
  const [joinError, setJoinError] = useState('');

  const loadTournament = async () => {
    if (!tournamentId) return;
    try {
      const data = await fetchTournament(tournamentId);
      setTournament(data);
      setUserRole(data.user_role || null);
      setIsMember(!!data.user_role);
      setIsAdmin(data.user_role === 'owner' || data.user_role === 'admin');
      setErrorStatus(null);
      setError('');

      // Verify admin dashboard access if user_role is admin/owner
      if (data.user_role === 'owner' || data.user_role === 'admin') {
        try {
          await fetchAdminDashboard(tournamentId);
          setIsAdmin(true);
        } catch {
          setIsAdmin(false);
        }
      }
    } catch (err: any) {
      const status = err instanceof ApiError ? err.status : null;
      setErrorStatus(status);
      setError(err.message || 'Tournament not found');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    setLoading(true);
    loadTournament();
  }, [tournamentId]);

  const handleJoin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!joinCode.trim()) return;
    setJoining(true);
    setJoinError('');
    try {
      await joinTournament(joinCode.trim());
      setJoinCode('');
      setLoading(true);
      await loadTournament();
    } catch (err: any) {
      setJoinError(err.message);
    } finally {
      setJoining(false);
    }
  };

  if (loading) {
    return (
      <div className="page" style={{ textAlign: 'center', padding: '3rem' }}>
        <div className="spinner" style={{ margin: '0 auto' }} />
        <p style={{ marginTop: '1rem', color: 'var(--text-light)' }}>Loading tournament...</p>
      </div>
    );
  }

  if (errorStatus === 403) {
    return (
      <div className="page">
        <div className="info-card">
          <h3>Not a Member</h3>
          <p>You don't have access to this tournament. Enter a join code to become a member.</p>
          <form className="join-tournament-form" onSubmit={handleJoin} style={{ marginTop: '1rem' }}>
            <input
              type="text"
              value={joinCode}
              onChange={(e) => setJoinCode(e.target.value.toUpperCase())}
              placeholder="Enter join code"
              maxLength={8}
              required
            />
            <button type="submit" className="btn btn-primary" disabled={joining}>
              {joining ? 'Joining...' : 'Join'}
            </button>
          </form>
          {joinError && <div className="error-message" style={{ marginTop: '0.5rem' }}>{joinError}</div>}
        </div>
      </div>
    );
  }

  if (error || !tournament) {
    return (
      <div className="page">
        <div className="info-card">
          <h3>Tournament Not Found</h3>
          <p>{error || 'This tournament does not exist.'}</p>
        </div>
      </div>
    );
  }

  return (
    <TournamentContext.Provider value={{ tournament, tournamentId: tournamentId!, isAdmin, isMember, userRole, reload: loadTournament }}>
      <TournamentHeader />
      <Routes>
        <Route path="submit" element={<SubmitPage />} />
        <Route path="bracket" element={<BracketPage />} />
        <Route path="vote" element={<VotingPage />} />
        <Route path="admin" element={<AdminPage />} />
        <Route path="" element={<Navigate to="bracket" />} />
      </Routes>
    </TournamentContext.Provider>
  );
}
