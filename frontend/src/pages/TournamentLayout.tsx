import { useParams, Routes, Route, Navigate } from 'react-router-dom';
import { useState, useEffect, createContext, useContext } from 'react';
import { fetchTournament, fetchAdminDashboard } from '../lib/api';
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
  userRole: 'owner' | 'admin' | null;
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
  const [userRole, setUserRole] = useState<'owner' | 'admin' | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const loadTournament = async () => {
    if (!tournamentId) return;
    try {
      const data = await fetchTournament(tournamentId);
      setTournament(data);
      setUserRole(data.user_role || null);
      setIsAdmin(!!data.user_role);

      // Also verify admin dashboard access if user_role is set
      if (data.user_role) {
        try {
          await fetchAdminDashboard(tournamentId);
          setIsAdmin(true);
        } catch {
          setIsAdmin(false);
          setUserRole(null);
        }
      }
    } catch (err: any) {
      setError(err.message || 'Tournament not found');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    setLoading(true);
    loadTournament();
  }, [tournamentId]);

  if (loading) {
    return (
      <div className="page" style={{ textAlign: 'center', padding: '3rem' }}>
        <div className="spinner" style={{ margin: '0 auto' }} />
        <p style={{ marginTop: '1rem', color: 'var(--text-light)' }}>Loading tournament...</p>
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
    <TournamentContext.Provider value={{ tournament, tournamentId: tournamentId!, isAdmin, userRole, reload: loadTournament }}>
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
