import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import api from '../lib/api';
import { Application } from '../lib/types';
import { AppForm } from './AppForm';

export const Dashboard: React.FC = () => {
  const [showAddForm, setShowAddForm] = useState(false);
  const [error, setError] = useState('');
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: applications = [], isLoading, refetch } = useQuery({
    queryKey: ['applications'],
    queryFn: async () => {
      const response = await api.get<Application[]>('applications/');
      return response.data;
    }
  });

  const refetchTimeoutRef = React.useRef<any>(null);
  const refetchDebounced = React.useCallback(() => {
    if (refetchTimeoutRef.current) {
      clearTimeout(refetchTimeoutRef.current);
    }
    refetchTimeoutRef.current = setTimeout(() => {
      refetch();
    }, 1500);
  }, [refetch]);

  useEffect(() => {
    const token = localStorage.getItem('access_token');
    if (!token) return;

    const apiBase = (import.meta as any).env.VITE_API_URL || (typeof window !== 'undefined' ? window.location.origin + '/api/' : 'http://127.0.0.1:8000/api/');
    let sseBase = apiBase.replace('/api/', '/api/events/');
    if (typeof window !== 'undefined' && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')) {
      sseBase = 'http://127.0.0.1:8000/api/events/';
    }
    const sseUrl = `${sseBase}?token=${encodeURIComponent(token)}`;

    const eventSource = new EventSource(sseUrl);

    let errCount = 0;
    eventSource.onerror = () => {
      errCount++;
      if (errCount > 5) {
        console.warn('SSE connection retry limit reached on Dashboard. Closing EventSource.');
        eventSource.close();
      }
    };

    eventSource.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        const { type } = payload;
        
        if (
          type.startsWith('application_') ||
          type.startsWith('bug_')
        ) {
          refetchDebounced();
        }
      } catch (err) {
        console.error('Failed to parse SSE event on dashboard:', err);
      }
    };

    return () => {
      eventSource.close();
      if (refetchTimeoutRef.current) {
        clearTimeout(refetchTimeoutRef.current);
      }
    };
  }, [refetchDebounced]);

  const handleAppCreated = (newApp: Application) => {
    queryClient.invalidateQueries({ queryKey: ['applications'] });
    setShowAddForm(false);
    navigate(`/scans/${newApp.id}`); // Auto-navigate to scans detail page
  };

  const handleDeleteApp = async (id: number, url: string) => {
    if (window.confirm(`Are you sure you want to delete "${url}"? All pages, test cases, and bug logs will be permanently deleted.`)) {
      try {
        await api.delete(`applications/${id}/`);
        queryClient.invalidateQueries({ queryKey: ['applications'] });
      } catch (err) {
        console.error(err);
        setError('Failed to delete application environment.');
      }
    }
  };

  const prefetchAppDetails = (appId: number) => {
    queryClient.prefetchQuery({
      queryKey: ['application', appId],
      queryFn: async () => {
        const res = await api.get(`applications/${appId}/`);
        return res.data;
      },
    });
    queryClient.prefetchQuery({
      queryKey: ['testCases', appId],
      queryFn: async () => {
        const res = await api.get(`test-cases/?app=${appId}`);
        return Array.isArray(res.data) ? res.data : (res.data.results || []);
      },
    });
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

      {isLoading ? (
        <div className="applications-grid">
          <style>{`
            @keyframes shimmer {
              0% { background-position: -200% 0; }
              100% { background-position: 200% 0; }
            }
            .skeleton-card {
              min-height: 180px;
              background: rgba(255, 255, 255, 0.02);
              border: 1px solid rgba(255, 255, 255, 0.05);
              border-radius: 12px;
              padding: 20px;
              display: flex;
              flex-direction: column;
              gap: 16px;
            }
            .skeleton-shimmer {
              background: linear-gradient(90deg, rgba(255,255,255,0.02) 25%, rgba(255,255,255,0.06) 50%, rgba(255,255,255,0.02) 75%);
              background-size: 200% 100%;
              animation: shimmer 1.5s infinite;
              border-radius: 4px;
            }
          `}</style>
          {[1, 2, 3].map((i) => (
            <div key={i} className="skeleton-card">
              <div className="skeleton-shimmer" style={{ height: '24px', width: '70%' }} />
              <div className="skeleton-shimmer" style={{ height: '16px', width: '40%' }} />
              <div style={{ display: 'flex', gap: '8px', marginTop: 'auto' }}>
                <div className="skeleton-shimmer" style={{ height: '28px', width: '80px', borderRadius: '6px' }} />
                <div className="skeleton-shimmer" style={{ height: '28px', width: '80px', borderRadius: '6px' }} />
              </div>
            </div>
          ))}
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
              onClick={() => navigate(`/scans/${app.id}`)}
              onMouseEnter={() => prefetchAppDetails(app.id)}
              onFocus={() => prefetchAppDetails(app.id)}
              style={{ cursor: 'pointer' }}
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
