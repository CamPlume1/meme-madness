import { useState, useEffect } from 'react';
import { uploadMeme, fetchMyMemes, deleteMeme } from '../lib/api';
import { Meme } from '../types';
import { useTournament } from './TournamentLayout';

export default function SubmitPage() {
  const { tournament, tournamentId } = useTournament();
  const [myMemes, setMyMemes] = useState<Meme[]>([]);
  const [title, setTitle] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const loadData = async () => {
    try {
      const memes = await fetchMyMemes(tournamentId);
      setMyMemes(memes);
    } catch {
      // ignore
    }
  };

  useEffect(() => {
    loadData();
  }, [tournamentId]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) {
      setFile(f);
      setPreview(URL.createObjectURL(f));
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file || !title.trim()) return;
    setLoading(true);
    setError('');
    setSuccess('');

    const formData = new FormData();
    formData.append('file', file);
    formData.append('title', title);
    formData.append('tournament_id', tournamentId);

    try {
      await uploadMeme(formData);
      setSuccess('Meme submitted successfully!');
      setTitle('');
      setFile(null);
      setPreview(null);
      loadData();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (memeId: string) => {
    if (!confirm('Are you sure you want to delete this meme?')) return;
    setDeleting(memeId);
    setError('');
    try {
      await deleteMeme(memeId, tournamentId);
      loadData();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setDeleting(null);
    }
  };

  const submissionsOpen = tournament.status === 'submission_open';
  const atLimit = myMemes.length >= 2;

  return (
    <div className="page submit-page">
      <h2>Submit Your Meme</h2>

      {!submissionsOpen && (
        <div className="info-card">
          <p>Submissions are closed. The tournament is {tournament.status === 'voting_open' ? 'in progress' : 'complete'}!</p>
        </div>
      )}

      {submissionsOpen && atLimit && (
        <div className="info-card limit-reached">
          <h3>Submission Limit Reached</h3>
          <p>You've already submitted 2 memes — that's the max! Good luck in the tournament.</p>
        </div>
      )}

      {submissionsOpen && !atLimit && (
        <form className="upload-form" onSubmit={handleSubmit}>
          <div className="form-group">
            <label htmlFor="title">Meme Title</label>
            <input
              id="title"
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Give your meme a name..."
              required
            />
          </div>

          <div className="form-group">
            <label htmlFor="file">Image</label>
            <input
              id="file"
              type="file"
              accept="image/*"
              onChange={handleFileChange}
              required
            />
          </div>

          {preview && (
            <div className="image-preview">
              <img src={preview} alt="Preview" />
            </div>
          )}

          {error && <div className="error-message">{error}</div>}
          {success && <div className="success-message">{success}</div>}

          <button type="submit" className="btn btn-primary" disabled={loading || !file || !title.trim()}>
            {loading ? 'Uploading...' : 'Submit Meme'}
          </button>

          <p className="submissions-count">{myMemes.length}/2 submissions used</p>
        </form>
      )}

      <h3>My Submissions</h3>
      {myMemes.length === 0 ? (
        <p className="empty-state">You haven't submitted any memes yet.</p>
      ) : (
        <div className="meme-grid">
          {myMemes.map((meme) => (
            <div key={meme.id} className="meme-card">
              <img src={meme.image_url} alt={meme.title || 'Meme'} />
              <div className="meme-info">
                <h4>{meme.title || 'Untitled'}</h4>
                <span className="meme-date">
                  {new Date(meme.submitted_at).toLocaleDateString()}
                </span>
                {meme.tournament_status && (
                  <span className={`status-badge status-${meme.tournament_status}`}>
                    {meme.tournament_status === 'active' && 'In Tournament'}
                    {meme.tournament_status === 'eliminated' && 'Eliminated'}
                    {meme.tournament_status === 'bye_advanced' && 'BYE — Advanced'}
                    {meme.tournament_status === 'advanced' && 'Advanced'}
                    {meme.tournament_status === 'not_in_bracket' && 'Awaiting Bracket'}
                  </span>
                )}
                {submissionsOpen && (
                  <button
                    className="btn btn-danger btn-sm"
                    onClick={() => handleDelete(meme.id)}
                    disabled={deleting === meme.id}
                  >
                    {deleting === meme.id ? 'Deleting...' : 'Delete'}
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
