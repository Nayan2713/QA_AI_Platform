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

  // 1. Fetch App details (Parallel/non-blocking with double-guard)
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const signal = controller.signal;
    // Only show the full-page skeleton on the very first load (no app data yet).
    // Background refreshes (triggered by SSE/polling) update silently in-place.
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

  // 2. Fetch Test Cases (Decoupled, parallel, 15s timeout with double-guard)
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const signal = controller.signal;
    // Only show loading spinner on first fetch — not on background refreshes (avoids blinking)
    if (testCases.length === 0) setIsTestCasesLoading(true);
    setTestCasesError(null);

    const fetchTestCases = async () => {
      try {
        const res = await api.get(`test-cases/?app=${appId}`, { signal, timeout: 15000 });
        const rawData = res.data;
        const data = Array.isArray(rawData) ? rawData : (rawData.results || []);
        if (active) {
          setTestCases(data);
        }
      } catch (err: any) {
        if (active && err.name !== 'CanceledError' && err.name !== 'AbortError') {
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
  }, [appId, refreshTrigger]);

  // 3. Fetch Bugs
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const signal = controller.signal;
    // Only show loading spinner on first fetch
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

  // 4. Fetch API Endpoints
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const signal = controller.signal;
    // Only show loading spinner on first fetch
    if (apiEndpoints.length === 0) setIsApiEndpointsLoading(true);

    const fetchEndpoints = async () => {
      try {
        const res = await api.get<APIEndpoint[]>(`api-endpoints/?app=${appId}`, { signal });
        if (active) {
          setApiEndpoints(res.data);
        }
      } catch (err: any) {
        if (active && err.name !== 'CanceledError' && err.name !== 'AbortError') {
          console.error('Failed to fetch API endpoints:', err);
        }
      } finally {
        if (active) {
          setIsApiEndpointsLoading(false);
        }
      }
    };

    fetchEndpoints();
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
    // Only show loading spinner on first fetch
    if (agentSessions.length === 0) setIsAgentSessionsLoading(true);

    const fetchSessions = async () => {
      try {
        const res = await api.get(`agent-sessions/?app=${appId}`, { signal });
        const rawData = res.data;
        const data = Array.isArray(rawData) ? rawData : (rawData.results || []);
        if (active) {
          setAgentSessions(data);
        }
      } catch (err: any) {
        if (active && err.name !== 'CanceledError' && err.name !== 'AbortError') {
          console.warn('Failed to fetch agent sessions:', err);
        }
      } finally {
        if (active) {
          setIsAgentSessionsLoading(false);
        }
      }
    };

    fetchSessions();
    return () => {
      active = false;
      controller.abort();
    };
  }, [appId, refreshTrigger]);

  // 6. Fetch API dependency Graph
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const signal = controller.signal;
    setIsApiGraphLoading(true);

    const fetchGraph = async () => {
      try {
        const res = await api.get<any>(`applications/${appId}/api-dependency-graph/`, { signal });
        if (active) {
          setApiGraph(res.data);
        }
      } catch (err: any) {
        if (active && err.name !== 'CanceledError' && err.name !== 'AbortError') {
          console.warn('Failed to fetch api dependency graph:', err);
        }
      } finally {
        if (active) {
          setIsApiGraphLoading(false);
        }
      }
    };

    fetchGraph();
    return () => {
      active = false;
      controller.abort();
    };
  }, [appId, refreshTrigger]);

  // Cleanup timeout hook
  useEffect(() => {
    return () => {
      if (refetchTimeoutRef.current) {
        clearTimeout(refetchTimeoutRef.current);
      }
    };
  }, []);

  // Restore active task if one is running for this application on mount
  useEffect(() => {
    let isMounted = true;
    // Reset currentTask immediately when switching applications
    setCurrentTask(null);

    const restoreActiveTask = async () => {
      try {
        const tasksRes = await api.get<CeleryTask[]>(`tasks/?app_id=${appId}`);
        if (!isMounted) return;
        const activeTask = tasksRes.data.find(t => t.status === 'pending' || t.status === 'progress');
        if (activeTask) {
          setActiveTaskId(activeTask.task_id);
          setCurrentTask(activeTask);
        } else {
          setActiveTaskId(null);
          setCurrentTask(null);
        }
      } catch (taskErr) {
        console.warn('Failed to restore active tasks:', taskErr);
        if (isMounted) {
          setActiveTaskId(null);
          setCurrentTask(null);
        }
      }
    };
    restoreActiveTask();
    return () => {
      isMounted = false;
    };
  }, [appId]);

  // Refs to allow SSE handler to access the latest state without reconnecting
  const activeTaskIdRef = React.useRef(activeTaskId);
  useEffect(() => {
    activeTaskIdRef.current = activeTaskId;
  }, [activeTaskId]);

  // Real-time updates via Server-Sent Events (SSE)
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

        switch (type) {
          case 'celerytask_created':
          case 'celerytask_updated':
            if (data.task_id === activeTaskIdRef.current && (!data.app || data.app === appId)) {
              setCurrentTask(data);
              if (data.status === 'success' || data.status === 'failed') {
                refetchAllDebounced();
                setTimeout(() => {
                  setActiveTaskId(null);
                  setCurrentTask(null);
                }, 3000);
              }
            }
            break;

          case 'application_updated':
            if (data.id === appId) {
              setApp(prev => prev ? { ...prev, ...data } : null);
              if (data.status === 'DISCOVERED' || data.status === 'FAILED') {
                setDiscovering(false);
                refetchAllDebounced();
              }
            }
            break;

          case 'page_created':
          case 'apiendpoint_created':
          case 'bug_created':
          case 'bug_updated':
          case 'testrun_updated':
            // Full data refetch when a complete run or bug finishes.
            // testresult_created (individual steps) is intentionally excluded to prevent
            // constant refetching during Run All Tests execution.
            refetchAllDebounced();
            break;

          case 'testresult_created':
            // Individual step results — no full refetch needed, the task progress
            // tracker already shows live step info via the backup polling loop.
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

  // Backup polling for Celery tasks using real-time celery-status endpoint
  useEffect(() => {
    if (!activeTaskId) return;
    
    let isMounted = true;
    let pollCount = 0;
    const MAX_POLLS = 150; // 5 minutes
    
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
          // Fetch DB task record details
          try {
            const taskDb = await api.get<CeleryTask>(`tasks/${activeTaskId}/`);
            if (isMounted) {
              if (taskDb.data.app && taskDb.data.app !== appId) {
                // Task belongs to another application! Clear task state for this view
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
      // Call stop-all to cancel every queued/running task for this app,
      // not just the single activeTaskId (Run All Tests queues many tasks at once)
      await api.post(`applications/${appId}/stop-all/`);
      setActiveTaskId(null);
      setCurrentTask(null);
      await refetchAll();
    } catch (err) {
      console.error('Failed to stop all tasks:', err);
    }
  };

  const handleStartDiscovery = async () => {
    if (!app) return;
    const oldStatus = app.status;
    
    // Optimistic UI updates
    setDiscovering(true);
    setApp(prev => prev ? { ...prev, status: 'DISCOVERING' } : null);
    
    try {
      const res = await api.post(`applications/${appId}/discover/`);
      if (res.data.task_id) {
        setActiveTaskId(res.data.task_id);
      }
    } catch (err) {
      console.error(err);
      // Rollback on error
      setDiscovering(false);
      setApp(prev => prev ? { ...prev, status: oldStatus } : null);
    }
  };

  const handleDiscoveryComplete = () => {
    setDiscovering(false);
    refetchAll();
    setActiveTab('tests'); // Auto navigate to tests when discovery completes
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
      // Fetch pages list dynamically to get full URLs and titles
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
      
      // Trigger file download
      const blob = new Blob([reportContent], { type: 'text/markdown;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      
      // Clean filename from app url
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

  // If base application metadata failed to load, render connection retry overlay
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

  // Render shimmer page skeleton *only* on initial load when app data is not yet available
  if (!app) {
    return (
      <div className="glass-card loading-state" style={{ padding: '40px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
        <style>{`
          @keyframes shimmer {
            0% { background-position: -200% 0; }
            100% { background-position: 200% 0; }
          }
          .skeleton-line {
            height: 16px;
            background: linear-gradient(90deg, rgba(255,255,255,0.03) 25%, rgba(255,255,255,0.08) 50%, rgba(255,255,255,0.03) 75%);
            background-size: 200% 100%;
            animation: shimmer 1.5s infinite;
            border-radius: 4px;
          }
        `}</style>
        <div className="skeleton-line" style={{ width: '40%', height: '32px', marginBottom: '10px' }} />
        <div className="skeleton-line" style={{ width: '80%' }} />
        <div className="skeleton-line" style={{ width: '60%' }} />
        <div style={{ display: 'flex', gap: '12px', marginTop: '20px' }}>
          <div className="skeleton-line" style={{ width: '120px', height: '40px', borderRadius: '8px' }} />
          <div className="skeleton-line" style={{ width: '120px', height: '40px', borderRadius: '8px' }} />
          <div className="skeleton-line" style={{ width: '120px', height: '40px', borderRadius: '8px' }} />
        </div>
      </div>
    );
  }

  return (
    <div className="app-detail-container">
      <button onClick={onBack} className="btn-back-link">
        ← Back to Applications
      </button>

      {/* Main app panel */}
      <div className="glass-card app-detail-header-card">
        <div className="header-info">
          <h2>🌐 {app.url}</h2>
          <p className="base-url-text">Base Domain: <code>{app.base_url}</code></p>
          <div className="app-details-metrics">
            <span className="metric-tag">📄 {app.page_count} Pages Discovered</span>
            <span className="metric-tag">🔗 {app.api_count} APIs Discovered</span>
            <span className="metric-tag">📋 {app.test_case_count} Test Cases</span>
            <span className="metric-tag bug-metric">🐞 {app.bug_count} Bugs Detected</span>
            <span className="metric-tag industry-tag" style={{
              borderColor: (!app.industry || app.industry === 'General') ? 'rgba(156, 163, 175, 0.4)' : 'rgba(99, 102, 241, 0.4)',
              color: (!app.industry || app.industry === 'General') ? '#d1d5db' : '#a5b4fc',
              backgroundColor: (!app.industry || app.industry === 'General') ? 'rgba(156, 163, 175, 0.1)' : 'rgba(99, 102, 241, 0.1)',
              fontWeight: 600
            }}>
              🏭 Industry: {app.industry || 'General'}
            </span>
            {app.login_url && (
              <span className={`metric-tag login-status-tag ${
                app.login_status === 'SUCCESS' ? 'login-success' : 
                app.login_status === 'FAILED' ? 'login-failed' : 
                'login-pending'
              }`}
              style={{
                borderColor: 
                  app.login_status === 'SUCCESS' ? 'rgba(34, 197, 94, 0.4)' : 
                  app.login_status === 'FAILED' ? (showLoginError ? '#ff4d4d' : 'rgba(239, 68, 68, 0.4)') : 
                  'rgba(234, 179, 8, 0.4)',
                color: 
                  app.login_status === 'SUCCESS' ? '#22c55e' : 
                  app.login_status === 'FAILED' ? '#ff4d4d' : 
                  '#eab308',
                backgroundColor: 
                  app.login_status === 'SUCCESS' ? 'rgba(34, 197, 94, 0.1)' : 
                  app.login_status === 'FAILED' ? 'rgba(239, 68, 68, 0.15)' : 
                  'rgba(234, 179, 8, 0.1)',
                cursor: app.login_status === 'FAILED' ? 'pointer' : 'default',
                boxShadow: app.login_status === 'FAILED' && showLoginError ? '0 0 10px rgba(239, 68, 68, 0.3)' : 'none',
                transition: 'all 0.2s ease',
                userSelect: 'none'
              }}
              onClick={() => {
                if (app.login_status === 'FAILED') {
                  setShowLoginError(prev => !prev);
                }
              }}
              title={app.login_status === 'FAILED' ? "Click to view login failure details" : undefined}
              >
                {app.login_status === 'SUCCESS' ? '🔑 Authenticated' : 
                 app.login_status === 'FAILED' ? (showLoginError ? '⚠️ Login Failed ▲' : '⚠️ Login Failed ▼ (Click for details)') : 
                 '🔑 Auth Pending'}
              </span>
            )}
          </div>
        </div>
        
        <div className="header-actions" style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
          <button 
            onClick={handleStartDiscovery} 
            disabled={discovering} 
            className={`btn-primary btn-discover ${discovering ? 'discovering' : ''}`}
          >
            {discovering ? (
              <div className="loader-container-inline">
                <div className="spinner-small"></div>
                <span>Discovering...</span>
              </div>
            ) : (
              '🔍 Start Discovery Run'
            )}
          </button>

          <button 
            onClick={handleDownloadReport}
            className="btn-secondary"
            style={{
              backgroundColor: '#4a5568',
              color: '#ffffff',
              border: 'none',
              padding: '10px 16px',
              borderRadius: '8px',
              cursor: 'pointer',
              fontWeight: '600',
              display: 'flex',
              alignItems: 'center',
              gap: '6px'
            }}
          >
            📋 Export QA Report
          </button>
          
          <button 
            onClick={handleDeleteAppDetail}
            className="btn-danger"
            style={{
              backgroundColor: '#ff4d4d',
              color: '#ffffff',
              border: 'none',
              padding: '10px 16px',
              borderRadius: '8px',
              cursor: 'pointer',
              fontWeight: '600',
              display: 'flex',
              alignItems: 'center',
              gap: '6px'
            }}
          >
            🗑️ Delete
          </button>
        </div>

      </div>

      {/* Login Failure Diagnostics Card */}
      {showLoginError && app.login_status === 'FAILED' && (
        <>
          <style>{`
            @keyframes slideDownFade {
              from {
                opacity: 0;
                transform: translateY(-8px);
              }
              to {
                opacity: 1;
                transform: translateY(0);
              }
            }
            .diagnostic-card-container {
              animation: slideDownFade 0.25s ease-out forwards;
            }
          `}</style>
          <div className="glass-card diagnostic-card-container" style={{
            marginTop: '-12px',
            padding: '20px',
            border: '1px solid rgba(239, 68, 68, 0.35)',
            background: 'linear-gradient(135deg, rgba(239, 68, 68, 0.12) 0%, rgba(20, 10, 10, 0.7) 100%)',
            backdropFilter: 'blur(16px)',
            borderRadius: '12px',
            boxShadow: '0 8px 32px 0 rgba(239, 68, 68, 0.15)',
            display: 'flex',
            flexDirection: 'column',
            gap: '16px'
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <span style={{ fontSize: '1.4rem' }}>🚨</span>
                <div>
                  <h4 style={{ margin: 0, color: '#ff6b6b', fontWeight: 600, fontSize: '1.1rem' }}>
                    Login Failure Diagnostic Details
                  </h4>
                  <p style={{ margin: '2px 0 0 0', fontSize: '0.78rem', color: 'rgba(255, 255, 255, 0.5)' }}>
                    Captured during target environment analysis and test runs
                  </p>
                </div>
              </div>
              <button 
                onClick={() => setShowLoginError(false)}
                style={{
                  background: 'rgba(255, 255, 255, 0.05)',
                  border: '1px solid rgba(255, 255, 255, 0.1)',
                  borderRadius: '6px',
                  color: 'rgba(255, 255, 255, 0.7)',
                  cursor: 'pointer',
                  fontSize: '0.8rem',
                  padding: '4px 8px',
                  transition: 'all 0.2s'
                }}
                onMouseOver={(e) => {
                  e.currentTarget.style.background = 'rgba(255, 255, 255, 0.1)';
                  e.currentTarget.style.color = '#fff';
                }}
                onMouseOut={(e) => {
                  e.currentTarget.style.background = 'rgba(255, 255, 255, 0.05)';
                  e.currentTarget.style.color = 'rgba(255, 255, 255, 0.7)';
                }}
              >
                ✕ Close
              </button>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <span style={{ fontSize: '0.8rem', fontWeight: 600, color: '#fca5a5', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Error Description
              </span>
              <div style={{
                background: 'rgba(0, 0, 0, 0.4)',
                border: '1px solid rgba(239, 68, 68, 0.25)',
                borderRadius: '8px',
                padding: '16px',
                fontFamily: 'Consolas, Monaco, monospace',
                fontSize: '0.85rem',
                color: '#fca5a5',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                boxShadow: 'inset 0 2px 8px rgba(0, 0, 0, 0.5)',
                maxHeight: '200px',
                overflowY: 'auto'
              }}>
                {app.login_error || 'No specific error message was captured. Please check if the login page is accessible and the configured credentials are valid.'}
              </div>
            </div>

            <div style={{
              borderTop: '1px solid rgba(255, 255, 255, 0.08)',
              paddingTop: '14px',
              fontSize: '0.85rem',
              color: 'rgba(255, 255, 255, 0.85)'
            }}>
              <strong style={{ color: '#fff', display: 'block', marginBottom: '8px' }}>💡 Recommended Troubleshooting Steps:</strong>
              <ul style={{ margin: 0, paddingLeft: '20px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                <li>
                  Check if the target login URL is active and matches: <a href={app.login_url} target="_blank" rel="noopener noreferrer" style={{ color: '#60a5fa', textDecoration: 'underline' }}><code>{app.login_url}</code></a>
                </li>
                <li>
                  Ensure the configured <strong>email/username</strong> and <strong>password</strong> fields are correct and have access rights.
                </li>
                <li>
                  Verify that your login form uses standard email/username and password input elements so that Playwright can automatically locate and fill them.
                </li>
                <li>
                  Ensure that your target site is not blocked by CAPTCHA, Cloudflare, or Multi-Factor Authentication (MFA) during automated login attempts.
                </li>
              </ul>
            </div>
          </div>
        </>
      )}

      {/* Internal Task Progress Tracker */}
      {currentTask && (!currentTask.app || currentTask.app === appId) && (
        <div className="glass-card task-progress-tracker" style={{
          margin: '20px 0',
          padding: '16px',
          border: `1px solid ${
            currentTask.status === 'success' ? 'rgba(34, 197, 94, 0.35)' :
            currentTask.status === 'failed' ? 'rgba(239, 68, 68, 0.35)' :
            'rgba(255, 255, 255, 0.15)'
          }`,
          background: 'rgba(30, 30, 40, 0.65)',
          backdropFilter: 'blur(16px)',
          borderRadius: '12px',
          boxShadow: '0 8px 32px 0 rgba(0, 0, 0, 0.37)'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
            <span style={{ 
              fontSize: '0.9rem', 
              fontWeight: 'bold', 
              textTransform: 'uppercase', 
              letterSpacing: '0.05em', 
              color: currentTask.status === 'success' ? '#22c55e' : currentTask.status === 'failed' ? '#ff4d4d' : '#a0a0ff' 
            }}>
              {currentTask.status === 'success' ? '✓ ' : currentTask.status === 'failed' ? '✗ ' : '⚙️ '} 
              Internal Progress: {currentTask.task_type.replace('_', ' ')}
            </span>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <span style={{ fontSize: '0.95rem', fontWeight: 'bold', color: '#ffffff' }}>
                {currentTask.progress}%
              </span>
              {(currentTask.status === 'pending' || currentTask.status === 'progress') && (
                <button
                  onClick={handleStopTask}
                  style={{
                    backgroundColor: 'rgba(239, 68, 68, 0.2)',
                    border: '1px solid rgba(239, 68, 68, 0.4)',
                    color: '#ff8888',
                    padding: '2px 8px',
                    borderRadius: '4px',
                    fontSize: '0.75rem',
                    cursor: 'pointer',
                    fontWeight: 'bold',
                    transition: 'all 0.2s'
                  }}
                  onMouseOver={(e) => {
                    e.currentTarget.style.backgroundColor = 'rgba(239, 68, 68, 0.4)';
                    e.currentTarget.style.color = '#ffffff';
                  }}
                  onMouseOut={(e) => {
                    e.currentTarget.style.backgroundColor = 'rgba(239, 68, 68, 0.2)';
                    e.currentTarget.style.color = '#ff8888';
                  }}
                >
                  🛑 Stop
                </button>
              )}
            </div>
          </div>
          
          <div style={{
            width: '100%',
            height: '8px',
            backgroundColor: 'rgba(255, 255, 255, 0.1)',
            borderRadius: '4px',
            overflow: 'hidden',
            marginBottom: '10px'
          }}>
            <div style={{
              width: `${currentTask.progress}%`,
              height: '100%',
              backgroundColor: 
                currentTask.status === 'success' ? '#22c55e' : 
                currentTask.status === 'failed' ? '#ff4d4d' : 
                '#a0a0ff',
              transition: 'width 0.4s ease-in-out',
              borderRadius: '4px'
            }} />
          </div>
          
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            {currentTask.status === 'progress' && <div className="spinner-small" />}
            <span style={{ fontSize: '0.9rem', color: 'rgba(255, 255, 255, 0.85)' }}>
              {currentTask.status === 'success' ? (
                currentTask.task_type === 'discovery' ? (
                  `Discovery complete! Found ${currentTask.result?.pages_discovered || 0} pages and cataloged ${currentTask.result?.apis_cataloged || 0} APIs.`
                ) : currentTask.task_type === 'test_generation' ? (
                  `Test generation complete! Created ${currentTask.result?.tests_generated || 0} test cases using ${currentTask.result?.model_used || 'Fallback Templates'}.`
                ) : currentTask.task_type === 'execution' ? (
                  `Execution complete! ${currentTask.result?.passed_steps || 0}/${currentTask.result?.total_steps || 0} steps passed.`
                ) : currentTask.task_type === 'bug_detection' ? (
                  `Bug audit complete! Discovered ${currentTask.result?.bugs_found || 0} defects.`
                ) : currentTask.task_type === 'quality_check' ? (
                  `Quality check complete! Calculations updated.`
                ) : (
                  currentTask.result?.status_text || 'Task completed successfully.'
                )
              ) : (
                currentTask.result?.status_text || currentTask.error || 'Running internal tasks...'
              )}
            </span>
          </div>
        </div>
      )}

      {/* Tab system */}
      <div className="tabs-container">
        <div className="tabs-header">
          <button 
            className={`tab-btn ${activeTab === 'discovery' ? 'active' : ''}`}
            onClick={() => setActiveTab('discovery')}
          >
            🔍 Discovery Details
          </button>
          <button 
            className={`tab-btn ${activeTab === 'apis' ? 'active' : ''}`}
            onClick={() => setActiveTab('apis')}
          >
            🔌 APIs & Graph ({apiEndpoints.length})
          </button>
          <button 
            className={`tab-btn ${activeTab === 'tests' ? 'active' : ''}`}
            onClick={() => setActiveTab('tests')}
          >
            📋 Test Suite ({app.test_case_count})
          </button>
          <button 
            className={`tab-btn ${activeTab === 'bugs' ? 'active' : ''}`}
            onClick={() => setActiveTab('bugs')}
          >
            🐞 App Bugs ({app.bug_count})
          </button>
          <button 
            className={`tab-btn ${activeTab === 'sessions' ? 'active' : ''}`}
            onClick={() => setActiveTab('sessions')}
          >
            🔑 Sessions & Auth
          </button>
          <button 
            className={`tab-btn ${activeTab === 'quality' ? 'active' : ''}`}
            onClick={() => setActiveTab('quality')}
          >
            📊 Quality Dashboard
          </button>
        </div>

        <div className="tab-content">
          {activeTab === 'discovery' && (
            <DiscoveryStatus 
              appId={app.id} 
              appStatus={app.status} 
              discoverySource={app.discovery_source}
              onDiscoveryComplete={handleDiscoveryComplete}
            />
          )}

          {activeTab === 'apis' && (
            <div className="glass-card api-status-card" style={{ padding: '20px' }}>
              <div className="card-header" style={{ marginBottom: '20px' }}>
                <div>
                  <h3>🔌 Discovered API Catalog</h3>
                  <p className="card-subtitle">REST, Axios, and GraphQL endpoints monitored during crawlers and runs.</p>
                </div>
              </div>
              
              <div className="api-endpoints-table-container" style={{ overflowX: 'auto', marginBottom: '30px' }}>
                <table className="api-endpoints-table" style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.1)', textAlign: 'left' }}>
                      <th style={{ padding: '12px' }}>Method</th>
                      <th style={{ padding: '12px' }}>Pattern</th>
                      <th style={{ padding: '12px' }}>Auth Type</th>
                      <th style={{ padding: '12px' }}>Schema</th>
                      <th style={{ padding: '12px' }}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {apiEndpoints.length === 0 ? (
                      <tr>
                        <td colSpan={5} style={{ padding: '20px', textAlign: 'center', color: 'var(--text-muted)' }}>
                          No background APIs intercepted yet. Perform crawler discovery or execute test cases.
                        </td>
                      </tr>
                    ) : (
                      apiEndpoints.map((ep) => (
                        <React.Fragment key={ep.id}>
                          <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                            <td style={{ padding: '12px' }}>
                              <span className={`badge-method method-${ep.method.toLowerCase()}`} style={{
                                padding: '4px 8px',
                                borderRadius: '4px',
                                fontWeight: 'bold',
                                fontSize: '0.75rem',
                                background: ep.method === 'GET' ? 'rgba(34, 197, 94, 0.2)' : 'rgba(59, 130, 246, 0.2)',
                                color: ep.method === 'GET' ? '#22c55e' : '#3b82f6'
                              }}>
                                {ep.method}
                              </span>
                            </td>
                            <td style={{ padding: '12px', fontFamily: 'monospace', fontSize: '0.85rem' }}>{ep.url_pattern}</td>
                            <td style={{ padding: '12px' }}>{ep.auth_type || 'none'}</td>
                            <td style={{ padding: '12px', fontSize: '0.8rem' }}>
                              {ep.response_schema ? `${Object.keys(ep.response_schema).length} fields` : 'no schema'}
                            </td>
                            <td style={{ padding: '12px' }}>
                              <button 
                                className="btn-secondary" 
                                style={{ padding: '4px 8px', fontSize: '0.8rem' }}
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
                                {loadingApiAnalysisId === ep.id ? 'Loading...' : selectedApiAnalysis?.endpoint_id === ep.id ? 'Hide Analysis' : 'Analyze API'}
                              </button>
                            </td>
                          </tr>
                          {selectedApiAnalysis?.endpoint_id === ep.id && (
                            <tr>
                              <td colSpan={5} style={{ background: 'rgba(0,0,0,0.2)', padding: '16px' }}>
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                                  <div>
                                    <h4 style={{ margin: '0 0 8px 0', color: '#60a5fa' }}>📈 Live Metrics & Health</h4>
                                    <div style={{ background: 'rgba(255,255,255,0.02)', padding: '12px', borderRadius: '6px' }}>
                                      <p><strong>Health Score:</strong> {selectedApiAnalysis.health_score} / 100</p>
                                      <p><strong>Total Calls:</strong> {selectedApiAnalysis.total_calls_tracked}</p>
                                      <p><strong>Average Latency:</strong> {selectedApiAnalysis.latency.avg_ms} ms</p>
                                      <p><strong>Status Failures:</strong> {selectedApiAnalysis.failures.status_errors}</p>
                                      <p><strong>Schema Violations:</strong> {selectedApiAnalysis.failures.schema_violations}</p>
                                    </div>
                                  </div>
                                  <div>
                                    <h4 style={{ margin: '0 0 8px 0', color: '#60a5fa' }}>📄 Response Schema contract</h4>
                                    <pre style={{ background: '#111827', padding: '12px', borderRadius: '6px', fontSize: '0.75rem', margin: 0, maxHeight: '150px', overflowY: 'auto' }}>
                                      {JSON.stringify(ep.response_schema, null, 2)}
                                    </pre>
                                  </div>
                                </div>
                              </td>
                            </tr>
                          )}
                        </React.Fragment>
                      ))
                    )}
                  </tbody>
                </table>
              </div>

              {/* Dependency Graph visual list */}
              {apiGraph && apiGraph.links.length > 0 && (
                <div style={{ background: 'rgba(255,255,255,0.02)', padding: '16px', borderRadius: '8px' }}>
                  <h4>🕸️ API Dependency Flow Graph</h4>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginTop: '12px' }}>
                    {apiGraph.links.map((link, lIdx) => {
                      const srcNode = apiGraph.nodes.find(n => n.id === link.source);
                      const tgtNode = apiGraph.nodes.find(n => n.id === link.target);
                      if (!srcNode || !tgtNode) return null;
                      return (
                        <div key={lIdx} style={{ display: 'flex', alignItems: 'center', gap: '12px', background: 'rgba(255,255,255,0.03)', padding: '8px 12px', borderRadius: '6px' }}>
                          <span style={{ fontSize: '0.8rem', color: '#10b981', fontFamily: 'monospace' }}>{srcNode.label}</span>
                          <span style={{ color: 'rgba(255,255,255,0.4)' }}>➔</span>
                          <span style={{ background: 'rgba(96,165,250,0.2)', color: '#60a5fa', fontSize: '0.75rem', padding: '2px 6px', borderRadius: '4px' }}>
                            pass {link.parameters.join(', ')}
                          </span>
                          <span style={{ color: 'rgba(255,255,255,0.4)' }}>➔</span>
                          <span style={{ fontSize: '0.8rem', color: '#f59e0b', fontFamily: 'monospace' }}>{tgtNode.label}</span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          )}

          {activeTab === 'tests' && (
            <div style={{ position: 'relative' }}>
              {isTestCasesLoading ? (
                <div className="glass-card" style={{ padding: '40px', textAlign: 'center', display: 'flex', flexDirection: 'column', gap: '12px', alignItems: 'center' }}>
                  <div className="spinner-small" style={{ borderTopColor: '#60a5fa' }} />
                  <p style={{ color: 'rgba(255,255,255,0.6)', fontSize: '0.9rem' }}>Loading test suite...</p>
                </div>
              ) : testCasesError ? (
                <div className="glass-card" style={{ padding: '30px', textAlign: 'center', border: '1px solid rgba(239, 68, 68, 0.3)' }}>
                  <span style={{ fontSize: '2rem' }}>⚠️</span>
                  <h4 style={{ color: '#ef4444', margin: '8px 0' }}>Failed to Load Test Cases</h4>
                  <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: '0.85rem', marginBottom: '16px' }}>
                    {testCasesError instanceof Error ? testCasesError.message : 'The request timed out or connection was refused.'}
                  </p>
                  <button onClick={() => refetchAll()} className="btn-secondary" style={{ padding: '6px 16px', fontSize: '0.8rem' }}>
                    🔄 Try Again
                  </button>
                </div>
              ) : (
                <TestCaseList 
                  appId={app.id}
                  testCases={testCases}
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
              {/* Storage State Section */}
              <div className="glass-card" style={{ padding: '20px' }}>
                <h3>🔑 Active Storage & Session State</h3>
                <p className="card-subtitle">Active credentials, cookies, and local storage variables preserved from Playwright runs.</p>
                
                {(() => {
                  let cookies: any[] = [];
                  let origins: any[] = [];
                  try {
                    if (app?.storage_state) {
                      const parsed = JSON.parse(app.storage_state);
                      cookies = parsed.cookies || [];
                      origins = parsed.origins || [];
                    }
                  } catch (err) {}
                  
                  return (
                    <div style={{ marginTop: '16px' }}>
                      <h4 style={{ color: '#60a5fa', marginBottom: '8px' }}>🍪 Preserved Session Cookies</h4>
                      <div style={{ overflowX: 'auto', marginBottom: '24px' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
                          <thead>
                            <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.1)', textAlign: 'left' }}>
                              <th style={{ padding: '8px' }}>Name</th>
                              <th style={{ padding: '8px' }}>Domain</th>
                              <th style={{ padding: '8px' }}>Value</th>
                              <th style={{ padding: '8px' }}>Path</th>
                              <th style={{ padding: '8px' }}>Expiry</th>
                            </tr>
                          </thead>
                          <tbody>
                            {cookies.length === 0 ? (
                              <tr>
                                <td colSpan={5} style={{ padding: '12px', textAlign: 'center', color: 'rgba(255,255,255,0.5)' }}>
                                  No session cookies captured yet. Login has not been executed or session was cleared.
                                </td>
                              </tr>
                            ) : (
                              cookies.map((c, idx) => (
                                <tr key={idx} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                                  <td style={{ padding: '8px', fontWeight: 'bold' }}>{c.name}</td>
                                  <td style={{ padding: '8px' }}>{c.domain}</td>
                                  <td style={{ padding: '8px', fontFamily: 'monospace', maxWidth: '200px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.value}</td>
                                  <td style={{ padding: '8px' }}>{c.path}</td>
                                  <td style={{ padding: '8px' }}>{c.expires ? new Date(c.expires * 1000).toLocaleDateString() : 'Session'}</td>
                                </tr>
                              ))
                            )}
                          </tbody>
                        </table>
                      </div>
                      
                      <h4 style={{ color: '#60a5fa', marginBottom: '8px' }}>📦 Local Storage Preserves</h4>
                      <div style={{ overflowX: 'auto' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
                          <thead>
                            <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.1)', textAlign: 'left' }}>
                              <th style={{ padding: '8px' }}>Origin</th>
                              <th style={{ padding: '8px' }}>Key</th>
                              <th style={{ padding: '8px' }}>Value</th>
                            </tr>
                          </thead>
                          <tbody>
                            {origins.length === 0 ? (
                              <tr>
                                <td colSpan={3} style={{ padding: '12px', textAlign: 'center', color: 'rgba(255,255,255,0.5)' }}>
                                  No Local Storage records captured yet.
                                </td>
                              </tr>
                            ) : (
                              origins.flatMap((originObj: any) => {
                                const localStorageItems = originObj.localStorage || [];
                                if (localStorageItems.length === 0) return [];
                                return localStorageItems.map((item: any, idx: number) => (
                                  <tr key={`${originObj.origin}-${idx}`} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                                    <td style={{ padding: '8px', color: 'rgba(255,255,255,0.5)' }}>{originObj.origin}</td>
                                    <td style={{ padding: '8px', fontWeight: 'bold' }}>{item.name}</td>
                                    <td style={{ padding: '8px', fontFamily: 'monospace', maxWidth: '300px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.value}</td>
                                  </tr>
                                ));
                              })
                            )}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  );
                })()}
              </div>
              
              {/* Agent Sessions list */}
              <div className="glass-card" style={{ padding: '20px' }}>
                <h3>🤖 Autonomous Agent Log Sessions</h3>
                <p className="card-subtitle">Trace history of Browser-Use reasoning and goal planning runs.</p>
                <div style={{ marginTop: '16px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  {agentSessions.length === 0 ? (
                    <div style={{ padding: '20px', textAlign: 'center', color: 'rgba(255,255,255,0.5)' }}>
                      No agent session logs recorded yet.
                    </div>
                  ) : (
                    agentSessions.map((session) => (
                      <div key={session.id} style={{ border: '1px solid rgba(255,255,255,0.1)', borderRadius: '6px', padding: '12px', background: 'rgba(255,255,255,0.01)' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                          <strong>{session.task_type.toUpperCase()} session ({session.llm_model})</strong>
                          <span className={`badge-status status-${session.status}`} style={{
                            padding: '2px 6px',
                            borderRadius: '4px',
                            fontSize: '0.75rem',
                            fontWeight: 'bold',
                            background: session.status === 'completed' ? 'rgba(34,197,94,0.2)' : 'rgba(239,68,68,0.2)',
                            color: session.status === 'completed' ? '#22c55e' : '#ef4444'
                          }}>{session.status}</span>
                        </div>
                        <p style={{ margin: '0 0 8px 0', fontSize: '0.85rem', color: 'rgba(255,255,255,0.85)' }}>{session.result_summary}</p>
                        <div style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.5)' }}>
                          Duration: {session.duration_seconds?.toFixed(1)}s | Tokens: {session.tokens_used} | Executed: {new Date(session.created_at).toLocaleString()}
                        </div>
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

      {/* Active Playwright run overlay/side drawer */}
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
