import { useState, useEffect } from 'react';
import { useAuth } from '../hooks/useAuth';
import { fetchRounds, fetchRoundMatchups, castVote, fetchMyVote, fetchMatchupResults } from '../lib/api';
import { Round, Matchup } from '../types';
import { useTournament } from './TournamentLayout';

function VotingMatchup({ matchup, userId, onVoted }: { matchup: Matchup; userId: string; onVoted: () => void }) {
  const [myVote, setMyVote] = useState<string | null>(null);
  const [results, setResults] = useState<{ votes_a: number; votes_b: number } | null>(null);
  const [loading, setLoading] = useState(false);
  const [checkingVote, setCheckingVote] = useState(true);

  const isOwner =
    matchup.meme_a?.owner_id === userId ||
    matchup.meme_b?.owner_id === userId;

  useEffect(() => {
    fetchMyVote(matchup.id).then((data) => {
      if (data.voted) {
        setMyVote(data.vote.meme_id);
        fetchMatchupResults(matchup.id).then((r) => {
          if (r.can_see_results) setResults(r);
        });
      }
      setCheckingVote(false);
    });
  }, [matchup.id]);

  const handleVote = async (memeId: string) => {
    setLoading(true);
    try {
      await castVote(matchup.id, memeId);
      setMyVote(memeId);
      const r = await fetchMatchupResults(matchup.id);
      if (r.can_see_results) setResults(r);
      onVoted();
    } catch (err: any) {
      alert(err.message);
    } finally {
      setLoading(false);
    }
  };

  if (checkingVote) return <div className="matchup-vote-card loading">Loading...</div>;

  const isBye = !matchup.meme_b_id;
  if (isBye) return null;

  return (
    <div className={`matchup-vote-card ${myVote ? 'voted' : ''}`}>
      <div className={`vote-side ${myVote === matchup.meme_a_id ? 'selected' : ''}`}>
        {matchup.meme_a && (
          <>
            <img src={matchup.meme_a.image_url} alt={matchup.meme_a.title || 'Meme A'} className="vote-image" />
            <h4>{matchup.meme_a.title || 'Untitled'}</h4>
          </>
        )}
        {results && <div className="vote-count">{results.votes_a} votes</div>}
        {!myVote && !isOwner && matchup.status === 'voting' && (
          <button className="btn btn-vote" onClick={() => handleVote(matchup.meme_a_id)} disabled={loading}>
            Vote
          </button>
        )}
      </div>

      <div className="vote-vs">
        {isOwner ? (
          <span className="owner-badge">You're in this matchup</span>
        ) : myVote ? (
          <span className="voted-badge">Voted ✓</span>
        ) : (
          'VS'
        )}
      </div>

      <div className={`vote-side ${myVote === matchup.meme_b_id ? 'selected' : ''}`}>
        {matchup.meme_b && (
          <>
            <img src={matchup.meme_b.image_url} alt={matchup.meme_b.title || 'Meme B'} className="vote-image" />
            <h4>{matchup.meme_b.title || 'Untitled'}</h4>
          </>
        )}
        {results && <div className="vote-count">{results.votes_b} votes</div>}
        {!myVote && !isOwner && matchup.status === 'voting' && matchup.meme_b_id && (
          <button className="btn btn-vote" onClick={() => handleVote(matchup.meme_b_id!)} disabled={loading}>
            Vote
          </button>
        )}
      </div>
    </div>
  );
}

export default function VotingPage() {
  const { user } = useAuth();
  const { tournamentId } = useTournament();
  const [rounds, setRounds] = useState<Round[]>([]);
  const [activeRound, setActiveRound] = useState<number | null>(null);
  const [matchups, setMatchups] = useState<Matchup[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(0);
  const [total, setTotal] = useState(0);
  const PAGE_SIZE = 10;

  useEffect(() => {
    fetchRounds(tournamentId).then((data) => {
      setRounds(data);
      const votingRound = data.find((r: Round) => r.status === 'voting');
      if (votingRound) setActiveRound(votingRound.round_number);
      else if (data.length > 0) setActiveRound(data[data.length - 1].round_number);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, [tournamentId]);

  useEffect(() => {
    if (activeRound === null) return;
    setLoading(true);
    fetchRoundMatchups(tournamentId, activeRound, page * PAGE_SIZE, PAGE_SIZE)
      .then((data) => {
        setMatchups(data.matchups);
        setTotal(data.total);
      })
      .finally(() => setLoading(false));
  }, [tournamentId, activeRound, page]);

  if (loading && !matchups.length) return <div className="page"><p>Loading...</p></div>;

  if (!rounds.length) {
    return (
      <div className="page">
        <h2>Voting</h2>
        <div className="info-card"><p>No rounds available yet. Check back when the bracket is seeded!</p></div>
      </div>
    );
  }

  const totalPages = Math.ceil(total / PAGE_SIZE);

  return (
    <div className="page voting-page">
      <h2>Vote</h2>

      <div className="round-tabs">
        {rounds.map((r) => (
          <button
            key={r.round_number}
            className={`round-tab ${activeRound === r.round_number ? 'active' : ''} ${r.status}`}
            onClick={() => { setActiveRound(r.round_number); setPage(0); }}
          >
            Round {r.round_number}
            {r.status === 'voting' && <span className="live-dot" />}
          </button>
        ))}
      </div>

      <div className="voting-feed">
        {matchups.map((m) => (
          <VotingMatchup
            key={m.id}
            matchup={m}
            userId={user?.id || ''}
            onVoted={() => {
              fetchRoundMatchups(tournamentId, activeRound!, page * PAGE_SIZE, PAGE_SIZE).then((data) => {
                setMatchups(data.matchups);
              });
            }}
          />
        ))}
      </div>

      {totalPages > 1 && (
        <div className="pagination">
          <button className="btn btn-secondary" disabled={page === 0} onClick={() => setPage(page - 1)}>
            Previous
          </button>
          <span>Page {page + 1} of {totalPages}</span>
          <button className="btn btn-secondary" disabled={page >= totalPages - 1} onClick={() => setPage(page + 1)}>
            Next
          </button>
        </div>
      )}
    </div>
  );
}
