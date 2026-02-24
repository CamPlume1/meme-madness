import { NavLink } from 'react-router-dom';
import { useTournament } from '../pages/TournamentLayout';

export default function TournamentHeader() {
  const { tournament, tournamentId, isAdmin } = useTournament();

  return (
    <div className="tournament-subheader">
      <div className="tournament-subheader-info">
        <h2 className="tournament-name">{tournament.name}</h2>
        <span className={`status-badge status-${tournament.status}`}>
          {tournament.status === 'submission_open' && 'Submissions Open'}
          {tournament.status === 'voting_open' && 'Voting In Progress'}
          {tournament.status === 'complete' && 'Complete'}
        </span>
      </div>
      <nav className="tournament-nav">
        <NavLink
          to={`/tournament/${tournamentId}/submit`}
          className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
        >
          Submit
        </NavLink>
        <NavLink
          to={`/tournament/${tournamentId}/bracket`}
          className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
        >
          Bracket
        </NavLink>
        <NavLink
          to={`/tournament/${tournamentId}/vote`}
          className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
        >
          Vote
        </NavLink>
        {isAdmin && (
          <NavLink
            to={`/tournament/${tournamentId}/admin`}
            className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
          >
            Admin
          </NavLink>
        )}
      </nav>
    </div>
  );
}
