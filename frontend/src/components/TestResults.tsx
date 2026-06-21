import React, { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import api from '../lib/api';
import { TestRun } from '../lib/types';

interface TestResultsProps {
  testRunId: number;
  onClose: () => void;
  onBugDetected: () => void;
}

export const TestResults: React.FC<TestResultsProps> = ({
  testRunId,
  onClose,
  onBugDetected
}) => {
  const [testRun, setTestRun] = useState<TestRun | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selectedScreenshot, setSelectedScreenshot] = useState<string | null>(null);

  const fetchResults = async () => {
    try {
      const response = await api.get<TestRun>(`test-runs/${testRunId}/`);
      setTestRun(response.data);
      setError('');
      
      // If a bug is detected (i.e. bug count increases)
      if (response.data.bugs_found > 0) {
        onBugDetected();
      }
    } catch (err) {
      console.error('Failed to fetch test run details:', err);
      setError('Could not retrieve execution results.');
    } finally {
      setLoading(false);
    }
  };

  // Poll status of the test run if it is still running
  useEffect(() => {
    let intervalId: any;
    let isMounted = true;
    let pollCount = 0;
    const MAX_POLLS = 300; // Stop polling after 10 minutes (300 * 2 sec)

    const startPolling = async () => {
      if (!isMounted) return;
      
      await fetchResults();
      
      intervalId = setInterval(async () => {
        if (!isMounted || pollCount >= MAX_POLLS) {
          clearInterval(intervalId);
          return;
        }
        
        pollCount++;
        
        try {
          const response = await api.get<{ status: string; bugs_found: number; data: TestRun }>(`test-runs/${testRunId}/status/`);
          if (!isMounted) return;
          
          const status = response.data.status;
          setTestRun(response.data.data);
          
          if (status === 'COMPLETED' || status === 'FAILED') {
            clearInterval(intervalId);
            await fetchResults(); // fetch full results one last time
          }
        } catch (err) {
          console.error('Polling error:', err);
          clearInterval(intervalId);
          if (isMounted) {
            setError('Test run was cancelled, completed, or deleted.');
          }
        }
      }, 2000);
    };
    
    startPolling();

    return () => {
      isMounted = false;
      if (intervalId) clearInterval(intervalId);
    };
  }, [testRunId]);

  if (loading && !testRun) {
    return (
      <div className="glass-card test-results-card loading-state">
        <div className="spinner"></div>
        <p>Loading execution timeline...</p>
      </div>
    );
  }

  if (error || !testRun) {
    return (
      <div className="glass-card test-results-card error-state">
        <div className="error-alert">{error || 'Test run not found'}</div>
        <button onClick={onClose} className="btn-secondary">Close</button>
      </div>
    );
  }

  const isExecuting = testRun.status === 'PENDING' || testRun.status === 'RUNNING';

  return (
    <div className="glass-card test-results-card">
      <div className="card-header results-header">
        <div>
          <h3>🎭 Browser Automation Execution Results</h3>
          <p className="card-subtitle">
            Test Case: <strong>{testRun.test_case_title}</strong>
          </p>
        </div>
        <div className="header-actions">
          <span className={`badge-run-status status-${testRun.status.toLowerCase()}`}>
            {isExecuting ? '⏳ Running...' : testRun.status}
          </span>
          <button onClick={onClose} className="btn-close-panel">✕</button>
        </div>
      </div>

      <div className="run-metadata">
        <div className="meta-item">
          <span className="meta-label">App Target:</span>
          <span className="meta-val">{testRun.app_url}</span>
        </div>
        <div className="meta-item">
          <span className="meta-label">Executed At:</span>
          <span className="meta-val">{new Date(testRun.created_at).toLocaleString()}</span>
        </div>
        <div className="meta-item">
          <span className="meta-label">Bugs Logged:</span>
          <span className="meta-val bug-indicator">{testRun.bugs_found}</span>
        </div>
      </div>

      <div className="execution-timeline">
        <h4>📋 Step-by-Step Timeline Logs</h4>
        
        {(!testRun.results || testRun.results.length === 0) ? (
          <div className="empty-results-timeline">
            {isExecuting ? (
              <p>Spinning up browser environment... steps will start streaming shortly.</p>
            ) : (
              <p>No step results recorded. Playwright failed before starting the tests.</p>
            )}
          </div>
        ) : (
          <div className="timeline-steps-list">
            {testRun.results.map((res) => (
              <div key={res.id} className={`timeline-step-item status-${res.status.toLowerCase()}`}>
                <div className="step-badge-col">
                  <span className={`step-status-icon ${res.status === 'PASSED' ? 'icon-pass' : 'icon-fail'}`}>
                    {res.status === 'PASSED' ? '✓' : '✗'}
                  </span>
                </div>
                
                <div className="step-content-col">
                  <div className="step-main">
                    <span className="step-number">Step {res.step_number}</span>
                    <span className="step-result-status">{res.status}</span>
                  </div>
                  
                  {res.error && (
                    <div className="step-error-box">
                      <strong>Execution Error:</strong>
                      <pre className="error-trace">{res.error}</pre>
                    </div>
                  )}

                  {res.screenshot && (
                    <div className="step-screenshot-box">
                      <button 
                        onClick={() => setSelectedScreenshot(`data:image/png;base64,${res.screenshot}`)}
                        className="btn-view-screenshot"
                      >
                        📷 View Screenshot
                      </button>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {selectedScreenshot && createPortal(
        <div className="screenshot-modal-overlay" onClick={() => setSelectedScreenshot(null)}>
          <div className="screenshot-modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="screenshot-modal-header">
              <h5>Failed Checkpoint Screenshot</h5>
              <button onClick={() => setSelectedScreenshot(null)} className="btn-close-modal">✕</button>
            </div>
            <img src={selectedScreenshot} alt="Execution Failure Checkpoint" className="failure-screenshot-img" />
          </div>
        </div>,
        document.body
      )}
    </div>
  );
};
