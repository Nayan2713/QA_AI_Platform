import React, { useState, useEffect, useRef } from 'react';
import { Routes, Route, Navigate, useNavigate, useLocation, useParams } from 'react-router-dom';
import api from './lib/api';
import { User, Bug } from './lib/types';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Navigation } from './components/Navigation';
import { TeamModal } from './components/TeamModal';
import UserProfileModal from './components/UserProfileModal';
import ForgotPasswordModal from './components/ForgotPasswordModal';

import { ChatbotWidget } from './components/ChatbotWidget';
import { ToastManager, ToastItem } from './components/ToastManager';
import { NotificationItem } from './components/NotificationCenter';
import { playNotificationSound, initAudioUnlock } from './lib/notificationSound';
import { LandingPage } from './landing/LandingPage';
import './App.css';

const Dashboard = React.lazy(() => import('./components/Dashboard').then(module => ({ default: module.Dashboard })));
const AppDetail = React.lazy(() => import('./components/AppDetail').then(module => ({ default: module.AppDetail })));
const BugList = React.lazy(() => import('./components/BugList').then(module => ({ default: module.BugList })));
const TestResults = React.lazy(() => import('./components/TestResults').then(module => ({ default: module.TestResults })));

// Standalone wrapper for rendering execution results route-based
const TestResultsRoute = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  return (
    <div style={{ padding: '24px', maxWidth: '1200px', margin: '0 auto' }}>
      <TestResults
        testRunId={parseInt(id || '0')}
        onClose={() => navigate(-1)}
        onBugDetected={() => { }}
      />
    </div>
  );
};

