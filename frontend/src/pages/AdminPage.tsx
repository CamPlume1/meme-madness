import { useState, useEffect } from 'react';
import { useAuth } from '../hooks/useAuth';
import {
  fetchAdminDashboard,
  createTournament,
  seedTournament,
  advanceRound,
  closeAllMatchups,
  tieBreak,
  fetchRoundMatchups,
} from '../lib/api';
import { AdminDashboard, Matchup, Round } from '../types';

export default function AdminPage() {
  const { profile } = useAuth();
  const [dashboard, setDashboard] = useState<AdminDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [roundMatchups, setRoundMatchups] = useState<Matchup[]>([]);
  const [viewingRound, setViewingRound] = useState<Round | null>(null);

  const loadDashboard = async () => {
    try {
      const data = await fetchAdminDashboard();
      setDashboard(data);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDashboard();
  }, []);

  const handleAction = async (action: string, fn: () => Promise<any>) => {
    setActionLoading(action);
    setError('');
    setMessage('');
    try {
      const result = await fn();
      setMessage(JSON.stringify(result, null, 2));
      loadDashboard();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setActionLoading('');
    }
  };

  const loadRoundMatchups = async (round: Round) => {
    setViewingRound(round);
    try {
      const data = await fetchRoundMatchups(round.round_number, 0, 100);
      setRoundMatchups(data.matchups);
    } catch (err: any) {
      setError(err.message);
    }
  };

  if (!profile?.is_admin) {
    return (
      <div className="page">
        <h2>Access Denied</h2>
        <p>You don't have admin privileges.</p>
      </div>
    );
  }

  if (loading) return <div className="page"><p>Loading admin dashboard...</p></div>;

  return (
    <div className="page admin-page">
      <h2>Admin Panel</h2>

      {/* Dashboard Summary */}
      {dashboard && (
        <div className="admin-summary">
          <div className="summary-card">
            <h4>Tournament</h4>
            <p>{dashboard.tournament?.name || 'None'}</p>
            <span className={`status-badge status-${dashboard.tournament?.status || 'none'}`}>
              {dashboard.tournament?.status || 'No tournament'}
            </span>
          </div>
          <div className="summary-card">
            <h4>Submissions</h4>
            <p className="big-number">{dashboard.memes_count}</p>
          </div>
          <div className="summary-card">
            <h4>Bracket Size</h4>
            <p className="big-number">{dashboard.bracket_size}</p>
            <span>{dashboard.num_byes} byes</span>
          </div>
          <div className="summary-card">
            <h4>Rounds</h4>
            <p className="big-number">{dashboard.total_rounds || '-'}</p>
            {dashboard.current_round && (
              <span>Current: Round {dashboard.current_round.round_number}</span>
            )}
          </div>
          {dashboard.current_round && (
            <div className="summary-card wide">
              <h4>Round {dashboard.current_round.round_number} Status</h4>
              <div className="round-stats">
                <span>Voting: {dashboard.current_round.voting}</span>
                <span>Complete: {dashboard.current_round.complete}</span>
                <span>Pending: {dashboard.current_round.pending}</span>
                <span>Total: {dashboard.current_round.total_matchups}</span>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Actions */}
      <div className="admin-actions">
        <h3>Actions</h3>

        {!dashboard?.tournament && (
          <button
            className="btn btn-primary"
            disabled={!!actionLoading}
            onClick={() => handleAction('create', () => createTournament())}
          >
            {actionLoading === 'create' ? 'Creating...' : 'Create Tournament'}
          </button>
        )}

        {dashboard?.tournament?.status === 'submission_open' && (
          <button
            className="btn btn-primary"
            disabled={!!actionLoading || dashboard.memes_count < 2}
            onClick={() => handleAction('seed', () => seedTournament(dashboard.tournament!.id))}
          >
            {actionLoading === 'seed' ? 'Seeding...' : `Close Submissions & Seed Bracket (${dashboard.memes_count} memes)`}
          </button>
        )}

        {dashboard?.tournament?.status === 'voting_open' && dashboard.current_round && (
          <>
            <button
              className="btn btn-accent"
              disabled={!!actionLoading}
              onClick={() => {
                const votingRound = dashboard.rounds.find(r => r.status === 'voting');
                if (votingRound) {
                  handleAction('close-all', () => closeAllMatchups(votingRound.id));
                }
              }}
            >
              {actionLoading === 'close-all' ? 'Closing...' : 'Close All Matchup Voting'}
            </button>

            <button
              className="btn btn-primary"
              disabled={!!actionLoading}
              onClick={() => handleAction('advance', () => advanceRound(dashboard.tournament!.id))}
            >
              {actionLoading === 'advance' ? 'Advancing...' : 'Advance to Next Round'}
            </button>
          </>
        )}
      </div>

      {/* Round Matchup Inspector */}
      {dashboard?.rounds && dashboard.rounds.length > 0 && (
        <div className="admin-rounds">
          <h3>Inspect Rounds</h3>
          <div className="round-tabs">
            {dashboard.rounds.map((r) => (
              <button
                key={r.round_number}
                className={`round-tab ${viewingRound?.id === r.id ? 'active' : ''} ${r.status}`}
                onClick={() => loadRoundMatchups(r)}
              >
                Round {r.round_number} ({r.status})
              </button>
            ))}
          </div>

          {viewingRound && (
            <div className="admin-matchups">
              {roundMatchups.map((m) => (
                <div key={m.id} className={`admin-matchup-card ${m.status}`}>
                  <div className="admin-matchup-memes">
                    <div className="admin-meme">
                      {m.meme_a && (
                        <>
                          <img src={m.meme_a.image_url} alt={m.meme_a.title || 'A'} />
                          <span>{m.meme_a.title || 'Untitled'}</span>
                        </>
                      )}
                      <span className="admin-votes">{m.votes_a ?? 0} votes</span>
                      {m.winner_id === m.meme_a_id && <span className="winner-badge">Winner</span>}
                    </div>

                    <div className="admin-vs">
                      {!m.meme_b_id ? 'BYE' : 'VS'}
                    </div>

                    <div className="admin-meme">
                      {m.meme_b ? (
                        <>
                          <img src={m.meme_b.image_url} alt={m.meme_b.title || 'B'} />
                          <span>{m.meme_b.title || 'Untitled'}</span>
                        </>
                      ) : (
                        <span className="bye-label">Auto-advance</span>
                      )}
                      <span className="admin-votes">{m.votes_b ?? 0} votes</span>
                      {m.winner_id === m.meme_b_id && m.meme_b_id && <span className="winner-badge">Winner</span>}
                    </div>
                  </div>

                  {/* Tie-break controls */}
                  {m.status !== 'complete' && m.meme_b_id && (m.votes_a ?? 0) === (m.votes_b ?? 0) && (
                    <div className="tie-break">
                      <span className="tie-label">TIE — Admin decision required:</span>
                      <button
                        className="btn btn-sm"
                        onClick={() => handleAction(`tiebreak-${m.id}`, () => tieBreak(m.id, m.meme_a_id))}
                        disabled={!!actionLoading}
                      >
                        Pick A
                      </button>
                      <button
                        className="btn btn-sm"
                        onClick={() => handleAction(`tiebreak-${m.id}`, () => tieBreak(m.id, m.meme_b_id!))}
                        disabled={!!actionLoading}
                      >
                        Pick B
                      </button>
                    </div>
                  )}

                  <div className="matchup-meta">
                    <span className={`status-badge status-${m.status}`}>{m.status}</span>
                    <span>Total votes: {m.total_votes ?? 0}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Messages */}
      {error && <div className="error-message">{error}</div>}
      {message && <pre className="result-output">{message}</pre>}
    </div>
  );
}
