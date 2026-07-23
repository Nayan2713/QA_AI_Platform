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

  // Calculate high-level summary metrics across registered applications
  const totalApps = applications.length;
  const totalPages = applications.reduce((acc, app) => acc + (app.page_count || 0), 0);
  const totalTests = applications.reduce((acc, app) => acc + (app.test_case_count || 0), 0);
  const totalBugs = applications.reduce((acc, app) => acc + (app.bug_count || 0), 0);

  return (
    <div className="dashboard-container animate-slide-up">
      {/* Header section */}
      <header className="dashboard-header">
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <h2 style={{ fontSize: '1.75rem', fontWeight: 700, letterSpacing: '-0.5px' }}>
              ⚡ QA Testing Control Hub
            </h2>
          </div>
          <p className="subtitle-text" style={{ marginTop: '4px' }}>
            Autonomous multi-agent site discovery, AI test suite generation, and real-time defect verification
          </p>
        </div>
        <button 
          onClick={() => setShowAddForm(true)} 
          className="btn-primary btn-add-app"
          disabled={showAddForm}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            padding: '12px 20px',
            borderRadius: '10px',
            fontWeight: 600,
            boxShadow: '0 4px 14px rgba(139, 92, 246, 0.4)',
            transition: 'all 0.2s ease'
          }}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <line x1="12" y1="5" x2="12" y2="19"></line>
            <line x1="5" y1="12" x2="19" y2="12"></line>
          </svg>
          Register Application
        </button>
      </header>

      {/* Summary KPI stat cards */}
      {applications.length > 0 && (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          gap: '16px',
          marginBottom: '28px'
        }}>
          <div className="glass-card" style={{ padding: '20px', display: 'flex', alignItems: 'center', gap: '16px' }}>
            <div style={{
              width: '46px', height: '46px', borderRadius: '12px',
              background: 'rgba(139, 92, 246, 0.15)', border: '1px solid rgba(139, 92, 246, 0.3)',
              display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '1.4rem'
            }}>🌐</div>
            <div>
              <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>Active Environments</span>
              <h3 style={{ fontSize: '1.6rem', fontWeight: 700, color: '#fff' }}>{totalApps}</h3>
            </div>
          </div>

          <div className="glass-card" style={{ padding: '20px', display: 'flex', alignItems: 'center', gap: '16px' }}>
            <div style={{
              width: '46px', height: '46px', borderRadius: '12px',
              background: 'rgba(6, 182, 212, 0.15)', border: '1px solid rgba(6, 182, 212, 0.3)',
              display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '1.4rem'
            }}>📄</div>
            <div>
              <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>Pages Discovered</span>
              <h3 style={{ fontSize: '1.6rem', fontWeight: 700, color: '#fff' }}>{totalPages}</h3>
            </div>
          </div>

          <div className="glass-card" style={{ padding: '20px', display: 'flex', alignItems: 'center', gap: '16px' }}>
            <div style={{
              width: '46px', height: '46px', borderRadius: '12px',
              background: 'rgba(16, 185, 129, 0.15)', border: '1px solid rgba(16, 185, 129, 0.3)',
              display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '1.4rem'
            }}>🧪</div>
            <div>
              <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>Generated Tests</span>
              <h3 style={{ fontSize: '1.6rem', fontWeight: 700, color: '#fff' }}>{totalTests}</h3>
            </div>
          </div>

          <div className="glass-card" style={{ padding: '20px', display: 'flex', alignItems: 'center', gap: '16px' }}>
            <div style={{
              width: '46px', height: '46px', borderRadius: '12px',
              background: 'rgba(239, 68, 68, 0.15)', border: '1px solid rgba(239, 68, 68, 0.3)',
              display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '1.4rem'
            }}>🐛</div>
            <div>
              <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>Defects Identified</span>
              <h3 style={{ fontSize: '1.6rem', fontWeight: 700, color: totalBugs > 0 ? '#ef4444' : '#34d399' }}>{totalBugs}</h3>
            </div>
          </div>
        </div>
      )}

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
          {[1, 2, 3].map((i) => (
            <div key={i} className="glass-card" style={{ minHeight: '200px', display: 'flex', flexDirection: 'column', gap: '16px', padding: '24px' }}>
              <div className="skeleton-shimmer" style={{ height: '24px', width: '65%' }} />
              <div className="skeleton-shimmer" style={{ height: '14px', width: '45%' }} />
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px', margin: '16px 0' }}>
                <div className="skeleton-shimmer" style={{ height: '40px' }} />
                <div className="skeleton-shimmer" style={{ height: '40px' }} />
                <div className="skeleton-shimmer" style={{ height: '40px' }} />
                <div className="skeleton-shimmer" style={{ height: '40px' }} />
              </div>
              <div className="skeleton-shimmer" style={{ height: '32px', width: '100%', borderRadius: '8px', marginTop: 'auto' }} />
            </div>
          ))}
        </div>
      ) : applications.length === 0 ? (
        <div className="empty-state-card glass-card">
          <svg className="empty-state-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ color: '#8b5cf6' }}>
            <circle cx="12" cy="12" r="10"></circle>
            <line x1="2" y1="12" x2="22" y2="12"></line>
            <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path>
          </svg>
          <h3 className="empty-state-title">Register Your First Application</h3>
          <p className="empty-state-desc">
            Provide any web application URL. Our autonomous AI engine will crawl pages, inspect forms & API patterns, 
            synthesize full end-to-end test suites, and detect defects automatically.
          </p>
          <button onClick={() => setShowAddForm(true)} className="btn-primary btn-lg" style={{ marginTop: '8px', padding: '12px 28px' }}>
            + Register New Web App
          </button>
        </div>
      ) : (
        <div className="applications-grid">
          {applications.map((app) => {
            const isDiscovering = app.status === 'DISCOVERING';
            const isFailed = app.status === 'FAILED';
            return (
              <div 
                key={app.id} 
                className="glass-card application-card"
                onClick={() => navigate(`/scans/${app.id}`)}
                onMouseEnter={() => prefetchAppDetails(app.id)}
                onFocus={() => prefetchAppDetails(app.id)}
                style={{ 
                  cursor: 'pointer',
                  position: 'relative',
                  overflow: 'hidden',
                  ...(isDiscovering ? { animation: 'pulseGlow 2.5s infinite' } : {})
                }}
              >
                <div className="app-card-header">
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px', overflow: 'hidden' }}>
                    <h4 style={{
                      fontSize: '1.05rem',
                      fontWeight: 700,
                      whiteSpace: 'nowrap',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis'
                    }}>
                      {app.url}
                    </h4>
                  </div>
                  
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span 
                      className={`live-pulse-dot ${isDiscovering ? 'running' : isFailed ? 'failed' : ''}`}
                      title={`Status: ${app.status}`}
                    />
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDeleteApp(app.id, app.url);
                      }}
                      title="Delete Application"
                      style={{
                        background: 'rgba(239, 68, 68, 0.1)',
                        border: '1px solid rgba(239, 68, 68, 0.2)',
                        color: '#ef4444',
                        cursor: 'pointer',
                        fontSize: '0.85rem',
                        padding: '4px 8px',
                        borderRadius: '6px',
                        transition: 'all 0.2s ease'
                      }}
                    >
                      🗑️
                    </button>
                  </div>
                </div>

                <p className="app-card-url" style={{ fontFamily: 'var(--font-mono)', fontSize: '0.78rem', color: 'var(--text-muted)', marginBottom: '16px' }}>
                  {app.base_url}
                </p>
                
                {/* Metrics Breakdown Grid */}
                <div className="app-card-metrics" style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(4, 1fr)',
                  gap: '8px',
                  background: 'rgba(11, 8, 22, 0.4)',
                  padding: '12px',
                  borderRadius: '10px',
                  border: '1px solid rgba(255, 255, 255, 0.04)',
                  marginBottom: '16px'
                }}>
                  <div className="metric" style={{ textAlign: 'center' }}>
                    <span className="metric-lbl" style={{ display: 'block', fontSize: '0.7rem', color: 'var(--text-muted)' }}>Pages</span>
                    <span className="metric-val" style={{ fontSize: '1.1rem', fontWeight: 700, color: '#fff' }}>{app.page_count}</span>
                  </div>
                  <div className="metric" style={{ textAlign: 'center' }}>
                    <span className="metric-lbl" style={{ display: 'block', fontSize: '0.7rem', color: 'var(--text-muted)' }}>APIs</span>
                    <span className="metric-val" style={{ fontSize: '1.1rem', fontWeight: 700, color: '#fff' }}>{app.api_count}</span>
                  </div>
                  <div className="metric" style={{ textAlign: 'center' }}>
                    <span className="metric-lbl" style={{ display: 'block', fontSize: '0.7rem', color: 'var(--text-muted)' }}>Tests</span>
                    <span className="metric-val" style={{ fontSize: '1.1rem', fontWeight: 700, color: '#fff' }}>{app.test_case_count}</span>
                  </div>
                  <div className="metric bug-metric" style={{ textAlign: 'center' }}>
                    <span className="metric-lbl" style={{ display: 'block', fontSize: '0.7rem', color: 'var(--text-muted)' }}>Bugs</span>
                    <span className="metric-val" style={{ fontSize: '1.1rem', fontWeight: 700, color: app.bug_count > 0 ? '#ef4444' : '#34d399' }}>{app.bug_count}</span>
                  </div>
                </div>
                
                {/* Footer status & industry tags */}
                <div className="app-card-footer" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span className={`badge-status ${isDiscovering ? 'badge-status-running' : isFailed ? 'badge-status-failed' : 'badge-status-passed'}`}>
                      {app.status}
                    </span>
                    
                    {(() => {
                      const ind = app.industry ? app.industry.trim() : "";
                      if (!ind || ind === "General") {
                        return (
                          <span style={{
                            padding: '2px 8px',
                            borderRadius: '12px',
                            fontSize: '0.7rem',
                            fontWeight: 600,
                            backgroundColor: 'rgba(148, 163, 184, 0.12)',
                            color: '#94a3b8',
                            border: '1px solid rgba(148, 163, 184, 0.25)',
                          }}>
                            General
                          </span>
                        );
                      }
                      return (
                        <span style={{
                          padding: '2px 8px',
                          borderRadius: '12px',
                          fontSize: '0.7rem',
                          fontWeight: 600,
                          backgroundColor: 'rgba(139, 92, 246, 0.15)',
                          color: '#c084fc',
                          border: '1px solid rgba(139, 92, 246, 0.3)',
                        }}>
                          {ind}
                        </span>
                      );
                    })()}
                  </div>

                  <span className="btn-view-details" style={{ fontSize: '0.85rem', color: '#a5b4fc', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '4px' }}>
                    Inspect & Run →
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