function App() {
  const queryClient = useQueryClient();
  const [token, setToken] = useState<string | null>(localStorage.getItem('access_token'));
  const [username, setUsername] = useState<string>(localStorage.getItem('username') || '');
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);
  const [isForgotPasswordOpen, setIsForgotPasswordOpen] = useState(false);


  const navigate = useNavigate();
  const location = useLocation();

  // Enforce scroll to top on page refresh and route navigation
  useEffect(() => {
    if (typeof window !== 'undefined') {
      if ('scrollRestoration' in window.history) {
        window.history.scrollRestoration = 'manual';
      }
      window.scrollTo(0, 0);
    }
  }, [location.pathname]);

  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const handleDismissToast = (id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  };

  const { data: notifications = [], refetch: refetchNotifications } = useQuery<NotificationItem[]>({
    queryKey: ['notifications'],
    queryFn: async ({ signal }) => {
      const response = await api.get<any>('notifications/', { signal });
      const rawData = response.data;
      if (Array.isArray(rawData)) return rawData;
      if (rawData && Array.isArray(rawData.results)) return rawData.results;
      if (rawData && Array.isArray(rawData.data)) return rawData.data;
      return [];
    },
    enabled: !!token,
    refetchInterval: 10000,
  });

  const seenNotifsRef = useRef<Set<number>>(new Set());
  const isInitialMountRef = useRef<boolean>(true);

  // Polling Toast & Sound Fallback: Triggers toasts & audio alerts ONLY for new notifications arriving during active session
  useEffect(() => {
    if (!notifications || notifications.length === 0) return;

    if (isInitialMountRef.current) {
      // Seed pre-existing notifications on initial page mount/refresh so F5 doesn't re-toast past notifications
      notifications.forEach((n) => seenNotifsRef.current.add(n.id));
      isInitialMountRef.current = false;
      return;
    }

    notifications.forEach((n) => {
      if (!n.is_read && !seenNotifsRef.current.has(n.id)) {
        seenNotifsRef.current.add(n.id);

        const newToast: ToastItem = {
          id: `toast-${n.id}`,
          title: n.title,
          message: n.message,
          level: n.level || 'info',
        };

        setToasts(prev => {
          if (prev.some(t => t.id === newToast.id)) return prev;
          return [newToast, ...prev.slice(0, 4)];
        });

        playNotificationSound(n.level || 'info');

        if (typeof window !== 'undefined' && 'Notification' in window && Notification.permission === 'granted') {
          try {
            new Notification(n.title, { body: n.message });
          } catch (err) {
            console.warn('Desktop notification dispatch failed:', err);
          }
        }

        setTimeout(() => {
          handleDismissToast(newToast.id);
        }, 5000);
      }
    });
  }, [notifications]);

  // Global SSE listener for real-time task completion notifications.
  // Reconnects with a fresh token whenever the stored access token changes
  // (silent refresh) or the connection drops (network blip, server restart,
  // laptop sleep) — the previous version opened the connection once and
  // never recovered from either case, so toasts/sound would silently stop
  // firing while the notification bell kept working via polling.
  useEffect(() => {
    initAudioUnlock();

    if (typeof window !== 'undefined' && 'Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission().catch(() => { });
    }

    if (!token) return;

    const apiBase = (import.meta as any).env.VITE_API_URL || (typeof window !== 'undefined' ? window.location.origin + '/api/' : 'http://127.0.0.1:8000/api/');
    const baseUrl = apiBase.endsWith('/') ? apiBase : apiBase + '/';

    let eventSource: EventSource | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let stopped = false;

    const scheduleReconnect = () => {
      if (stopped || reconnectTimer) return;
      reconnectTimer = setTimeout(() => {
        reconnectTimer = null;
        connect();
      }, 3000);
    };

    const connect = () => {
      if (stopped) return;

      const currentToken = localStorage.getItem('access_token');
      if (!currentToken) return;

      const sseUrl = `${baseUrl}events/?token=${encodeURIComponent(currentToken)}`;
      eventSource = new EventSource(sseUrl);

      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          console.log('[SSE Event Received]', data);

          if (data.type === 'auth_error') {
            console.warn('[SSE] Token rejected, reconnecting with a fresh one:', data.message);
            eventSource?.close();
            scheduleReconnect();
            return;
          }

          // Global instant cache invalidation and window event broadcast
          queryClient.invalidateQueries();
          if (typeof window !== 'undefined') {
            window.dispatchEvent(new CustomEvent('qa_platform:sse_event', { detail: data }));
          }

          if (data.type === 'notification_created' && data.data) {
            const n = data.data;
            const newToast: ToastItem = {
              id: `toast-${n.id || Date.now()}`,
              title: n.title,
              message: n.message,
              level: n.level || 'info',
            };
            setToasts(prev => [newToast, ...prev.slice(0, 4)]);
            playNotificationSound(n.level || 'info');
            refetchNotifications();

            // Native Browser Desktop OS Notification
            if (typeof window !== 'undefined' && 'Notification' in window && Notification.permission === 'granted') {
              try {
                new Notification(n.title, {
                  body: n.message,
                });
              } catch (err) {
                console.warn('Desktop notification dispatch failed:', err);
              }
            }

            setTimeout(() => {
              handleDismissToast(newToast.id);
            }, 5000);
          } else {
            refetchNotifications();
          }
        } catch (e) {
          // ignore heartbeats/parse errors
        }
      };

      eventSource.onerror = () => {
        console.warn('[SSE] Connection dropped, reconnecting...');
        eventSource?.close();
        scheduleReconnect();
      };
    };

    connect();

    // Fired by lib/api.ts right after a silent token refresh, so we swap
    // to the new token immediately instead of waiting for the old one to
    // eventually get rejected.
    const handleTokenRefreshed = () => {
      console.log('[SSE] Access token refreshed, reconnecting.');
      if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
      eventSource?.close();
      connect();
    };
    window.addEventListener('auth:token_refreshed', handleTokenRefreshed);

    return () => {
      stopped = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      eventSource?.close();
      window.removeEventListener('auth:token_refreshed', handleTokenRefreshed);
    };
  }, [token, refetchNotifications]);

  const { data: bugs = [], refetch: fetchGlobalBugs } = useQuery({
    queryKey: ['globalBugs'],
    queryFn: async ({ signal }) => {
      const response = await api.get<Bug[]>('bugs/', { signal });
      const rawData = response.data as any;
      return Array.isArray(rawData) ? rawData : (rawData.results || []);
    },
    enabled: !!token && location.pathname === '/bugs',
  });

  // Auth Form State
  const [isLogin, setIsLogin] = useState(true);
  const [authUsername, setAuthUsername] = useState('');
  const [authEmail, setAuthEmail] = useState('');
  const [authPassword, setAuthPassword] = useState('');
  const [authError, setAuthError] = useState('');
  const [authSuccess, setAuthSuccess] = useState('');
  const [authLoading, setAuthLoading] = useState(false);

  const [permissionError, setPermissionError] = useState<string | null>(null);

  // Check auth on startup & listen for auth:logout and auth:permission_denied events
  useEffect(() => {
    const storedToken = localStorage.getItem('access_token');
    const storedUser = localStorage.getItem('username');
    if (storedToken && storedUser) {
      setToken(storedToken);
      setUsername(storedUser);
    }

    const handleAuthLogout = () => {
      queryClient.clear();
      setToken(null);
      setUsername('');
    };

    const handlePermissionDenied = (e: any) => {
      const msg = e.detail?.message || 'Permission Denied: You do not have access for this action.';
      setPermissionError(msg);
      setTimeout(() => {
        setPermissionError(null);
      }, 5000);
    };

    window.addEventListener('auth:logout', handleAuthLogout);
    window.addEventListener('auth:permission_denied', handlePermissionDenied as EventListener);

    return () => {
      window.removeEventListener('auth:logout', handleAuthLogout);
      window.removeEventListener('auth:permission_denied', handlePermissionDenied as EventListener);
    };
  }, [queryClient]);

  const handleRunTestCaseFromGlobal = async (testCaseId: number) => {
    try {
      const response = await api.post('test-runs/execute/', { test_case_id: testCaseId });
      if (response.data.test_run_id) {
        if (response.data.task_id) {
          setActiveTaskId(response.data.task_id);
        }
        // Direct client-side route navigation
        navigate(`/results/${response.data.test_run_id}`);
      }
    } catch (err) {
      console.error('Failed to execute test run from global bugs list:', err);
    }
  };

  const handleLogout = () => {
    queryClient.clear();
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('username');
    setToken(null);
    setUsername('');
    setAuthEmail('');
    setAuthPassword('');
    setAuthUsername('');
    setAuthError('');
    setAuthSuccess('');
    window.location.href = '/dashboard';
  };

  const handleAuthSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isLogin) {
      if (!authEmail || !authPassword) {
        setAuthError('Please fill in all required fields.');
        return;
      }
    } else {
      if (!authUsername || !authEmail || !authPassword) {
        setAuthError('Please fill in all required fields.');
        return;
      }
    }

    setAuthError('');
    setAuthSuccess('');
    setAuthLoading(true);

    try {
      if (isLogin) {
        // Clear old cached queries from previous user session before logging in new user
        queryClient.clear();
        // Log in with email
        const response = await api.post<{ access: string; refresh: string; user: User }>('auth/login/', {
          email: authEmail,
          password: authPassword
        });
        localStorage.setItem('access_token', response.data.access);
        localStorage.setItem('refresh_token', response.data.refresh);
        localStorage.setItem('username', response.data.user.username);
        setToken(response.data.access);
        setUsername(response.data.user.username);

        // Reset login form fields
        setAuthEmail('');
        setAuthPassword('');

        // Perform clean navigation to dashboard
        window.location.href = '/dashboard';
      } else {
        // Register
        await api.post<{ access: string; refresh: string; user: User }>('auth/register/', {
          username: authUsername,
          email: authEmail,
          password: authPassword
        });

        // Success notification & switch to Login form
        setAuthSuccess('Successfully registered! Please log in.');
        setIsLogin(true);

        // Keep the email filled in for ease of login, clear username and password
        setAuthUsername('');
        setAuthPassword('');
      }
    } catch (err: any) {
      console.error(err);
      let msg = 'Authentication failed.';
      if (err.response?.data) {
        const data = err.response.data;
        if (data.detail) {
          if (typeof data.detail === 'string') {
            msg = data.detail;
          } else if (typeof data.detail === 'object') {
            const firstKey = Object.keys(data.detail)[0];
            const firstVal = data.detail[firstKey];
            msg = Array.isArray(firstVal) ? firstVal[0] : (typeof firstVal === 'string' ? firstVal : JSON.stringify(data.detail));
          }
        } else if (data.username) {
          msg = Array.isArray(data.username) ? data.username[0] : data.username;
        } else if (data.email) {
          msg = Array.isArray(data.email) ? data.email[0] : data.email;
        } else if (data.password) {
          msg = Array.isArray(data.password) ? data.password[0] : data.password;
        }
      }
      setAuthError(msg);
    } finally {
      setAuthLoading(false);
    }
  };

  const handleLandingAuthSubmit = async (
    e: React.FormEvent,
    isLoginMode: boolean,
    emailInput: string,
    passInput: string,
    userInput: string
  ) => {
    e.preventDefault();
    setAuthError('');
    setAuthSuccess('');
    setAuthLoading(true);

    try {
      if (isLoginMode) {
        queryClient.clear();
        const response = await api.post<{ access: string; refresh: string; user: User }>('auth/login/', {
          email: emailInput,
          password: passInput
        });
        localStorage.setItem('access_token', response.data.access);
        localStorage.setItem('refresh_token', response.data.refresh);
        localStorage.setItem('username', response.data.user.username);
        setToken(response.data.access);
        setUsername(response.data.user.username);
        window.location.href = '/dashboard';
      } else {
        await api.post<{ access: string; refresh: string; user: User }>('auth/register/', {
          username: userInput,
          email: emailInput,
          password: passInput
        });
        setAuthSuccess('Successfully registered! Please log in.');
      }
    } catch (err: any) {
      console.error(err);
      let msg = 'Authentication failed.';
      if (err.response?.data) {
        const data = err.response.data;
        if (data.detail) {
          if (typeof data.detail === 'string') {
            msg = data.detail;
          } else if (typeof data.detail === 'object') {
            const firstKey = Object.keys(data.detail)[0];
            const firstVal = data.detail[firstKey];
            msg = Array.isArray(firstVal) ? firstVal[0] : (typeof firstVal === 'string' ? firstVal : JSON.stringify(data.detail));
          }
        } else if (data.username) {
          msg = Array.isArray(data.username) ? data.username[0] : data.username;
        } else if (data.email) {
          msg = Array.isArray(data.email) ? data.email[0] : data.email;
        } else if (data.password) {
          msg = Array.isArray(data.password) ? data.password[0] : data.password;
        }
      }
      setAuthError(msg);
    } finally {
      setAuthLoading(false);
    }
  };

  if (!token) {
    const landingNode = (
      <>
        <LandingPage
          authError={authError}
          authSuccess={authSuccess}
          authLoading={authLoading}
          onAuthSubmit={handleLandingAuthSubmit}
          onOpenForgotPassword={() => setIsForgotPasswordOpen(true)}
        />
        <ForgotPasswordModal
          isOpen={isForgotPasswordOpen}
          onClose={() => setIsForgotPasswordOpen(false)}
        />
      </>
    );
    return (
      <Routes>
        <Route path="/" element={landingNode} />
        <Route path="/login" element={landingNode} />
        <Route path="/signup" element={landingNode} />
        <Route path="/register" element={landingNode} />
        <Route path="/forgot-password" element={landingNode} />
        <Route path="/dashboard" element={landingNode} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    );
  }


  const [isTeamModalOpen, setIsTeamModalOpen] = useState(false);
  const [isProfileModalOpen, setIsProfileModalOpen] = useState(false);

  return (
    <div className="app-layout">
      <ToastManager toasts={toasts} onDismiss={handleDismissToast} />
      <Navigation
        username={username}
        onLogout={handleLogout}
        onOpenTeamModal={() => setIsTeamModalOpen(true)}
        onOpenProfileModal={() => setIsProfileModalOpen(true)}
        notifications={notifications}
        onRefreshNotifications={refetchNotifications}
      />

      <TeamModal
        isOpen={isTeamModalOpen}
        onClose={() => setIsTeamModalOpen(false)}
        currentUser={username}
      />

      <UserProfileModal
        isOpen={isProfileModalOpen}
        onClose={() => setIsProfileModalOpen(false)}
        onProfileUpdated={(newUsername) => setUsername(newUsername)}
      />

      <main className="main-content">
        <React.Suspense fallback={
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '200px', gap: '16px' }}>
            <div className="spinner-small"></div>
            <p style={{ color: 'rgba(255,255,255,0.6)', fontSize: '0.9rem' }}>Loading view...</p>
          </div>
        }>
          <Routes>
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="/login" element={<Navigate to="/dashboard" replace />} />
            <Route path="/signup" element={<Navigate to="/dashboard" replace />} />
            <Route path="/register" element={<Navigate to="/dashboard" replace />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route
              path="/scans/:id/:tab?/:runId?"
              element={
                <AppDetail
                  activeTaskId={activeTaskId}
                  setActiveTaskId={setActiveTaskId}
                />
              }
            />
            <Route path="/results/:id" element={<TestResultsRoute />} />
            <Route
              path="/bugs"
              element={
                <BugList
                  bugs={bugs}
                  onRefreshBugs={fetchGlobalBugs}
                  onRunTestCase={handleRunTestCaseFromGlobal}
                  activeTaskId={activeTaskId}
                />
              }
            />
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </React.Suspense>
      </main>

      <footer className="app-footer">
        <p>© 2026 QA Engineer MVP. Built with Django, Playwright, Autonomous AI Engine, and React.</p>
      </footer>

      {/* Permission Denied UI Popup Notification */}
      {permissionError && (
        <div style={{
          position: 'fixed',
          bottom: '24px',
          right: '24px',
          zIndex: 99999,
          background: 'linear-gradient(135deg, rgba(239, 68, 68, 0.95) 0%, rgba(185, 28, 28, 0.95) 100%)',
          color: '#fff',
          padding: '16px 20px',
          borderRadius: '14px',
          boxShadow: '0 10px 30px rgba(239, 68, 68, 0.4)',
          border: '1px solid rgba(255, 255, 255, 0.2)',
          display: 'flex',
          alignItems: 'center',
          gap: '14px',
          maxWidth: '420px',
          backdropFilter: 'blur(8px)'
        }}>
          <span style={{ fontSize: '1.6rem' }}>🔒</span>
          <div style={{ flex: 1 }}>
            <strong style={{ display: 'block', fontSize: '0.95rem', marginBottom: '2px', color: '#fff' }}>
              Permission Restricted
            </strong>
            <span style={{ fontSize: '0.82rem', opacity: 0.95, color: '#fee2e2', lineHeight: '1.3' }}>
              {permissionError}
            </span>
          </div>
          <button
            onClick={() => setPermissionError(null)}
            style={{
              background: 'rgba(255,255,255,0.2)',
              border: 'none',
              color: '#fff',
              width: '26px',
              height: '26px',
              borderRadius: '50%',
              cursor: 'pointer',
              fontWeight: 'bold',
              fontSize: '0.85rem'
            }}
          >
            ✕
          </button>
        </div>
      )}

      {/* Floating Application-Scoped Chatbot */}
      {!!token && <ChatbotWidget />}
    </div>
  );
}

export default App;