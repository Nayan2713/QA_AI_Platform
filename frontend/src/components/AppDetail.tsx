import React, { useState, useEffect } from 'react';
import api from '../lib/api';
import { Application, TestCase, Bug } from '../lib/types';
import { DiscoveryStatus } from './DiscoveryStatus';
import { TestCaseList } from './TestCaseList';
import { TestResults } from './TestResults';
import { BugList } from './BugList';

interface AppDetailProps {
  appId: number;
  onBack: () => void;
}

export const AppDetail: React.FC<AppDetailProps> = ({ appId, onBack }) => {
  const [app, setApp] = useState<Application | null>(null);
  const [testCases, setTestCases] = useState<TestCase[]>([]);
  const [bugs, setBugs] = useState<Bug[]>([]);
  const [loading, setLoading] = useState(true);
  const [discovering, setDiscovering] = useState(false);
  const [activeTab, setActiveTab] = useState<'discovery' | 'tests' | 'bugs'>('discovery');
  
  // Track active execution
  const [activeTestRunId, setActiveTestRunId] = useState<number | null>(null);

  const fetchAppDetails = async () => {
    try {
      const appRes = await api.get<Application>(`applications/${appId}/`);
      setApp(appRes.data);
      setDiscovering(appRes.data.status === 'DISCOVERING');

      // Fetch test cases
      const testCasesRes = await api.get<TestCase[]>(`test-cases/?app=${appId}`);
      // Filter test cases belonging to this app
      setTestCases(testCasesRes.data.filter(tc => tc.app === appId));

      // Fetch bugs
      const bugsRes = await api.get<Bug[]>(`bugs/`);
      setBugs(bugsRes.data.filter(b => b.app_url === appRes.data.url));
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAppDetails();
  }, [appId]);

  const handleStartDiscovery = async () => {
    if (!app) return;
    setDiscovering(true);
    try {
      await api.post(`applications/${appId}/discover/`);
      setApp(prev => prev ? { ...prev, status: 'DISCOVERING' } : null);
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
          </div>
        </div>
        
        <div className="header-actions">
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
        </div>
      </div>

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
              onTestExecuted={(runId) => setActiveTestRunId(runId)}
            />
          )}

          {activeTab === 'bugs' && (
            <BugList 
              bugs={bugs} 
              onRefreshBugs={fetchAppDetails}
            />
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
