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
  
  const mediaOrigin = (api.defaults.baseURL && api.defaults.baseURL.replace('/api/', '')) || (typeof window !== 'undefined' ? window.location.origin : 'http://127.0.0.1:8000');

  return (
    <div className="glass-card test-results-card">
      <div className="card-header results-header">
        <div>
          <h3>🎭 Browser Automation Execution Results</h3>
          <p className="card-subtitle">
            Test Case: <strong>{testRun.test_case_title}</strong>
          </p>
        </div>
        <div className="header-actions" style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <span className="badge-engine" style={{
            padding: '4px 8px',
            borderRadius: '6px',
            fontSize: '0.8rem',
            fontWeight: 'bold',
            background: ((testRun.metadata as any)?.engine_used === 'BROWSER_USE') ? 'rgba(160, 160, 255, 0.2)' : 'rgba(34, 197, 94, 0.2)',
            color: ((testRun.metadata as any)?.engine_used === 'BROWSER_USE') ? '#a0a0ff' : '#22c55e',
            border: `1px solid ${((testRun.metadata as any)?.engine_used === 'BROWSER_USE') ? 'rgba(160, 160, 255, 0.4)' : 'rgba(34, 197, 94, 0.4)'}`
          }}>
            🤖 {((testRun.metadata as any)?.engine_used === 'BROWSER_USE') ? 'BROWSER-USE AGENT' : 'PLAYWRIGHT ENGINE'}
          </span>
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

      {/* Video Playback */}
      {(testRun.metadata as any)?.video_path && (
        <div className="video-playback-box" style={{ margin: '16px 0', background: 'rgba(255,255,255,0.05)', padding: '12px', borderRadius: '8px' }}>
          <h4 style={{ margin: '0 0 8px 0' }}>🎥 Execution Video Recording</h4>
          <video 
            src={`${mediaOrigin}/media/${(testRun.metadata as any).video_path}`} 
            controls 
            style={{ width: '100%', borderRadius: '6px', maxHeight: '240px', background: '#000' }}
          />
        </div>
      )}

      {/* HAR Download Link */}
      {(testRun.metadata as any)?.har_path && (
        <div className="har-download-box" style={{ margin: '12px 0', fontSize: '0.9rem' }}>
          📥 <a 
            href={`${mediaOrigin}/media/${(testRun.metadata as any).har_path}`} 
            download 
            style={{ color: '#60a5fa', textDecoration: 'underline', fontWeight: '500' }}
          >
            Download HAR Network Traffic Trace File
          </a>
        </div>
      )}

      {/* Browser Console logs */}
      {(testRun.metadata as any)?.console_logs && (testRun.metadata as any).console_logs.length > 0 && (
        <div className="console-logs-box" style={{ margin: '16px 0', background: '#111827', padding: '12px', borderRadius: '8px' }}>
          <h4 style={{ margin: '0 0 8px 0', color: '#fbbf24' }}>💻 Browser Console Outputs</h4>
          <pre style={{ 
            maxHeight: '120px', 
            overflowY: 'auto', 
            margin: 0, 
            fontSize: '0.75rem', 
            fontFamily: 'monospace', 
            whiteSpace: 'pre-wrap', 
            color: '#f3f4f6' 
          }}>
            {(testRun.metadata as any).console_logs.join('\n')}
          </pre>
        </div>
      )}

      {/* Intercepted API calls list */}
      {(testRun.metadata as any)?.api_calls && (testRun.metadata as any).api_calls.length > 0 && (
        <div className="api-calls-box" style={{ margin: '16px 0', background: '#1f2937', padding: '12px', borderRadius: '8px' }}>
          <h4 style={{ margin: '0 0 8px 0', color: '#60a5fa' }}>🔌 Intercepted AJAX API Requests</h4>
          <div style={{ overflowX: 'auto', maxHeight: '180px' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.1)', textAlign: 'left', color: 'rgba(255,255,255,0.6)' }}>
                  <th style={{ padding: '6px' }}>Method</th>
                  <th style={{ padding: '6px' }}>URL</th>
                  <th style={{ padding: '6px' }}>Status</th>
                  <th style={{ padding: '6px' }}>Latency</th>
                </tr>
              </thead>
              <tbody>
                {(testRun.metadata as any).api_calls.map((call: any, idx: number) => (
                  <tr key={idx} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)', color: '#f3f4f6' }}>
                    <td style={{ padding: '6px' }}>
                      <span className={`badge-method method-${call.method?.toLowerCase()}`} style={{
                        padding: '2px 4px',
                        borderRadius: '3px',
                        fontWeight: 'bold',
                        fontSize: '0.7rem',
                        background: call.method === 'GET' ? 'rgba(34,197,94,0.2)' : 'rgba(59,130,246,0.2)',
                        color: call.method === 'GET' ? '#10b981' : '#3b82f6'
                      }}>
                        {call.method}
                      </span>
                    </td>
                    <td style={{ padding: '6px', fontFamily: 'monospace', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: '300px' }} title={call.url}>
                      {call.url}
                    </td>
                    <td style={{ padding: '6px' }}>
                      <span style={{ color: call.status >= 400 ? '#f87171' : '#34d399', fontWeight: 'bold' }}>{call.status}</span>
                    </td>
                    <td style={{ padding: '6px', color: call.latency > 1500 ? '#f59e0b' : 'inherit' }}>
                      {call.latency} ms
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

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
                        onClick={() => {
                          const ss = res.screenshot;
                          const origin = (api.defaults.baseURL && api.defaults.baseURL.replace('/api/', '')) || (typeof window !== 'undefined' ? window.location.origin : 'http://127.0.0.1:8000');
                          let src: string;
                          if (ss.length > 500) {
                            src = `data:image/png;base64,${ss}`;
                          } else if (ss.startsWith('http')) {
                            src = ss;
                          } else if (ss.startsWith('/')) {
                            src = `${origin}${ss}`;
                          } else {
                            src = `${origin}/media/${ss}`;
                          }
                          setSelectedScreenshot(src);
                        }}
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
