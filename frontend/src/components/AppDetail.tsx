import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import api from '../lib/api';
import { Application, TestCase, Bug, CeleryTask, APIEndpoint, AgentSession } from '../lib/types';
import { DiscoveryStatus } from './DiscoveryStatus';
import { TestCaseList } from './TestCaseList';
import { TestResults } from './TestResults';
import { BugList } from './BugList';
import QualityDashboard from './QualityDashboard/QualityDashboard';

interface AppDetailProps {
  appId?: number;
  onBack?: () => void;
  activeTestRunId?: number | null;
  setActiveTestRunId?: (id: number | null) => void;
  activeTaskId?: string | null;
  setActiveTaskId?: (id: string | null) => void;
}

interface ToastMessage {
  id: string;
  type: 'success' | 'error' | 'info';
  title: string;
  message: string;
}

export const AppDetail: React.FC<AppDetailProps> = ({ 
  appId: propAppId, 
  onBack,
  activeTestRunId: propActiveTestRunId,
  setActiveTestRunId: propSetActiveTestRunId,
  activeTaskId: propActiveTaskId,
  setActiveTaskId: propSetActiveTaskId
}) => {
  const { id, tab, runId } = useParams<{ id: string; tab?: string; runId?: string }>();
  const appId = propAppId || parseInt(id || '0');
  const navigate = useNavigate();

  // Vanilla state management
  const [app, setApp] = useState<Application | null>(null);
  const [isAppLoading, setIsAppLoading] = useState(true);
  const [appError, setAppError] = useState('');

  const [testCases, setTestCases] = useState<TestCase[]>([]);
  const [isTestCasesLoading, setIsTestCasesLoading] = useState(true);
  const [testCasesError, setTestCasesError] = useState<any>(null);
  const [testCasesPage, setTestCasesPage] = useState<number>(1);
  const [testCasesPageSize, setTestCasesPageSize] = useState<number>(100);
  const [totalTestCasesCount, setTotalTestCasesCount] = useState<number>(0);

  const [bugs, setBugs] = useState<Bug[]>([]);
  const [isBugsLoading, setIsBugsLoading] = useState(true);

  const [apiEndpoints, setApiEndpoints] = useState<APIEndpoint[]>([]);
  const [isApiEndpointsLoading, setIsApiEndpointsLoading] = useState(true);

  const [agentSessions, setAgentSessions] = useState<AgentSession[]>([]);
  const [isAgentSessionsLoading, setIsAgentSessionsLoading] = useState(true);

  const [apiGraph, setApiGraph] = useState<{ nodes: any[]; links: any[] } | null>(null);
  const [isApiGraphLoading, setIsApiGraphLoading] = useState(true);

  const [selectedApiAnalysis, setSelectedApiAnalysis] = useState<any | null>(null);
  const [loadingApiAnalysisId, setLoadingApiAnalysisId] = useState<number | null>(null);
  const [discovering, setDiscovering] = useState(false);
  const activeTab = (tab as any) || 'discovery';
  const setActiveTab = (tabName: string) => {
    navigate(`/scans/${appId}/${tabName}`);
  };
  const [showLoginError, setShowLoginError] = useState(false);
  const [apiSearchQuery, setApiSearchQuery] = useState('');
  
  // Real-time toast notification system
  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  const addToast = (type: 'success' | 'error' | 'info', title: string, message: string) => {
    const toastId = Math.random().toString(36).substring(2, 9);
    setToasts(prev => [...prev.slice(-3), { id: toastId, type, title, message }]);
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== toastId));
    }, 4500);
  };
  
  // Track active execution via Route parameter
  const activeTestRunId = propActiveTestRunId !== undefined ? propActiveTestRunId : (runId ? parseInt(runId) : null);
  const setActiveTestRunId = (rId: number | null) => {
    if (propSetActiveTestRunId) {
      propSetActiveTestRunId(rId);
    } else {
      if (rId) {
        navigate(`/scans/${appId}/${activeTab}/${rId}`);
      } else {
        navigate(`/scans/${appId}/${activeTab}`);
      }
    }
  };

  // Task progress tracking
  const [localActiveTaskId, setLocalActiveTaskId] = useState<string | null>(null);
  const activeTaskId = propActiveTaskId !== undefined ? propActiveTaskId : localActiveTaskId;
  const setActiveTaskId = propSetActiveTaskId || setLocalActiveTaskId;
  const [currentTask, setCurrentTask] = useState<CeleryTask | null>(null);

  // Manual refresh trigger increment to trigger re-fetches
  const [refreshTrigger, setRefreshTrigger] = useState(0);
  const refetchAll = React.useCallback(() => {
    setRefreshTrigger(prev => prev + 1);
  }, []);

  const refetchTimeoutRef = React.useRef<any>(null);
  const refetchAllDebounced = React.useCallback(() => {
    if (refetchTimeoutRef.current) {
      clearTimeout(refetchTimeoutRef.current);
    }
    refetchTimeoutRef.current = setTimeout(() => {
      refetchAll();
    }, 3000); // 3s debounce absorbs bursts of SSE events during Run All Tests
  }, [refetchAll]);

  // 1. Fetch App details
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const signal = controller.signal;
    if (!app) setIsAppLoading(true);
    setAppError('');

    const fetchApp = async () => {
      try {
        const res = await api.get<Application>(`applications/${appId}/`, { signal });
        if (active) {
          setApp(res.data);
        }
      } catch (err: any) {
        if (active && err.name !== 'CanceledError' && err.name !== 'AbortError') {
          console.error('Failed to fetch app details:', err);
          setAppError('Failed to fetch application details.');
        }
      } finally {
        if (active) {
          setIsAppLoading(false);
        }
      }
    };

    fetchApp();
    return () => {
      active = false;
      controller.abort();
    };
  }, [appId, refreshTrigger]);

  // Sync discovering status
  useEffect(() => {
    if (app) {
      setDiscovering(app.status === 'DISCOVERING');
    }
  }, [app]);

  // 2. Fetch Test Cases
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const signal = controller.signal;
    if (testCases.length === 0) setIsTestCasesLoading(true);
    setTestCasesError(null);

    const fetchTestCases = async (retryCount = 0) => {
      try {
        const res = await api.get(`test-cases/?app=${appId}&page=${testCasesPage}&page_size=${testCasesPageSize}`, { signal, timeout: 15000 });
        const rawData = res.data;
        const data = Array.isArray(rawData) ? rawData : (rawData?.results || []);
        const totalCount = (rawData && typeof rawData === 'object' && rawData.count !== undefined) ? rawData.count : data.length;
        if (active) {
          setTestCases(data);
          setTotalTestCasesCount(totalCount);
          setTestCasesError(null);
        }
      } catch (err: any) {
        if (active && err.name !== 'CanceledError' && err.name !== 'AbortError') {
          if (retryCount < 1) {
            console.warn('Retrying test cases fetch after lag...');
            setTimeout(() => {
              if (active) fetchTestCases(retryCount + 1);
            }, 1000);
            return;
          }
          console.error('Failed to fetch test cases:', err);
          setTestCasesError(err);
        }
      } finally {
        if (active) {
          setIsTestCasesLoading(false);
        }
      }
    };

    fetchTestCases();
    return () => {
      active = false;
      controller.abort();
    };
  }, [appId, refreshTrigger, testCasesPage, testCasesPageSize]);

  // 3. Fetch Bugs
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const signal = controller.signal;
    if (bugs.length === 0) setIsBugsLoading(true);

    const fetchBugs = async () => {
      try {
        const res = await api.get(`bugs/?app=${appId}`, { signal });
        const rawData = res.data;
        const data = Array.isArray(rawData) ? rawData : (rawData.results || []);
        if (active) {
          setBugs(data);
        }
      } catch (err: any) {
        if (active && err.name !== 'CanceledError' && err.name !== 'AbortError') {
          console.error('Failed to fetch bugs:', err);
        }
      } finally {
        if (active) {
          setIsBugsLoading(false);
        }
      }
    };

    fetchBugs();
    return () => {
      active = false;
      controller.abort();
    };
  }, [appId, refreshTrigger]);

  // 4. Fetch API Endpoints & Graph
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const signal = controller.signal;
    if (apiEndpoints.length === 0) setIsApiEndpointsLoading(true);

    const fetchApiData = async () => {
      try {
        const epRes = await api.get(`api-endpoints/?app=${appId}`, { signal });
        const rawData = epRes.data;
        const data = Array.isArray(rawData) ? rawData : (rawData.results || []);
        if (active) setApiEndpoints(data);
      } catch (err: any) {
        if (active && err.name !== 'CanceledError' && err.name !== 'AbortError') {
          console.error('Failed to fetch API endpoints:', err);
        }
      } finally {
        if (active) setIsApiEndpointsLoading(false);
      }

      try {
        const graphRes = await api.get(`applications/${appId}/api-dependency-graph/`, { signal });
        if (active) setApiGraph(graphRes.data);
      } catch (err: any) {
        if (active && err.name !== 'CanceledError' && err.name !== 'AbortError') {
          console.error('Failed to fetch API graph:', err);
        }
      } finally {
        if (active) setIsApiGraphLoading(false);
      }
    };

    fetchApiData();
    return () => {
      active = false;
      controller.abort();
    };
  }, [appId, refreshTrigger]);

  // 5. Fetch Agent Sessions
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const signal = controller.signal;
    if (agentSessions.length === 0) setIsAgentSessionsLoading(true);

    const fetchSessions = async () => {
      try {
        const res = await api.get(`agent-sessions/?app=${appId}`, { signal });
        const rawData = res.data;
        const data = Array.isArray(rawData) ? rawData : (rawData.results || []);
        if (active) setAgentSessions(data as any);
      } catch (err: any) {
        if (active && err.name !== 'CanceledError' && err.name !== 'AbortError') {
          console.error('Failed to fetch agent sessions:', err);
        }
      } finally {
        if (active) setIsAgentSessionsLoading(false);
      }
    };

    fetchSessions();
    return () => {
      active = false;
      controller.abort();
    };
  }, [appId, refreshTrigger]);

  // Real-time SSE Event listener with Toast Feedback
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
        console.warn('SSE connection retry limit reached on AppDetail. Closing EventSource.');
        eventSource.close();
      }
    };

    eventSource.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        const { type, data } = payload;

        if (data && data.app_id && data.app_id !== appId) {
          return;
        }

        switch (type) {
          case 'bug_created':
            addToast('error', '🐞 Defect Identified', data.title || 'A new bug was captured during test execution.');
            refetchAllDebounced();
            break;
          case 'application_updated':
            if (data.status === 'DISCOVERED' || data.status === 'FAILED') {
              setDiscovering(false);
              addToast(data.status === 'DISCOVERED' ? 'success' : 'error', 'Discovery Complete', `App status is now ${data.status}`);
              refetchAllDebounced();
            }
            break;
          case 'page_created':
          case 'apiendpoint_created':
          case 'bug_updated':
          case 'testrun_updated':
            refetchAllDebounced();
            break;
          default:
            break;
        }
      } catch (err) {
        console.error('Failed to parse SSE event message:', err);
      }
    };

    return () => {
      eventSource.close();
    };
  }, [appId, refetchAllDebounced]);

  // Auto-restore active task on page load / refresh
  useEffect(() => {
    let isMounted = true;

    const autoRestoreActiveTask = async () => {
      try {
        const res = await api.get(`tasks/?app=${appId}&page_size=10`);
        const rawData = res.data;
        const taskList: CeleryTask[] = Array.isArray(rawData) ? rawData : (rawData.results || []);

        const candidate = taskList.find(
          t => t.status === 'pending' || t.status === 'progress' || t.status === 'running'
        );

        if (candidate && isMounted) {
          try {
            const statusRes = await api.get(`tasks/${candidate.task_id}/celery-status/`);
            const cStatus = statusRes.data.status;
            if (cStatus === 'SUCCESS' || cStatus === 'FAILURE' || cStatus === 'REVOKED') {
              if (isMounted) {
                setActiveTaskId(null);
                setCurrentTask(null);
              }
              return;
            }
          } catch {
            // Ignore status check errors
          }

          if (isMounted) {
            setActiveTaskId(candidate.task_id);
            setCurrentTask(candidate);
          }
        } else if (isMounted) {
          setActiveTaskId(null);
          setCurrentTask(null);
        }
      } catch (err) {
        console.warn('Failed to auto-restore active task on page refresh:', err);
      }
    };

    autoRestoreActiveTask();

    return () => {
      isMounted = false;
    };
  }, [appId, app?.status]);

  // Backup polling for Celery tasks using real-time celery-status endpoint
  useEffect(() => {
    if (!activeTaskId) return;
    
    let isMounted = true;
    let pollCount = 0;
    const MAX_POLLS = 150;
    
    const pollInterval = setInterval(async () => {
      if (!isMounted || pollCount >= MAX_POLLS) {
        clearInterval(pollInterval);
        return;
      }
      pollCount++;
      
      try {
        const res = await api.get(`tasks/${activeTaskId}/celery-status/`);
        if (!isMounted) return;
        
        const celeryStatus = res.data.status;
        
        if (celeryStatus === 'SUCCESS' || celeryStatus === 'FAILURE') {
          refetchAllDebounced();
          clearInterval(pollInterval);
          setTimeout(() => {
            if (isMounted) {
              setActiveTaskId(null);
              setCurrentTask(null);
            }
          }, 3000);
        } else {
          try {
            const taskDb = await api.get<CeleryTask>(`tasks/${activeTaskId}/`);
            if (isMounted) {
              if (taskDb.data.app && taskDb.data.app !== appId) {
                setActiveTaskId(null);
                setCurrentTask(null);
                clearInterval(pollInterval);
                return;
              }
              setCurrentTask(taskDb.data);
            }
          } catch (dbErr) {
            console.warn("Failed to fetch detailed task DB record:", dbErr);
          }
        }
      } catch (err) {
        console.error("Backup task status polling error:", err);
      }
    }, 2000);

    return () => {
      isMounted = false;
      clearInterval(pollInterval);
    };
  }, [activeTaskId, appId, refetchAllDebounced]);

  const handleStopTask = async () => {
    try {
      if (activeTaskId) {
        try {
          await api.post(`tasks/${activeTaskId}/stop/`);
        } catch {}
      }
      await api.post(`applications/${appId}/stop-all/`);
      setActiveTaskId(null);
      setCurrentTask(null);
      addToast('info', 'Task Terminated', 'All running and queued task workflows were stopped.');
      await refetchAll();
    } catch (err) {
      console.error('Failed to stop all tasks:', err);
      setActiveTaskId(null);
      setCurrentTask(null);
    }
  };

  const handleStartDiscovery = async () => {
    if (!app) return;
    const oldStatus = app.status;
    
    setDiscovering(true);
    setApp(prev => prev ? { ...prev, status: 'DISCOVERING' } : null);
    
    try {
      const res = await api.post(`applications/${appId}/discover/`);
      if (res.data.task_id) {
        setActiveTaskId(res.data.task_id);
      }
      addToast('info', 'Discovery Started', 'Autonomous crawler is traversing target domain.');
    } catch (err) {
      console.error(err);
      setDiscovering(false);
      setApp(prev => prev ? { ...prev, status: oldStatus } : null);
    }
  };

  const handleDiscoveryComplete = () => {
    setDiscovering(false);
    refetchAll();
    setActiveTab('tests');
  };

  const handleDeleteAppDetail = async () => {
    if (!app) return;
    if (window.confirm(`Are you sure you want to delete "${app.url}"? All tests, runs, and bugs will be permanently deleted.`)) {
      try {
        await api.delete(`applications/${appId}/`);
        if (onBack) {
          onBack();
        } else {
          navigate('/dashboard');
        }
      } catch (err) {
        console.error('Failed to delete application environment:', err);
      }
    }
  };

  const handleRunTestCase = async (testCaseId: number) => {
    try {
      const response = await api.post('test-runs/execute/', { test_case_id: testCaseId });
      if (response.data.test_run_id) {
        if (response.data.task_id) {
          setActiveTaskId(response.data.task_id);
        }
        navigate(`/results/${response.data.test_run_id}`);
      }
    } catch (err) {
      console.error('Failed to execute test run:', err);
    }
  };

  const handleDownloadReport = async () => {
    if (!app) return;
    try {
      const pagesRes = await api.get<any[]>(`applications/${appId}/pages/`);
      const pages = pagesRes.data;
      
      let reportContent = `# 📊 QA Test Execution & Defect Report\n`;
      reportContent += `**Target System**: ${app.url}\n`;
      reportContent += `**Base Domain**: ${app.base_url}\n`;
      reportContent += `**Report Generated**: ${new Date().toLocaleString()}\n`;
      reportContent += `**Application Status**: ${app.status}\n`;
      reportContent += `**Discovery Method**: ${app.discovery_source || 'Browser Exploration'}\n`;
      reportContent += `**Total Pages Discovered**: ${pages.length}\n`;
      reportContent += `**Total Test Cases**: ${testCases.length}\n`;
      reportContent += `**Total Bugs Detected**: ${bugs.length}\n\n`;
      
      reportContent += `---\n\n`;
      reportContent += `## 📄 1. Test Scope (Discovered Pages)\n`;
      if (pages.length === 0) {
        reportContent += `No pages discovered yet.\n\n`;
      } else {
        reportContent += `The system successfully crawled the target domain and discovered **${pages.length} pages**:\n\n`;
        reportContent += `| # | Page URL | Title | Interactive Elements |\n`;
        reportContent += `|---|---|---|---|\n`;
        pages.forEach((page, idx) => {
          const formCount = page.forms ? page.forms.length : 0;
          const buttonCount = page.buttons ? page.buttons.length : 0;
          reportContent += `| ${idx + 1} | \`${page.url}\` | ${page.title || 'No Title'} | 📝 ${formCount} Forms, 🖱️ ${buttonCount} Buttons |\n`;
        });
        reportContent += `\n`;
      }
      
      reportContent += `---\n\n`;
      reportContent += `## 📋 2. Automated Test Suite\n`;
      if (testCases.length === 0) {
        reportContent += `No test cases generated yet.\n\n`;
      } else {
        reportContent += `The system generated **${testCases.length} automated test scenarios**:\n\n`;
        testCases.forEach((tc, idx) => {
          reportContent += `### Test Case ${idx + 1}: ${tc.title}\n`;
          reportContent += `* **Source**: ${tc.ai_generated ? '🤖 AI Generated' : '📋 Fallback Template'}\n`;
          reportContent += `* **Expected Result**: ${tc.expected_result}\n`;
          reportContent += `* **Automation Steps**:\n`;
          tc.steps.forEach((step: any, stepIdx: number) => {
            const actionStr = step.action.toUpperCase();
            let details = '';
            if (step.action === 'navigate') details = `to \`${step.target}\``;
            else if (step.action === 'fill') details = `selector \`${step.selector}\` with value \`"${step.value}"\``;
            else if (step.action === 'click') details = `selector \`${step.selector}\``;
            else if (step.action === 'wait') details = `for \`${step.value}ms\``;
            else if (step.action === 'assert') details = `that element \`${step.selector || 'body'}\` contains text \`"${step.value}"\``;
            
            reportContent += `    ${stepIdx + 1}. **${actionStr}** ${details}\n`;
          });
          reportContent += `\n`;
        });
      }
      
      reportContent += `---\n\n`;
      reportContent += `## 🐞 3. Defect Registry (Logged Bugs)\n`;
      if (bugs.length === 0) {
        reportContent += `✨ **Zero bugs detected!** The application passed all automation checks.\n\n`;
      } else {
        reportContent += `The system detected **${bugs.length} defects** during execution:\n\n`;
        bugs.forEach((bug, idx) => {
          const severityEmoji = bug.severity === 'critical' ? '🚨' : bug.severity === 'high' ? '⚠️' : '🔵';
          reportContent += `### ${severityEmoji} Bug ${idx + 1}: ${bug.title}\n`;
          reportContent += `* **Severity**: **${bug.severity.toUpperCase()}**\n`;
          reportContent += `* **Logged Date**: ${new Date(bug.created_at).toLocaleString()}\n`;
          reportContent += `* **Technical Details & Trace**:\n`;
          reportContent += `\`\`\`text\n${bug.description}\n\`\`\`\n\n`;
        });
      }
      
      reportContent += `---\n\n`;
      reportContent += `*Generated automatically by QA Engineer MVP Platform.*\n`;
      
      const blob = new Blob([reportContent], { type: 'text/markdown;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      
      const safeName = app.url.replace(/https?:\/\//, '').replace(/[^a-zA-Z0-9]/g, '_');
      link.setAttribute('download', `QA_Report_${safeName}.md`);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      
    } catch (err) {
      console.error('Failed to generate report:', err);
      alert('Failed to generate report.');
    }
  };

  // Filtered APIs for search
  const filteredApiEndpoints = apiEndpoints.filter(ep => {
    if (!apiSearchQuery.trim()) return true;
    const q = apiSearchQuery.toLowerCase();
    return ep.method.toLowerCase().includes(q) || ep.url_pattern.toLowerCase().includes(q) || (ep.auth_type && ep.auth_type.toLowerCase().includes(q));
  });

  if (appError) {
    return (
      <div className="glass-card loading-state" style={{ padding: '40px', textAlign: 'center', border: '1px solid rgba(239, 68, 68, 0.3)' }}>
        <span style={{ fontSize: '2rem' }}>⚠️</span>
        <h3 style={{ color: '#ef4444', margin: '12px 0' }}>Error Loading Application</h3>
        <p style={{ color: 'rgba(255, 255, 255, 0.6)', marginBottom: '20px' }}>{appError}</p>
        <button onClick={() => refetchAll()} className="btn-secondary" style={{ padding: '8px 20px' }}>
          🔄 Retry Connection
        </button>
      </div>
    );
  }

  if (!app) {
    return (
      <div className="glass-card loading-state" style={{ padding: '40px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
        <div className="skeleton-shimmer" style={{ width: '40%', height: '32px', marginBottom: '10px' }} />
        <div className="skeleton-shimmer" style={{ width: '80%', height: '16px' }} />
        <div className="skeleton-shimmer" style={{ width: '60%', height: '16px' }} />
        <div style={{ display: 'flex', gap: '12px', marginTop: '20px' }}>
          <div className="skeleton-shimmer" style={{ width: '120px', height: '40px', borderRadius: '8px' }} />
          <div className="skeleton-shimmer" style={{ width: '120px', height: '40px', borderRadius: '8px' }} />
          <div className="skeleton-shimmer" style={{ width: '120px', height: '40px', borderRadius: '8px' }} />
        </div>
      </div>
    );
  }

  const isDiscovering = app.status === 'DISCOVERING';

  return (
    <div className="app-detail-container animate-slide-up">
      {/* Toast Notification Container */}
      <div className="toast-container">
        {toasts.map(toast => (
          <div key={toast.id} className={`toast-item toast-${toast.type}`}>
            <span style={{ fontSize: '1.2rem' }}>
              {toast.type === 'error' ? '🚨' : toast.type === 'success' ? '✅' : 'ℹ️'}
            </span>
            <div>
              <strong style={{ display: 'block', fontWeight: 600 }}>{toast.title}</strong>
              <span style={{ fontSize: '0.8rem', opacity: 0.85 }}>{toast.message}</span>
            </div>
          </div>
        ))}
      </div>

      <button onClick={onBack || (() => navigate('/dashboard'))} className="btn-back-link" style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '6px',
        fontSize: '0.9rem',
        fontWeight: 600,
        marginBottom: '16px',
        color: '#a5b4fc',
        background: 'none',
        border: 'none',
        cursor: 'pointer'
      }}>
        ← Back to Dashboard
      </button>

      {/* Main App Overview Card */}
      <div className="glass-card app-detail-header-card" style={{ padding: '24px', marginBottom: '24px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '16px', width: '100%' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <span className={`live-pulse-dot ${isDiscovering ? 'running' : ''}`} />
              <h2 style={{ fontSize: '1.65rem', fontWeight: 700, margin: 0, color: '#fff' }}>🌐 {app.url}</h2>
            </div>
            <p className="base-url-text" style={{ fontFamily: 'var(--font-mono)', fontSize: '0.85rem', color: 'var(--text-muted)', marginTop: '4px' }}>
              Base Domain: <code>{app.base_url}</code>
            </p>
          </div>

          <div className="header-actions" style={{ display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap' }}>
            <button 
              onClick={handleStartDiscovery} 
              disabled={discovering} 
              className={`btn-primary btn-discover ${discovering ? 'discovering' : ''}`}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                padding: '10px 18px',
                borderRadius: '8px',
                fontWeight: 600
              }}
            >
              {discovering ? (
                <>
                  <div className="spinner-small"></div>
                  <span>Crawling Site...</span>
                </>
              ) : (
                '🔍 Start Discovery Run'
              )}
            </button>

            <button 
              onClick={handleDownloadReport}
              className="btn-secondary"
              style={{
                backgroundColor: 'rgba(255, 255, 255, 0.06)',
                border: '1px solid rgba(255, 255, 255, 0.12)',
                color: '#ffffff',
                padding: '10px 16px',
                borderRadius: '8px',
                cursor: 'pointer',
                fontWeight: 600,
                display: 'flex',
                alignItems: 'center',
                gap: '6px'
              }}
            >
              📄 Export QA Report
            </button>
            
            <button 
              onClick={handleDeleteAppDetail}
              className="btn-danger"
              style={{
                backgroundColor: 'rgba(239, 68, 68, 0.15)',
                border: '1px solid rgba(239, 68, 68, 0.3)',
                color: '#ef4444',
                padding: '10px 16px',
                borderRadius: '8px',
                cursor: 'pointer',
                fontWeight: 600,
                display: 'flex',
                alignItems: 'center',
                gap: '6px'
              }}
            >
              🗑️ Delete
            </button>
          </div>
        </div>

        {/* High-Level Overview Metrics Grid (5 cards across full width) */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))',
          gap: '12px',
          width: '100%',
          marginTop: '8px',
          paddingTop: '16px',
          borderTop: '1px solid rgba(255, 255, 255, 0.08)'
        }}>
          <div style={{ background: 'rgba(11, 8, 22, 0.45)', padding: '14px 16px', borderRadius: '10px', border: '1px solid rgba(255,255,255,0.06)' }}>
            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600, letterSpacing: '0.5px' }}>Pages Discovered</span>
            <div style={{ fontSize: '1.35rem', fontWeight: 700, color: '#fff', marginTop: '4px' }}>📄 {app.page_count}</div>
          </div>

          <div style={{ background: 'rgba(11, 8, 22, 0.45)', padding: '14px 16px', borderRadius: '10px', border: '1px solid rgba(255,255,255,0.06)' }}>
            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600, letterSpacing: '0.5px' }}>APIs Intercepted</span>
            <div style={{ fontSize: '1.35rem', fontWeight: 700, color: '#fff', marginTop: '4px' }}>🔌 {app.api_count}</div>
          </div>

          <div style={{ background: 'rgba(11, 8, 22, 0.45)', padding: '14px 16px', borderRadius: '10px', border: '1px solid rgba(255,255,255,0.06)' }}>
            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600, letterSpacing: '0.5px' }}>Test Scenarios</span>
            <div style={{ fontSize: '1.35rem', fontWeight: 700, color: '#fff', marginTop: '4px' }}>📋 {app.test_case_count}</div>
          </div>

          <div style={{ background: 'rgba(11, 8, 22, 0.45)', padding: '14px 16px', borderRadius: '10px', border: '1px solid rgba(255,255,255,0.06)' }}>
            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600, letterSpacing: '0.5px' }}>Bugs Found</span>
            <div style={{ fontSize: '1.35rem', fontWeight: 700, color: app.bug_count > 0 ? '#ef4444' : '#34d399', marginTop: '4px' }}>
              🐞 {app.bug_count}
            </div>
          </div>

          <div style={{ background: 'rgba(11, 8, 22, 0.45)', padding: '14px 16px', borderRadius: '10px', border: '1px solid rgba(255,255,255,0.06)' }}>
            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600, letterSpacing: '0.5px' }}>Auth Status</span>
            <div style={{ fontSize: '0.92rem', fontWeight: 600, marginTop: '6px', color: app.login_status === 'SUCCESS' ? '#34d399' : app.login_status === 'FAILED' ? '#ef4444' : '#fbbf24' }}>
              {app.login_status === 'SUCCESS' ? '🔑 Authenticated' : app.login_status === 'FAILED' ? '⚠️ Auth Failed' : '🔑 Auth Pending'}
            </div>
          </div>
        </div>
      </div>

      {/* Login Diagnostic Drawer */}
      {showLoginError && app.login_status === 'FAILED' && (
        <div className="glass-card diagnostic-card-container animate-slide-up" style={{
          marginBottom: '20px',
          padding: '20px',
          border: '1px solid rgba(239, 68, 68, 0.35)',
          background: 'linear-gradient(135deg, rgba(239, 68, 68, 0.12) 0%, rgba(20, 10, 10, 0.75) 100%)',
          borderRadius: '12px'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
            <h4 style={{ margin: 0, color: '#ff6b6b', fontWeight: 600 }}>🚨 Authentication Failure Details</h4>
            <button onClick={() => setShowLoginError(false)} style={{ background: 'none', border: 'none', color: '#9ca3af', cursor: 'pointer' }}>✕</button>
          </div>
          <div style={{
            background: 'rgba(0, 0, 0, 0.4)',
            padding: '12px',
            borderRadius: '8px',
            fontFamily: 'var(--font-mono)',
            fontSize: '0.82rem',
            color: '#fca5a5',
            whiteSpace: 'pre-wrap'
          }}>
            {app.login_error || 'No detailed trace available.'}
          </div>
        </div>
      )}

      {/* Real-time Task Execution Progress Tracker */}
      {currentTask && (currentTask.status === 'pending' || currentTask.status === 'progress' || currentTask.status === 'running') && (!currentTask.app || currentTask.app === appId) && (() => {
        const taskStatus = currentTask.status as string;
        return (
          <div className="glass-card task-progress-tracker animate-slide-up" style={{
            marginBottom: '24px',
            padding: '18px 20px',
            border: `1px solid ${
              taskStatus === 'success' ? 'rgba(16, 185, 129, 0.4)' :
              taskStatus === 'failed' ? 'rgba(239, 68, 68, 0.4)' :
              'rgba(245, 158, 11, 0.4)'
            }`,
            background: 'rgba(18, 14, 33, 0.85)',
            borderRadius: '12px'
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span className={`live-pulse-dot ${taskStatus === 'progress' || taskStatus === 'pending' || taskStatus === 'running' ? 'running' : ''}`} />
                <strong style={{ fontSize: '0.9rem', textTransform: 'uppercase', letterSpacing: '0.5px', color: '#fff' }}>
                  {currentTask.task_type.replace('_', ' ')} Workflow
                </strong>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <span style={{ fontSize: '0.95rem', fontWeight: 700, color: '#fff' }}>{currentTask.progress}%</span>
                {(taskStatus === 'pending' || taskStatus === 'progress' || taskStatus === 'running') && (
                  <button
                    onClick={handleStopTask}
                    style={{
                      backgroundColor: 'rgba(239, 68, 68, 0.2)',
                      border: '1px solid rgba(239, 68, 68, 0.4)',
                      color: '#ff8888',
                      padding: '3px 10px',
                      borderRadius: '6px',
                      fontSize: '0.78rem',
                      cursor: 'pointer',
                      fontWeight: 600
                    }}
                  >
                    🛑 Cancel Task
                  </button>
                )}
              </div>
            </div>

            <div style={{ width: '100%', height: '8px', backgroundColor: 'rgba(255, 255, 255, 0.08)', borderRadius: '4px', overflow: 'hidden', marginBottom: '10px' }}>
              <div style={{
                width: `${currentTask.progress}%`,
                height: '100%',
                backgroundColor: taskStatus === 'success' ? '#10b981' : taskStatus === 'failed' ? '#ef4444' : '#f59e0b',
                transition: 'width 0.4s ease',
                borderRadius: '4px'
              }} />
            </div>

            <div style={{ fontSize: '0.85rem', color: 'rgba(255, 255, 255, 0.8)' }}>
              {taskStatus === 'success' ? (
                `Task finished cleanly. ${currentTask.result?.status_text || ''}`
              ) : (
                currentTask.result?.status_text || currentTask.error || 'Executing Playwright automation steps...'
              )}
            </div>
          </div>
        );
      })()}

      {/* Main Tabs Navigation Bar */}
      <div className="tabs-container">
        <div className="tabs-header" style={{ display: 'flex', gap: '4px', borderBottom: '1px solid rgba(255, 255, 255, 0.08)', marginBottom: '24px', overflowX: 'auto' }}>
          <button 
            className={`tab-btn ${activeTab === 'discovery' ? 'active' : ''}`}
            onClick={() => setActiveTab('discovery')}
            style={{ padding: '12px 18px', fontWeight: 600, fontSize: '0.9rem', cursor: 'pointer' }}
          >
            🔍 Discovery Details
          </button>
          <button 
            className={`tab-btn ${activeTab === 'apis' ? 'active' : ''}`}
            onClick={() => setActiveTab('apis')}
            style={{ padding: '12px 18px', fontWeight: 600, fontSize: '0.9rem', cursor: 'pointer' }}
          >
            🔌 APIs & Graph ({apiEndpoints.length})
          </button>
          <button 
            className={`tab-btn ${activeTab === 'tests' ? 'active' : ''}`}
            onClick={() => setActiveTab('tests')}
            style={{ padding: '12px 18px', fontWeight: 600, fontSize: '0.9rem', cursor: 'pointer' }}
          >
            📋 Test Suite ({app.test_case_count})
          </button>
          <button 
            className={`tab-btn ${activeTab === 'bugs' ? 'active' : ''}`}
            onClick={() => setActiveTab('bugs')}
            style={{ padding: '12px 18px', fontWeight: 600, fontSize: '0.9rem', cursor: 'pointer' }}
          >
            🐞 App Bugs ({app.bug_count})
          </button>
          <button 
            className={`tab-btn ${activeTab === 'sessions' ? 'active' : ''}`}
            onClick={() => setActiveTab('sessions')}
            style={{ padding: '12px 18px', fontWeight: 600, fontSize: '0.9rem', cursor: 'pointer' }}
          >
            🔑 Sessions & Auth
          </button>
          <button 
            className={`tab-btn ${activeTab === 'quality' ? 'active' : ''}`}
            onClick={() => setActiveTab('quality')}
            style={{ padding: '12px 18px', fontWeight: 600, fontSize: '0.9rem', cursor: 'pointer' }}
          >
            📊 Quality Dashboard
          </button>
        </div>

        {/* Tab Content Views */}
        <div className="tab-content">
          {activeTab === 'discovery' && (
            <DiscoveryStatus 
              appId={app.id} 
              appStatus={app.status} 
              discoverySource={app.discovery_source}
              onDiscoveryComplete={handleDiscoveryComplete}
              currentTask={currentTask}
            />
          )}

          {activeTab === 'apis' && (
            <div className="glass-card api-status-card animate-slide-up" style={{ padding: '24px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', flexWrap: 'wrap', gap: '12px' }}>
                <div>
                  <h3 style={{ fontSize: '1.2rem', fontWeight: 700 }}>🔌 Intercepted API Endpoints</h3>
                  <p className="card-subtitle" style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                    REST, Axios, and GraphQL endpoints monitored during crawlers and runs
                  </p>
                </div>

                <input
                  type="text"
                  placeholder="🔍 Search endpoints by method or URL pattern..."
                  value={apiSearchQuery}
                  onChange={(e) => setApiSearchQuery(e.target.value)}
                  style={{
                    padding: '8px 14px',
                    borderRadius: '8px',
                    border: '1px solid rgba(255, 255, 255, 0.12)',
                    background: 'rgba(11, 8, 22, 0.6)',
                    color: '#fff',
                    fontSize: '0.85rem',
                    minWidth: '260px'
                  }}
                />
              </div>
              
              {apiEndpoints.length === 0 ? (
                <div className="empty-state-card">
                  <svg className="empty-state-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ color: '#06b6d4' }}>
                    <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
                    <polyline points="15 3 21 3 21 9"></polyline>
                    <line x1="10" y1="14" x2="21" y2="3"></line>
                  </svg>
                  <h4 className="empty-state-title">No API Endpoints Captured Yet</h4>
                  <p className="empty-state-desc">
                    As Playwright crawls your application or executes automated test cases, background HTTP API traffic 
                    (GET, POST, PUT, DELETE) will automatically be intercepted and cataloged here.
                  </p>
                  <button onClick={handleStartDiscovery} className="btn-primary" style={{ padding: '8px 20px' }}>
                    🔍 Run Crawler to Discover APIs
                  </button>
                </div>
              ) : (
                <div className="api-endpoints-table-container" style={{ overflowX: 'auto', marginBottom: '30px' }}>
                  <table className="api-endpoints-table" style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                      <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.1)', textAlign: 'left', color: 'var(--text-muted)', fontSize: '0.8rem' }}>
                        <th style={{ padding: '12px' }}>METHOD</th>
                        <th style={{ padding: '12px' }}>URL PATTERN</th>
                        <th style={{ padding: '12px' }}>AUTH TYPE</th>
                        <th style={{ padding: '12px' }}>SCHEMA FIELDS</th>
                        <th style={{ padding: '12px' }}>ACTIONS</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredApiEndpoints.map((ep) => (
                        <React.Fragment key={ep.id}>
                          <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                            <td style={{ padding: '12px' }}>
                              <span className={`method-badge method-${ep.method.toLowerCase()}`}>
                                {ep.method}
                              </span>
                            </td>
                            <td style={{ padding: '12px', fontFamily: 'var(--font-mono)', fontSize: '0.85rem' }}>{ep.url_pattern}</td>
                            <td style={{ padding: '12px', fontSize: '0.82rem', color: 'var(--text-muted)' }}>{ep.auth_type || 'none'}</td>
                            <td style={{ padding: '12px', fontSize: '0.82rem' }}>
                              {ep.response_schema ? `${Object.keys(ep.response_schema).length} fields` : 'no schema'}
                            </td>
                            <td style={{ padding: '12px' }}>
                              <button 
                                className="btn-secondary" 
                                style={{ padding: '4px 10px', fontSize: '0.78rem' }}
                                onClick={async () => {
                                  if (selectedApiAnalysis?.endpoint_id === ep.id) {
                                    setSelectedApiAnalysis(null);
                                    return;
                                  }
                                  setLoadingApiAnalysisId(ep.id);
                                  try {
                                    const analysisRes = await api.get(`api-endpoints/${ep.id}/analyze/`);
                                    setSelectedApiAnalysis(analysisRes.data);
                                  } catch (err) {
                                    console.error(err);
                                  } finally {
                                    setLoadingApiAnalysisId(null);
                                  }
                                }}
                              >
                                {loadingApiAnalysisId === ep.id ? 'Loading...' : selectedApiAnalysis?.endpoint_id === ep.id ? 'Hide Analysis' : 'Inspect API'}
                              </button>
                            </td>
                          </tr>
                          {selectedApiAnalysis?.endpoint_id === ep.id && (
                            <tr>
                              <td colSpan={5} style={{ background: 'rgba(0,0,0,0.3)', padding: '16px' }}>
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                                  <div>
                                    <h4 style={{ margin: '0 0 8px 0', color: '#60a5fa', fontSize: '0.9rem' }}>📈 Live Health Metrics</h4>
                                    <div style={{ background: 'rgba(255,255,255,0.02)', padding: '12px', borderRadius: '8px', fontSize: '0.82rem' }}>
                                      <p><strong>Health Score:</strong> {selectedApiAnalysis.health_score} / 100</p>
                                      <p><strong>Total Calls:</strong> {selectedApiAnalysis.total_calls_tracked}</p>
                                      <p><strong>Average Latency:</strong> {selectedApiAnalysis.latency.avg_ms} ms</p>
                                    </div>
                                  </div>
                                  <div>
                                    <h4 style={{ margin: '0 0 8px 0', color: '#60a5fa', fontSize: '0.9rem' }}>📄 Response Schema</h4>
                                    <pre style={{ background: '#111827', padding: '12px', borderRadius: '8px', fontSize: '0.75rem', margin: 0, maxHeight: '140px', overflowY: 'auto' }}>
                                      {JSON.stringify(ep.response_schema, null, 2)}
                                    </pre>
                                  </div>
                                </div>
                              </td>
                            </tr>
                          )}
                        </React.Fragment>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {activeTab === 'tests' && (
            <div style={{ position: 'relative' }}>
              {isTestCasesLoading ? (
                <div className="glass-card" style={{ padding: '40px', textAlign: 'center', display: 'flex', flexDirection: 'column', gap: '12px', alignItems: 'center' }}>
                  <div className="spinner-small" style={{ borderTopColor: '#8b5cf6' }} />
                  <p style={{ color: 'rgba(255,255,255,0.6)', fontSize: '0.9rem' }}>Loading test suite...</p>
                </div>
              ) : testCasesError ? (
                <div className="glass-card" style={{ padding: '30px', textAlign: 'center', border: '1px solid rgba(239, 68, 68, 0.3)' }}>
                  <span style={{ fontSize: '2rem' }}>⚠️</span>
                  <h4 style={{ color: '#ef4444', margin: '8px 0' }}>Failed to Load Test Cases</h4>
                  <button onClick={() => refetchAll()} className="btn-secondary" style={{ padding: '6px 16px', fontSize: '0.8rem', marginTop: '12px' }}>
                    🔄 Try Again
                  </button>
                </div>
              ) : (
                <TestCaseList 
                  appId={app.id}
                  testCases={testCases}
                  totalCount={totalTestCasesCount || app?.test_case_count || testCases.length}
                  page={testCasesPage}
                  pageSize={testCasesPageSize}
                  onPageChange={(newPage) => setTestCasesPage(newPage)}
                  onPageSizeChange={(newSize) => {
                    setTestCasesPageSize(newSize);
                    setTestCasesPage(1);
                  }}
                  onRefreshTests={refetchAll}
                  onTestExecuted={(runId, taskId) => {
                    if (taskId) {
                      setActiveTaskId(taskId);
                    }
                    navigate(`/results/${runId}`);
                  }}
                  onTaskTriggered={(taskId) => {
                    setActiveTaskId(taskId);
                  }}
                  activeTaskId={activeTaskId}
                />
              )}
            </div>
          )}

          {activeTab === 'bugs' && (
            <BugList 
              bugs={bugs} 
              onRefreshBugs={refetchAll}
              onRunTestCase={handleRunTestCase}
              activeTaskId={activeTaskId}
            />
          )}

          {activeTab === 'sessions' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              <div className="glass-card animate-slide-up" style={{ padding: '24px' }}>
                <h3 style={{ fontSize: '1.2rem', fontWeight: 700 }}>🔑 Preserved Auth Session State</h3>
                <p className="card-subtitle" style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                  Active credentials, cookies, and local storage variables preserved from Playwright automation runs.
                </p>
                
                {(() => {
                  let cookies: any[] = [];
                  try {
                    if (app?.storage_state) {
                      const parsed = JSON.parse(app.storage_state);
                      cookies = parsed.cookies || [];
                    }
                  } catch (err) {}
                  
                  return (
                    <div style={{ marginTop: '16px' }}>
                      <h4 style={{ color: '#60a5fa', marginBottom: '8px', fontSize: '0.9rem' }}>🍪 Preserved Session Cookies</h4>
                      <div style={{ overflowX: 'auto' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.82rem' }}>
                          <thead>
                            <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.1)', textAlign: 'left' }}>
                              <th style={{ padding: '8px' }}>Name</th>
                              <th style={{ padding: '8px' }}>Domain</th>
                              <th style={{ padding: '8px' }}>Value</th>
                              <th style={{ padding: '8px' }}>Path</th>
                            </tr>
                          </thead>
                          <tbody>
                            {cookies.length === 0 ? (
                              <tr>
                                <td colSpan={4} style={{ padding: '16px', textAlign: 'center', color: 'rgba(255,255,255,0.5)' }}>
                                  No session cookies captured yet.
                                </td>
                              </tr>
                            ) : (
                              cookies.map((c, idx) => (
                                <tr key={idx} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                                  <td style={{ padding: '8px', fontWeight: 'bold' }}>{c.name}</td>
                                  <td style={{ padding: '8px' }}>{c.domain}</td>
                                  <td style={{ padding: '8px', fontFamily: 'monospace', maxWidth: '220px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.value}</td>
                                  <td style={{ padding: '8px' }}>{c.path}</td>
                                </tr>
                              ))
                            )}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  );
                })()}
              </div>

              <div className="glass-card animate-slide-up" style={{ padding: '24px' }}>
                <h3 style={{ fontSize: '1.2rem', fontWeight: 700 }}>🤖 Autonomous Agent Log Sessions</h3>
                <p className="card-subtitle" style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                  Trace history of Browser-Use reasoning and goal planning runs.
                </p>
                <div style={{ marginTop: '16px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  {agentSessions.length === 0 ? (
                    <div style={{ padding: '20px', textAlign: 'center', color: 'rgba(255,255,255,0.5)' }}>
                      No agent session logs recorded yet.
                    </div>
                  ) : (
                    agentSessions.map((session) => (
                      <div key={session.id} style={{ border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px', padding: '14px', background: 'rgba(255,255,255,0.02)' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                          <strong>{session.task_type.toUpperCase()} ({session.llm_model})</strong>
                          <span className={`badge-status ${session.status === 'completed' ? 'badge-status-passed' : 'badge-status-failed'}`}>
                            {session.status}
                          </span>
                        </div>
                        <p style={{ margin: '0 0 8px 0', fontSize: '0.85rem', color: 'rgba(255,255,255,0.85)' }}>{session.result_summary}</p>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          )}

          {activeTab === 'quality' && (
            <QualityDashboard applicationId={app.id.toString()} />
          )}
        </div>
      </div>

      {activeTestRunId && (
        <div className="results-panel-drawer">
          <div className="results-panel-drawer-overlay" onClick={() => setActiveTestRunId(null)}></div>
          <div className="results-panel-drawer-content">
            <TestResults 
              testRunId={activeTestRunId} 
              onClose={() => setActiveTestRunId(null)}
              onBugDetected={refetchAll}
            />
          </div>
        </div>
      )}
    </div>
  );
};
