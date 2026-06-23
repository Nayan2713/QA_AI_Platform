import React, { useState, useEffect } from 'react';
import api from '../lib/api';
import { Application, TestCase, Bug, CeleryTask } from '../lib/types';
import { DiscoveryStatus } from './DiscoveryStatus';
import { TestCaseList } from './TestCaseList';
import { TestResults } from './TestResults';
import { BugList } from './BugList';
import QualityDashboard from './QualityDashboard/QualityDashboard';

interface AppDetailProps {
  appId: number;
  onBack: () => void;
  activeTestRunId?: number | null;
  setActiveTestRunId?: (id: number | null) => void;
  activeTaskId?: string | null;
  setActiveTaskId?: (id: string | null) => void;
}

export const AppDetail: React.FC<AppDetailProps> = ({ 
  appId, 
  onBack,
  activeTestRunId: propActiveTestRunId,
  setActiveTestRunId: propSetActiveTestRunId,
  activeTaskId: propActiveTaskId,
  setActiveTaskId: propSetActiveTaskId
}) => {
  const [app, setApp] = useState<Application | null>(null);
  const [testCases, setTestCases] = useState<TestCase[]>([]);
  const [bugs, setBugs] = useState<Bug[]>([]);
  const [loading, setLoading] = useState(true);
  const [discovering, setDiscovering] = useState(false);
  const [activeTab, setActiveTab] = useState<'discovery' | 'tests' | 'bugs' | 'quality'>('discovery');
  
  // Track active execution
  const [localActiveTestRunId, setLocalActiveTestRunId] = useState<number | null>(null);
  const activeTestRunId = propActiveTestRunId !== undefined ? propActiveTestRunId : localActiveTestRunId;
  const setActiveTestRunId = propSetActiveTestRunId || setLocalActiveTestRunId;

  // Task progress tracking
  const [localActiveTaskId, setLocalActiveTaskId] = useState<string | null>(null);
  const activeTaskId = propActiveTaskId !== undefined ? propActiveTaskId : localActiveTaskId;
  const setActiveTaskId = propSetActiveTaskId || setLocalActiveTaskId;
  const [currentTask, setCurrentTask] = useState<CeleryTask | null>(null);

  const fetchAppDetails = async () => {
    try {
      const appRes = await api.get<Application>(`applications/${appId}/`);
      setApp(appRes.data);
      setDiscovering(appRes.data.status === 'DISCOVERING');

      // Fetch test cases
      const testCasesRes = await api.get<TestCase[]>(`test-cases/?app=${appId}`);
      setTestCases(testCasesRes.data);

      // Fetch bugs
      const bugsRes = await api.get<Bug[]>(`bugs/?app=${appId}`);
      setBugs(bugsRes.data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAppDetails();
  }, [appId]);

  // Poll for background task status (progress, description logs)
  useEffect(() => {
    if (!activeTaskId) {
      setCurrentTask(null);
      return;
    }
    
    let errorCount = 0;
    let isMounted = true;
    let pollCount = 0;
    const MAX_POLLS = 400; // Stop polling after 10 minutes (400 * 1.5 sec)
    
    const fetchTaskStatus = async () => {
      if (!isMounted || pollCount >= MAX_POLLS) return;
      
      pollCount++;
      
      try {
        const res = await api.get<CeleryTask>(`tasks/${activeTaskId}/`);
        if (!isMounted) return;
        
        setCurrentTask(res.data);
        errorCount = 0; // reset on success
        
        if (res.data.status === 'success') {
          await fetchAppDetails();
          setTimeout(() => {
            if (isMounted) setActiveTaskId(null);
          }, 3000);
        } else if (res.data.status === 'failed') {
          await fetchAppDetails();
          setTimeout(() => {
            if (isMounted) setActiveTaskId(null);
          }, 5000);
        }
      } catch (err) {
        errorCount += 1;
        console.error(`Failed to poll task status (attempt ${errorCount}):`, err);
        if (errorCount >= 5) {
          if (isMounted) setActiveTaskId(null);
        }
      }
    };
    
    fetchTaskStatus();
    const intervalId = setInterval(fetchTaskStatus, 1500);
    
    return () => {
      isMounted = false;
      clearInterval(intervalId);
    };
  }, [activeTaskId]);

  const handleStartDiscovery = async () => {
    if (!app) return;
    setDiscovering(true);
    try {
      const res = await api.post(`applications/${appId}/discover/`);
      setApp(prev => prev ? { ...prev, status: 'DISCOVERING' } : null);
      if (res.data.task_id) {
        setActiveTaskId(res.data.task_id);
      }
    } catch (err) {
      console.error(err);
      setDiscovering(false);
    }
  };

  const handleDiscoveryComplete = () => {
    setDiscovering(false);
    fetchAppDetails();
    setActiveTab('tests'); // Auto navigate to tests when discovery completes
  };

  const handleDeleteAppDetail = async () => {
    if (!app) return;
    if (window.confirm(`Are you sure you want to delete "${app.url}"? All tests, runs, and bugs will be permanently deleted.`)) {
      try {
        await api.delete(`applications/${appId}/`);
        onBack();
      } catch (err) {
        console.error('Failed to delete application environment:', err);
      }
    }
  };

  const handleRunTestCase = async (testCaseId: number) => {
    try {
      const response = await api.post('test-runs/execute/', { test_case_id: testCaseId });
      if (response.data.test_run_id) {
        setActiveTestRunId(response.data.test_run_id);
        if (response.data.task_id) {
          setActiveTaskId(response.data.task_id);
        }
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

  if (loading || !app) {
    return (
      <div className="glass-card loading-state">
        <div className="spinner"></div>
        <p>Loading application details...</p>
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
            <span className="metric-tag">📋 {app.test_case_count} Test Cases</span>
            <span className="metric-tag bug-metric">🐞 {app.bug_count} Bugs Detected</span>
            {app.login_url && (
              <span className={`metric-tag login-status-tag ${
                app.login_status === 'SUCCESS' ? 'login-success' : 
                app.login_status === 'FAILED' ? 'login-failed' : 
                'login-pending'
              }`}
              style={{
                borderColor: 
                  app.login_status === 'SUCCESS' ? 'rgba(34, 197, 94, 0.4)' : 
                  app.login_status === 'FAILED' ? 'rgba(239, 68, 68, 0.4)' : 
                  'rgba(234, 179, 8, 0.4)',
                color: 
                  app.login_status === 'SUCCESS' ? '#22c55e' : 
                  app.login_status === 'FAILED' ? '#ef4444' : 
                  '#eab308',
                backgroundColor: 
                  app.login_status === 'SUCCESS' ? 'rgba(34, 197, 94, 0.1)' : 
                  app.login_status === 'FAILED' ? 'rgba(239, 68, 68, 0.1)' : 
                  'rgba(234, 179, 8, 0.1)'
              }}>
                {app.login_status === 'SUCCESS' ? '🔑 Authenticated' : 
                 app.login_status === 'FAILED' ? '⚠️ Login Failed' : 
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

      {/* Internal Task Progress Tracker */}
      {currentTask && (
        <div className="glass-card task-progress-tracker" style={{
          margin: '20px 0',
          padding: '16px',
          border: '1px solid rgba(255, 255, 255, 0.15)',
          background: 'rgba(30, 30, 40, 0.65)',
          backdropFilter: 'blur(16px)',
          borderRadius: '12px',
          boxShadow: '0 8px 32px 0 rgba(0, 0, 0, 0.37)'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
            <span style={{ fontSize: '0.9rem', fontWeight: 'bold', textTransform: 'uppercase', letterSpacing: '0.05em', color: '#a0a0ff' }}>
              ⚙️ Internal Progress: {currentTask.task_type.replace('_', ' ')}
            </span>
            <span style={{ fontSize: '0.95rem', fontWeight: 'bold', color: '#ffffff' }}>
              {currentTask.progress}%
            </span>
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
              backgroundColor: currentTask.status === 'failed' ? '#ff4d4d' : '#a0a0ff',
              transition: 'width 0.4s ease-in-out',
              borderRadius: '4px'
            }} />
          </div>
          
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            {currentTask.status === 'progress' && <div className="spinner-small" />}
            <span style={{ fontSize: '0.9rem', color: 'rgba(255, 255, 255, 0.85)' }}>
              {currentTask.result?.status_text || currentTask.error || 'Running internal tasks...'}
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
            className={`tab-btn ${activeTab === 'tests' ? 'active' : ''}`}
            onClick={() => setActiveTab('tests')}
          >
            📋 Test Suite ({testCases.length})
          </button>
          <button 
            className={`tab-btn ${activeTab === 'bugs' ? 'active' : ''}`}
            onClick={() => setActiveTab('bugs')}
          >
            🐞 App Bugs ({bugs.length})
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

          {activeTab === 'tests' && (
            <TestCaseList 
              appId={app.id}
              testCases={testCases}
              onRefreshTests={fetchAppDetails}
              onTestExecuted={(runId, taskId) => {
                setActiveTestRunId(runId);
                if (taskId) {
                  setActiveTaskId(taskId);
                }
              }}
              onTaskTriggered={(taskId) => {
                setActiveTaskId(taskId);
              }}
              activeTaskId={activeTaskId}
            />
          )}

          {activeTab === 'bugs' && (
            <BugList 
              bugs={bugs} 
              onRefreshBugs={fetchAppDetails}
              onRunTestCase={handleRunTestCase}
              activeTaskId={activeTaskId}
            />
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
              onBugDetected={fetchAppDetails}
            />
          </div>
        </div>
      )}
    </div>
  );
};
