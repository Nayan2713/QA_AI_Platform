import React, { useState } from 'react';
import api from '../lib/api';
import { Application } from '../lib/types';

interface AppFormProps {
  onAppCreated: (newApp: Application) => void;
  onCancel: () => void;
}

export const AppForm: React.FC<AppFormProps> = ({ onAppCreated, onCancel }) => {
  const [url, setUrl] = useState('');
  const [loginUrl, setLoginUrl] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!url) {
      setError('Application URL is required');
      return;
    }

    setLoading(true);
    setError('');

    try {
      const response = await api.post<Application>('applications/', {
        url,
        login_url: loginUrl || null,
        username: username || null,
        password: password || null,
      });
      onAppCreated(response.data);
      setUrl('');
      setLoginUrl('');
      setUsername('');
      setPassword('');
    } catch (err: any) {
      console.error(err);
      setError(err.response?.data?.url?.[0] || err.response?.data?.detail || 'Failed to add application');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="glass-card form-card">
      <div className="card-header">
        <h3>🚀 Add New Application URL</h3>
        <p className="card-subtitle">Register your web application to begin automated QA flows</p>
      </div>

      <form onSubmit={handleSubmit} className="app-form">
        {error && <div className="error-alert">{error}</div>}

        <div className="form-group">
          <label htmlFor="app-url">Application Target URL *</label>
          <input
            id="app-url"
            type="url"
            placeholder="https://example.com"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            required
            className="form-input"
          />
          <span className="input-tip">The landing page or base URL of the site you want to test.</span>
        </div>

        <fieldset className="form-fieldset">
          <legend>🔑 Optional Login Credentials (For Authenticated Crawling)</legend>
          <p className="fieldset-tip">Provide these if the crawler needs to bypass a login page to discover inner pages.</p>

          <div className="form-group">
            <label htmlFor="login-url">Login Page URL</label>
            <input
              id="login-url"
              type="url"
              placeholder="https://example.com/login"
              value={loginUrl}
              onChange={(e) => setLoginUrl(e.target.value)}
              className="form-input"
            />
          </div>

          <div className="form-grid">
            <div className="form-group">
              <label htmlFor="username">Username / Email</label>
              <input
                id="username"
                type="text"
                placeholder="qa-test-user"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="form-input"
              />
            </div>

            <div className="form-group">
              <label htmlFor="password">Password</label>
              <input
                id="password"
                type="password"
                placeholder="••••••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="form-input"
              />
            </div>
          </div>
        </fieldset>

        <div className="form-actions">
          <button type="button" onClick={onCancel} className="btn-secondary" disabled={loading}>
            Cancel
          </button>
          <button type="submit" className="btn-primary" disabled={loading}>
            {loading ? 'Adding Site...' : 'Add and Proceed'}
          </button>
        </div>
      </form>
    </div>
  );
};
