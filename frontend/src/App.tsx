import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './hooks/useAuth';
import Header from './components/Header';
import LoginPage from './pages/LoginPage';
import SubmitPage from './pages/SubmitPage';
import BracketPage from './pages/BracketPage';
import VotingPage from './pages/VotingPage';
import AdminPage from './pages/AdminPage';
import './App.css';

function ProtectedLayout() {
  const { session, loading } = useAuth();

  if (loading) {
    return (
      <div className="loading-screen">
        <div className="loading-brand">
          <h1>Blueprint Talent Group</h1>
          <h2>Meme Madness 🏆</h2>
        </div>
        <div className="spinner" />
      </div>
    );
  }

  if (!session) return <LoginPage />;

  return (
    <div className="app-layout">
      <Header />
      <main className="app-main">
        <Routes>
          <Route path="/" element={<SubmitPage />} />
          <Route path="/bracket" element={<BracketPage />} />
          <Route path="/vote" element={<VotingPage />} />
          <Route path="/admin" element={<AdminPage />} />
          <Route path="*" element={<Navigate to="/" />} />
        </Routes>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <ProtectedLayout />
      </AuthProvider>
    </BrowserRouter>
  );
}
