import { NavLink } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';

export default function Header() {
  const { profile, signOut } = useAuth();

  return (
    <header className="app-header">
      <div className="header-brand">
        <h1>
          <span className="brand-company">Blueprint Talent Group</span>
          <span className="brand-event">Meme Madness 🏆</span>
        </h1>
      </div>
      <nav className="header-nav">
        <NavLink to="/" className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}>
          Submit
        </NavLink>
        <NavLink to="/bracket" className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}>
          Bracket
        </NavLink>
        <NavLink to="/vote" className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}>
          Vote
        </NavLink>
        {profile?.is_admin && (
          <NavLink to="/admin" className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}>
            Admin
          </NavLink>
        )}
      </nav>
      <div className="header-user">
        <span className="user-name">{profile?.display_name || profile?.email}</span>
        <button className="btn btn-sm btn-secondary" onClick={signOut}>Sign Out</button>
      </div>
    </header>
  );
}
