import { useState, useEffect } from 'react';
import { fetchBracket } from '../lib/api';
import { BracketData, Matchup, Meme } from '../types';
import { useTournament } from './TournamentLayout';

function MemeModal({ meme, onClose }: { meme: Meme; onClose: () => void }) {
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [onClose]);

  return (
    <div className="meme-modal-overlay" onClick={onClose}>
      <div className="meme-modal" onClick={(e) => e.stopPropagation()}>
        <button className="meme-modal-close" onClick={onClose}>&times;</button>
        <img src={meme.image_url} alt={meme.title || 'Meme'} className="meme-modal-image" />
        <div className="meme-modal-info">
          <h3>{meme.title || 'Untitled'}</h3>
          {meme.profiles?.display_name && (
            <p className="meme-modal-author">by {meme.profiles.display_name}</p>
          )}
        </div>
      </div>
    </div>
  );
}

function MatchupCard({ matchup, compact, onMemeClick }: { matchup: Matchup; compact?: boolean; onMemeClick: (meme: Meme) => void }) {
  const isBye = !matchup.meme_b_id;
  const isComplete = matchup.status === 'complete';

  return (
    <div className={`matchup-card ${isComplete ? 'complete' : ''} ${isBye ? 'bye' : ''} ${compact ? 'compact' : ''}`}>
      <div className={`matchup-entry ${isComplete && matchup.winner_id === matchup.meme_a_id ? 'winner' : ''}`}>
        {matchup.meme_a ? (
          <>
            <img
              src={matchup.meme_a.image_url}
              alt={matchup.meme_a.title || 'Meme A'}
              className="matchup-thumb clickable"
              onClick={() => onMemeClick(matchup.meme_a!)}
            />
            <span className="matchup-name clickable" onClick={() => onMemeClick(matchup.meme_a!)}>{matchup.meme_a.title || 'Untitled'}</span>
          </>
        ) : (
          <span className="matchup-name">TBD</span>
        )}
        {isComplete && matchup.winner_id === matchup.meme_a_id && <span className="winner-badge">W</span>}
      </div>

      <div className="matchup-vs">{isBye ? 'BYE' : 'VS'}</div>

      <div className={`matchup-entry ${isComplete && matchup.winner_id === matchup.meme_b_id ? 'winner' : ''}`}>
        {isBye ? (
          <span className="matchup-name bye-label">Auto-advance</span>
        ) : matchup.meme_b ? (
          <>
            <img
              src={matchup.meme_b.image_url}
              alt={matchup.meme_b.title || 'Meme B'}
              className="matchup-thumb clickable"
              onClick={() => onMemeClick(matchup.meme_b!)}
            />
            <span className="matchup-name clickable" onClick={() => onMemeClick(matchup.meme_b!)}>{matchup.meme_b.title || 'Untitled'}</span>
          </>
        ) : (
          <span className="matchup-name">TBD</span>
        )}
        {isComplete && matchup.winner_id === matchup.meme_b_id && <span className="winner-badge">W</span>}
      </div>
    </div>
  );
}

export default function BracketPage() {
  const { tournamentId } = useTournament();
  const [bracket, setBracket] = useState<BracketData | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeRound, setActiveRound] = useState(1);
  const [selectedMeme, setSelectedMeme] = useState<Meme | null>(null);

  useEffect(() => {
    setLoading(true);
    fetchBracket(tournamentId)
      .then((data) => {
        setBracket(data);
        if (data.rounds.length > 0) {
          const active = data.rounds.find((r: any) => r.round.status !== 'complete');
          if (active) setActiveRound(active.round.round_number);
          else setActiveRound(data.rounds[data.rounds.length - 1].round.round_number);
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [tournamentId]);

  if (loading) return <div className="page"><p>Loading bracket...</p></div>;

  if (!bracket || !bracket.rounds.length) {
    return (
      <div className="page">
        <h2>Tournament Bracket</h2>
        <div className="info-card">
          <p>The bracket hasn't been seeded yet. Check back once submissions close!</p>
        </div>
      </div>
    );
  }

  const totalRounds = bracket.tournament.total_rounds || bracket.rounds.length;
  const isLarge = bracket.rounds[0]?.matchups.length > 32;

  return (
    <div className="page bracket-page">
      <div className="bracket-header">
        <h2>Tournament Bracket</h2>
        <div className="bracket-info">
          <span className="badge">Round {activeRound} of {totalRounds}</span>
          <span className="badge">{bracket.tournament.status === 'complete' ? 'Complete' : 'In Progress'}</span>
        </div>
      </div>

      <div className="round-tabs">
        {bracket.rounds.map((r) => (
          <button
            key={r.round.round_number}
            className={`round-tab ${activeRound === r.round.round_number ? 'active' : ''} ${r.round.status}`}
            onClick={() => setActiveRound(r.round.round_number)}
          >
            {r.round.round_number === totalRounds ? 'Final' :
              r.round.round_number === totalRounds - 1 ? 'Semis' :
              `Round ${r.round.round_number}`}
            <span className="round-tab-status">
              {r.round.status === 'complete' ? '✓' : r.round.status === 'voting' ? '•' : ''}
            </span>
          </button>
        ))}
      </div>

      {isLarge ? (
        <div className="bracket-single-round">
          {bracket.rounds
            .filter((r) => r.round.round_number === activeRound)
            .map((r) => (
              <div key={r.round.id} className="bracket-round">
                <h3>
                  {r.round.round_number === totalRounds ? 'Final' :
                    r.round.round_number === totalRounds - 1 ? 'Semifinals' :
                    `Round ${r.round.round_number}`}
                  {' '}({r.matchups.length} matchups)
                </h3>
                <div className="matchup-list">
                  {r.matchups.map((m) => (
                    <MatchupCard key={m.id} matchup={m} onMemeClick={setSelectedMeme} />
                  ))}
                </div>
              </div>
            ))}
        </div>
      ) : (
        <div className="bracket-scroll">
          {bracket.rounds.map((r) => (
            <div key={r.round.id} className="bracket-round-col">
              <h3>
                {r.round.round_number === totalRounds ? 'Final' :
                  r.round.round_number === totalRounds - 1 ? 'Semis' :
                  `R${r.round.round_number}`}
              </h3>
              <div className="matchup-col">
                {r.matchups.map((m) => (
                  <MatchupCard key={m.id} matchup={m} compact onMemeClick={setSelectedMeme} />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {bracket.tournament.status === 'complete' && (
        <div className="champion-banner">
          <h2>🏆 Champion! 🏆</h2>
          {bracket.rounds[bracket.rounds.length - 1]?.matchups[0] && (
            <div className="champion-meme">
              {(() => {
                const final = bracket.rounds[bracket.rounds.length - 1].matchups[0];
                const winnerMeme = final.winner_id === final.meme_a_id ? final.meme_a : final.meme_b;
                return winnerMeme ? (
                  <>
                    <img src={winnerMeme.image_url} alt={winnerMeme.title || 'Champion'} />
                    <h3>{winnerMeme.title || 'Untitled'}</h3>
                  </>
                ) : null;
              })()}
            </div>
          )}
        </div>
      )}

      {selectedMeme && (
        <MemeModal meme={selectedMeme} onClose={() => setSelectedMeme(null)} />
      )}
    </div>
  );
}
