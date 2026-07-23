import React, { useState, useEffect } from 'react';
import { Routes, Route, Navigate, useNavigate, useLocation, useParams } from 'react-router-dom';
import api from './lib/api';
import { User, Bug } from './lib/types';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Navigation } from './components/Navigation';
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
        onBugDetected={() => {}}
      />
    </div>
  );
};

function App() {
  const queryClient = useQueryClient();
  const [token, setToken] = useState<string | null>(localStorage.getItem('access_token'));
  const [username, setUsername] = useState<string>(localStorage.getItem('username') || '');
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);
  
  const navigate = useNavigate();
  const location = useLocation();

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

  // Check auth on startup
  useEffect(() => {
    const storedToken = localStorage.getItem('access_token');
    const storedUser = localStorage.getItem('username');
    if (storedToken && storedUser) {
      setToken(storedToken);
      setUsername(storedUser);
    }
  }, []);

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
    navigate('/dashboard');
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
        
        // Navigate to dashboard
        navigate('/dashboard');
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

  if (!token) {
    return (
      <div className="auth-container">
        <div className="glass-card auth-card">
          <div className="auth-header">
            <span className="auth-logo">⚡</span>
            <h2>{isLogin ? 'Welcome Back' : 'Create QA Space'}</h2>
            <p className="auth-subtitle">
              {isLogin ? 'Log in to manage your automated test runs' : 'Register your developer space to begin testing'}
            </p>
          </div>

          <form onSubmit={handleAuthSubmit} className="auth-form">
            {authError && <div className="error-alert">{authError}</div>}
            {authSuccess && <div className="success-alert">{authSuccess}</div>}

            {!isLogin && (
              <div className="form-group">
                <label htmlFor="auth-username">Username *</label>
                <input
                  id="auth-username"
                  type="text"
                  value={authUsername}
                  onChange={(e) => setAuthUsername(e.target.value)}
                  required={!isLogin}
                  className="form-input"
                  placeholder="qa_engineer"
                />
              </div>
            )}

            <div className="form-group">
              <label htmlFor="auth-email">Email Address *</label>
              <input
                id="auth-email"
                type="email"
                value={authEmail}
                onChange={(e) => setAuthEmail(e.target.value)}
                required
                className="form-input"
                placeholder="name@company.com"
              />
            </div>

            <div className="form-group">
              <label htmlFor="auth-password">Password *</label>
              <input
                id="auth-password"
                type="password"
                value={authPassword}
                onChange={(e) => setAuthPassword(e.target.value)}
                required
                className="form-input"
                placeholder="••••••••••••"
              />
            </div>

            <button type="submit" className="btn-primary btn-block" disabled={authLoading}>
              {authLoading ? 'Authenticating...' : isLogin ? 'Log In' : 'Sign Up'}
            </button>
          </form>

          <div className="auth-footer">
            <button className="btn-link" onClick={() => { setIsLogin(!isLogin); setAuthError(''); setAuthSuccess(''); }}>
              {isLogin ? "Don't have an account? Sign Up" : 'Already have an account? Log In'}
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="app-layout">
      <Navigation 
        username={username} 
        onLogout={handleLogout} 
      />
      
      <main className="main-content">
        <React.Suspense fallback={
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '200px', gap: '16px' }}>
            <div className="spinner-small"></div>
            <p style={{ color: 'rgba(255,255,255,0.6)', fontSize: '0.9rem' }}>Loading view...</p>
          </div>
        }>
          <Routes>
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
        <p>© 2026 QA Engineer MVP. Built with Django, Playwright, Ollama, and React.</p>
      </footer>
    </div>
  );
}

export default App;
