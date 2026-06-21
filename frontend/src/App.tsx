import React, { useState, useEffect } from 'react';
import api from './lib/api';
import { User, Bug } from './lib/types';
import { Navigation } from './components/Navigation';
import { Dashboard } from './components/Dashboard';
import { AppDetail } from './components/AppDetail';
import { BugList } from './components/BugList';
import './App.css';

function App() {
  const [token, setToken] = useState<string | null>(localStorage.getItem('access_token'));
  const [username, setUsername] = useState<string>(localStorage.getItem('username') || '');
  const [currentView, setCurrentView] = useState<'dashboard' | 'bugs'>('dashboard');
  const [bugs, setBugs] = useState<Bug[]>([]);
  const [selectedAppId, setSelectedAppId] = useState<number | null>(null);
  const [activeTestRunId, setActiveTestRunId] = useState<number | null>(null);
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);
  
  // Auth Form State
  const [isLogin, setIsLogin] = useState(true);
  const [authUsername, setAuthUsername] = useState('');
  const [authEmail, setAuthEmail] = useState('');
  const [authPassword, setAuthPassword] = useState('');
  const [authError, setAuthError] = useState('');
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

  // Fetch bugs if global bugs view is selected
  useEffect(() => {
    if (token && currentView === 'bugs') {
      fetchGlobalBugs();
    }
  }, [currentView, token]);

  const fetchGlobalBugs = async () => {
    try {
      const response = await api.get<Bug[]>('bugs/');
      setBugs(response.data);
    } catch (err) {
      console.error('Failed to fetch bugs:', err);
    }
  };

  const handleRunTestCaseFromGlobal = async (testCaseId: number) => {
    try {
      const bug = bugs.find(b => b.test_case_id === testCaseId);
      const appId = bug?.app_id;
      
      const response = await api.post('test-runs/execute/', { test_case_id: testCaseId });
      if (response.data.test_run_id) {
        setActiveTestRunId(response.data.test_run_id);
        if (response.data.task_id) {
          setActiveTaskId(response.data.task_id);
        }
        if (appId) {
          setSelectedAppId(appId);
        }
        setCurrentView('dashboard');
      }
    } catch (err) {
      console.error('Failed to execute test run from global bugs list:', err);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('username');
    setToken(null);
    setUsername('');
    setCurrentView('dashboard');
  };

  const handleAuthSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!authUsername || !authPassword || (!isLogin && !authEmail)) {
      setAuthError('Please fill in all required fields.');
      return;
    }

    setAuthError('');
    setAuthLoading(true);

    try {
      if (isLogin) {
        // Log in
        const response = await api.post<{ access: string; refresh: string }>('auth/login/', {
          username: authUsername,
          password: authPassword
        });
        localStorage.setItem('access_token', response.data.access);
        localStorage.setItem('refresh_token', response.data.refresh);
        localStorage.setItem('username', authUsername);
        setToken(response.data.access);
        setUsername(authUsername);
      } else {
        // Register
        const response = await api.post<{ access: string; refresh: string; user: User }>('auth/register/', {
          username: authUsername,
          email: authEmail,
          password: authPassword
        });
        localStorage.setItem('access_token', response.data.access);
        localStorage.setItem('refresh_token', response.data.refresh);
        localStorage.setItem('username', response.data.user.username);
        setToken(response.data.access);
        setUsername(response.data.user.username);
      }
      
      // Reset forms
      setAuthUsername('');
      setAuthEmail('');
      setAuthPassword('');
    } catch (err: any) {
      console.error(err);
      setAuthError(
        err.response?.data?.detail || 
        err.response?.data?.username?.[0] || 
        err.response?.data?.password?.[0] || 
        'Authentication failed.'
      );
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

            <div className="form-group">
              <label htmlFor="auth-username">Username *</label>
              <input
                id="auth-username"
                type="text"
                value={authUsername}
                onChange={(e) => setAuthUsername(e.target.value)}
                required
                className="form-input"
                placeholder="qa_engineer"
              />
            </div>

            {!isLogin && (
              <div className="form-group">
                <label htmlFor="auth-email">Email Address *</label>
                <input
                  id="auth-email"
                  type="email"
                  value={authEmail}
                  onChange={(e) => setAuthEmail(e.target.value)}
                  required={!isLogin}
                  className="form-input"
                  placeholder="name@company.com"
                />
              </div>
            )}

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
            <button className="btn-link" onClick={() => { setIsLogin(!isLogin); setAuthError(''); }}>
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
        onNavigate={(view) => {
          setSelectedAppId(null);
          setCurrentView(view);
        }}
        currentView={currentView}
      />
      
      <main className="main-content">
        {selectedAppId !== null ? (
          <AppDetail 
            appId={selectedAppId} 
            onBack={() => setSelectedAppId(null)}
            activeTestRunId={activeTestRunId}
            setActiveTestRunId={setActiveTestRunId}
            activeTaskId={activeTaskId}
            setActiveTaskId={setActiveTaskId}
          />
        ) : currentView === 'dashboard' ? (
          <Dashboard onSelectView={setCurrentView} onSelectApp={setSelectedAppId} />
        ) : (
          <BugList 
            bugs={bugs} 
            onRefreshBugs={fetchGlobalBugs} 
            onRunTestCase={handleRunTestCaseFromGlobal}
            activeTaskId={activeTaskId}
          />
        )}
      </main>
      
      <footer className="app-footer">
        <p>© 2026 QA Engineer MVP. Built with Django, Playwright, Ollama, and React.</p>
      </footer>
    </div>
  );
}

export default App;
