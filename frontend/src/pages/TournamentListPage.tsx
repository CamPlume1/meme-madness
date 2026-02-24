import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchTournaments, createTournament } from '../lib/api';
import { Tournament } from '../types';

export default function TournamentListPage() {
  const [tournaments, setTournaments] = useState<Tournament[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState('');
  const [error, setError] = useState('');
  const navigate = useNavigate();

  useEffect(() => {
    fetchTournaments()
      .then(setTournaments)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName.trim()) return;
    setCreating(true);
    setError('');
    try {
      const t = await createTournament(newName.trim());
      navigate(`/tournament/${t.id}/admin`);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setCreating(false);
    }
  };

  const active = tournaments.filter((t) => t.status !== 'complete');
  const completed = tournaments.filter((t) => t.status === 'complete');

  const getDefaultLink = (t: Tournament) => {
    if (t.status === 'submission_open') return `/tournament/${t.id}/submit`;
    if (t.status === 'voting_open') return `/tournament/${t.id}/vote`;
    return `/tournament/${t.id}/bracket`;
  };

  if (loading) {
    return (
      <div className="page" style={{ textAlign: 'center', padding: '3rem' }}>
        <div className="spinner" style={{ margin: '0 auto' }} />
      </div>
    );
  }

  return (
    <div className="page tournament-list-page">
      <div className="tournament-list-header">
        <h2>Tournaments</h2>
        <button className="btn btn-primary" onClick={() => setShowCreate(!showCreate)}>
          + New Tournament
        </button>
      </div>

      {showCreate && (
        <form className="create-tournament-form" onSubmit={handleCreate}>
          <input
            type="text"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="Tournament name (e.g. Meme Madness 2026)"
            required
          />
          <button type="submit" className="btn btn-accent" disabled={creating}>
            {creating ? 'Creating...' : 'Create'}
          </button>
          {error && <div className="error-message">{error}</div>}
        </form>
      )}

      {active.length > 0 && (
        <>
          <h3 className="section-title">Active</h3>
          <div className="tournament-grid">
            {active.map((t) => (
              <div
                key={t.id}
                className="tournament-card"
                onClick={() => navigate(getDefaultLink(t))}
              >
                <div className="tournament-card-header">
                  <h4>{t.name}</h4>
                  <span className={`status-badge status-${t.status}`}>
                    {t.status === 'submission_open' ? 'Submissions Open' : 'Voting'}
                  </span>
                </div>
                <div className="tournament-card-meta">
                  <span>{new Date(t.created_at).toLocaleDateString()}</span>
                  {t.user_role && (
                    <span className="role-badge">{t.user_role === 'owner' ? 'Owner' : 'Admin'}</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {completed.length > 0 && (
        <>
          <h3 className="section-title">Past Tournaments</h3>
          <div className="tournament-grid">
            {completed.map((t) => (
              <div
                key={t.id}
                className="tournament-card completed"
                onClick={() => navigate(`/tournament/${t.id}/bracket`)}
              >
                <div className="tournament-card-header">
                  <h4>{t.name}</h4>
                  <span className="status-badge status-complete">Complete</span>
                </div>
                <div className="tournament-card-meta">
                  <span>{new Date(t.created_at).toLocaleDateString()}</span>
                  {t.user_role && (
                    <span className="role-badge">{t.user_role === 'owner' ? 'Owner' : 'Admin'}</span>
                  )}
                  {t.total_rounds && <span>{t.total_rounds} rounds</span>}
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {tournaments.length === 0 && (
        <div className="info-card">
          <p>No tournaments yet. Create one to get started!</p>
        </div>
      )}
    </div>
  );
}
