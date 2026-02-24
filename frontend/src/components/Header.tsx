import { NavLink } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';

export default function Header() {
  const { profile, signOut } = useAuth();

  return (
    <header className="app-header">
      <div className="header-brand">
        <NavLink to="/" style={{ textDecoration: 'none', color: 'inherit' }}>
          <h1>
            <span className="brand-company">Blueprint Talent Group</span>
            <span className="brand-event">Meme Madness 🏆</span>
          </h1>
        </NavLink>
      </div>
      <nav className="header-nav">
        <NavLink to="/" className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'} end>
          Tournaments
        </NavLink>
      </nav>
      <div className="header-user">
        <span className="user-name">{profile?.display_name || profile?.email}</span>
        <button className="btn btn-sm btn-secondary" onClick={signOut}>Sign Out</button>
      </div>
    </header>
  );
}
