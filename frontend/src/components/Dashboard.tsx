import React, { useState, useEffect } from 'react';
import api from '../lib/api';
import { Application } from '../lib/types';
import { AppForm } from './AppForm';
import { AppDetail } from './AppDetail';

interface DashboardProps {
  onSelectView: (view: 'dashboard' | 'bugs') => void;
  onSelectApp: (appId: number) => void;
}

export const Dashboard: React.FC<DashboardProps> = ({ onSelectView, onSelectApp }) => {
  const [applications, setApplications] = useState<Application[]>([]);
  const [showAddForm, setShowAddForm] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const fetchApplications = async () => {
    try {
      const response = await api.get<Application[]>('applications/');
      setApplications(response.data);
      setError('');
    } catch (err) {
      console.error(err);
      setError('Failed to fetch applications list.');
    } finally {
      setLoading(false);
    }
  };

  const fetchTimeoutRef = React.useRef<any>(null);
  const fetchApplicationsRef = React.useRef(fetchApplications);
  useEffect(() => {
    fetchApplicationsRef.current = fetchApplications;
  });

  const fetchApplicationsDebounced = React.useCallback(() => {
    if (fetchTimeoutRef.current) {
      clearTimeout(fetchTimeoutRef.current);
    }
    fetchTimeoutRef.current = setTimeout(() => {
      fetchApplicationsRef.current();
    }, 1500);
  }, []);

  useEffect(() => {
    fetchApplications();

    const token = localStorage.getItem('access_token');
    if (!token) return;

    const apiBase = (import.meta as any).env.VITE_API_URL || (typeof window !== 'undefined' ? window.location.origin + '/api/' : 'http://127.0.0.1:8000/api/');
    const sseBase = apiBase.replace('/api/', '/api/events/');
    const sseUrl = `${sseBase}?token=${encodeURIComponent(token)}`;

    const eventSource = new EventSource(sseUrl);

    eventSource.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        const { type } = payload;
        
        if (
          type.startsWith('application_') ||
          type.startsWith('bug_')
        ) {
          fetchApplicationsDebounced();
        }
      } catch (err) {
        console.error('Failed to parse SSE event on dashboard:', err);
      }
    };

    return () => {
      eventSource.close();
      if (fetchTimeoutRef.current) {
        clearTimeout(fetchTimeoutRef.current);
      }
    };
  }, []);

  const handleAppCreated = (newApp: Application) => {
    setApplications([newApp, ...applications]);
    setShowAddForm(false);
    onSelectApp(newApp.id); // Auto-navigate to details
  };

  const handleDeleteApp = async (id: number, url: string) => {
    if (window.confirm(`Are you sure you want to delete "${url}"? All pages, test cases, and bug logs will be permanently deleted.`)) {
      try {
        await api.delete(`applications/${id}/`);
        setApplications(applications.filter(app => app.id !== id));
      } catch (err) {
        console.error(err);
        setError('Failed to delete application environment.');
      }
    }
  };



  return (
    <div className="dashboard-container">
      <header className="dashboard-header">
        <div>
          <h2>🚀 Application Testing Hub</h2>
          <p className="subtitle-text">Monitor discovery, execute test plans, and resolve identified defects</p>
        </div>
        <button 
          onClick={() => setShowAddForm(true)} 
          className="btn-primary btn-add-app"
          disabled={showAddForm}
        >
          ➕ Register Application
        </button>
      </header>

      {error && <div className="error-alert">{error}</div>}

      {showAddForm && (
        <div className="add-app-overlay">
          <AppForm 
            onAppCreated={handleAppCreated} 
            onCancel={() => setShowAddForm(false)} 
          />
        </div>
      )}

      {loading ? (
        <div className="glass-card loading-state">
          <div className="spinner"></div>
          <p>Loading application environments...</p>
        </div>
      ) : applications.length === 0 ? (
        <div className="glass-card empty-dashboard-card">
          <div className="empty-icon">🌐</div>
          <h3>Register Your First Application</h3>
          <p>
            Start scanning and testing websites. Give us any URL and we'll automatically discover pages, 
            generate AI-driven tests, and search for bugs.
          </p>
          <button onClick={() => setShowAddForm(true)} className="btn-primary btn-lg">
            Get Started
          </button>
        </div>
      ) : (
        <div className="applications-grid">
          {applications.map((app) => (
            <div 
              key={app.id} 
              className="glass-card application-card"
              onClick={() => onSelectApp(app.id)}
            >
              <div className="app-card-header">
                <h4>{app.url}</h4>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span className={`status-dot status-${app.status.toLowerCase()}`}></span>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDeleteApp(app.id, app.url);
                    }}
                    title="Delete Application"
                    style={{
                      background: 'none',
                      border: 'none',
                      color: '#ff4d4d',
                      cursor: 'pointer',
                      fontSize: '1rem',
                      padding: '2px 4px',
                      borderRadius: '4px',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
                    🗑️
                  </button>
                </div>
              </div>
              <p className="app-card-url">Base: {app.base_url}</p>
              
              <div className="app-card-metrics">
                <div className="metric">
                  <span className="metric-lbl">Pages</span>
                  <span className="metric-val">{app.page_count}</span>
                </div>
                <div className="metric">
                  <span className="metric-lbl">APIs</span>
                  <span className="metric-val">{app.api_count}</span>
                </div>
                <div className="metric">
                  <span className="metric-lbl">Tests</span>
                  <span className="metric-val">{app.test_case_count}</span>
                </div>
                <div className="metric bug-metric">
                  <span className="metric-lbl">Bugs</span>
                  <span className="metric-val">{app.bug_count}</span>
                </div>
              </div>
              
              <div className="app-card-footer">
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span className="app-card-status">Status: <strong>{app.status}</strong></span>
                  {(() => {
                    const ind = app.industry ? app.industry.trim() : "";
                    if (!ind || ind === "General") {
                      return (
                        <span className="industry-badge industry-general" style={{
                          padding: '2px 6px',
                          borderRadius: '12px',
                          fontSize: '0.7rem',
                          fontWeight: 600,
                          backgroundColor: 'rgba(148, 163, 184, 0.15)',
                          color: '#94a3b8',
                          border: '1px solid rgba(148, 163, 184, 0.3)',
                          display: 'inline-block'
                        }}>
                          General
                        </span>
                      );
                    }
                    return (
                      <span className="industry-badge" style={{
                        padding: '2px 6px',
                        borderRadius: '12px',
                        fontSize: '0.7rem',
                        fontWeight: 600,
                        backgroundColor: 'rgba(99, 102, 241, 0.15)',
                        color: '#a5b4fc',
                        border: '1px solid rgba(99, 102, 241, 0.3)',
                        display: 'inline-block'
                      }}>
                        {ind}
                      </span>
                    );
                  })()}
                </div>
                <span className="btn-view-details">Configure →</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
