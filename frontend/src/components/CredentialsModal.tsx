import React, { useState } from 'react';
import { createPortal } from 'react-dom';
import api from '../lib/api';
import { Application } from '../lib/types';

interface CredentialsModalProps {
  app: Application;
  onClose: () => void;
  onSuccess: (updatedApp: Application, taskId?: string, message?: string) => void;
}

export const CredentialsModal: React.FC<CredentialsModalProps> = ({ app, onClose, onSuccess }) => {
  const [loginUrl, setLoginUrl] = useState(app.login_url || '');
  const [username, setUsername] = useState(app.username || '');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSave = async (runDiscovery: boolean) => {
    setLoading(true);
    setError('');

    try {
      const payload: any = {
        login_url: loginUrl || null,
        username: username || null,
        run_discovery: runDiscovery
      };
      if (password) {
        payload.password = password;
      }

      const res = await api.post(`applications/${app.id}/update-credentials/`, payload);

      const updatedApp = res.data.application || app;
      const taskId = res.data.task_id;
      const message = res.data.message || (runDiscovery ? 'Credentials saved and discovery launched!' : 'Credentials saved successfully.');
      onSuccess(updatedApp, taskId, message);
    } catch (err: any) {
      console.error('Failed to update application credentials:', err);
      setError(err.response?.data?.error || err.response?.data?.message || 'Failed to update credentials. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return createPortal(
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content glass-card" onClick={e => e.stopPropagation()} style={{ maxWidth: '520px', padding: '24px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <h3 style={{ margin: 0, fontSize: '1.25rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
            🔑 Update Target Login Credentials
          </h3>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#fff', fontSize: '1.2rem', cursor: 'pointer' }}>
            ✕
          </button>
        </div>

        <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: '20px' }}>
          Update authentication credentials for <code>{app.url}</code>. Updating credentials automatically resets previous browser sessions so discovery & test runners use the new credentials.
        </p>

        {error && (
          <div style={{
            padding: '10px 14px',
            background: 'rgba(239, 68, 68, 0.15)',
            border: '1px solid rgba(239, 68, 68, 0.3)',
            borderRadius: '8px',
            color: '#f87171',
            fontSize: '0.85rem',
            marginBottom: '16px'
          }}>
            🚨 {error}
          </div>
        )}

        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', marginBottom: '24px' }}>
          <div>
            <label style={{ display: 'block', fontSize: '0.8rem', color: 'rgba(255, 255, 255, 0.7)', marginBottom: '6px' }}>
              Login Page URL
            </label>
            <input
              type="url"
              placeholder="e.g. https://example.com/login"
              value={loginUrl}
              onChange={e => setLoginUrl(e.target.value)}
              style={{
                width: '100%',
                padding: '10px 14px',
                background: 'rgba(20, 20, 30, 0.7)',
                border: '1px solid rgba(255, 255, 255, 0.1)',
                borderRadius: '8px',
                color: '#fff',
                fontSize: '0.9rem'
              }}
            />
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '0.8rem', color: 'rgba(255, 255, 255, 0.7)', marginBottom: '6px' }}>
              Username / Email
            </label>
            <input
              type="text"
              placeholder="e.g. admin@example.com"
              value={username}
              onChange={e => setUsername(e.target.value)}
              style={{
                width: '100%',
                padding: '10px 14px',
                background: 'rgba(20, 20, 30, 0.7)',
                border: '1px solid rgba(255, 255, 255, 0.1)',
                borderRadius: '8px',
                color: '#fff',
                fontSize: '0.9rem'
              }}
            />
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '0.8rem', color: 'rgba(255, 255, 255, 0.7)', marginBottom: '6px' }}>
              Password (leave empty to keep current password)
            </label>
            <input
              type="password"
              placeholder="••••••••"
              value={password}
              onChange={e => setPassword(e.target.value)}
              style={{
                width: '100%',
                padding: '10px 14px',
                background: 'rgba(20, 20, 30, 0.7)',
                border: '1px solid rgba(255, 255, 255, 0.1)',
                borderRadius: '8px',
                color: '#fff',
                fontSize: '0.9rem'
              }}
            />
          </div>
        </div>

        <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end', flexWrap: 'wrap' }}>
          <button
            type="button"
            onClick={onClose}
            disabled={loading}
            style={{
              padding: '10px 18px',
              background: 'rgba(255, 255, 255, 0.05)',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              borderRadius: '8px',
              color: '#fff',
              cursor: 'pointer',
              fontWeight: 600,
              fontSize: '0.85rem'
            }}
          >
            Cancel
          </button>

          <button
            type="button"
            onClick={() => handleSave(false)}
            disabled={loading}
            style={{
              padding: '10px 18px',
              background: 'rgba(139, 92, 246, 0.2)',
              border: '1px solid rgba(139, 92, 246, 0.4)',
              borderRadius: '8px',
              color: '#c084fc',
              cursor: 'pointer',
              fontWeight: 600,
              fontSize: '0.85rem'
            }}
          >
            {loading ? 'Saving...' : '💾 Save Credentials'}
          </button>

          <button
            type="button"
            onClick={() => handleSave(true)}
            disabled={loading}
            style={{
              padding: '10px 18px',
              background: 'linear-gradient(135deg, #6366f1 0%, #a855f7 100%)',
              border: 'none',
              borderRadius: '8px',
              color: '#fff',
              cursor: 'pointer',
              fontWeight: 600,
              fontSize: '0.85rem',
              boxShadow: '0 4px 12px rgba(168, 85, 247, 0.3)'
            }}
          >
            {loading ? 'Starting...' : '🚀 Save & Run Discovery'}
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
};

