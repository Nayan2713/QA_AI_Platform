import React, { useState, useEffect } from 'react';
import api from '../lib/api';
import { TestCase } from '../lib/types';

interface TestCaseListProps {
  appId: number;
  testCases: TestCase[];
  onTestExecuted: (testRunId: number, taskId?: string) => void;
  onRefreshTests: () => void;
  onTaskTriggered?: (taskId: string) => void;
  activeTaskId?: string | null;
}

export const TestCaseList: React.FC<TestCaseListProps> = ({
  appId,
  testCases,
  onTestExecuted,
  onRefreshTests,
  onTaskTriggered,
  activeTaskId
}) => {
  const [generating, setGenerating] = useState(false);
  const [executingTestCaseId, setExecutingTestCaseId] = useState<number | null>(null);
  const [executingAll, setExecutingAll] = useState(false);
  const [validatingIds, setValidatingIds] = useState<Record<number, boolean>>({});
  const [fixingIds, setFixingIds] = useState<Record<number, boolean>>({});
  const [validationResults, setValidationResults] = useState<Record<number, any>>({});
  const [error, setError] = useState('');
  const [successMsg, setSuccessMsg] = useState('');

  // Suite Progress Tracking State
  const [suiteRuns, setSuiteRuns] = useState<Array<{ id: number, testCaseId: number, title: string, status: string }>>([]);
  const [suiteRunStartTime, setSuiteRunStartTime] = useState<number | null>(null);
  const [showSuiteProgress, setShowSuiteProgress] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  useEffect(() => {
    if (!activeTaskId) {
      setGenerating(false);
      setSuccessMsg('');
    }
  }, [activeTaskId]);

  // Live ticking timer for elapsed duration
  useEffect(() => {
    if (!showSuiteProgress || !suiteRunStartTime) {
      setElapsedSeconds(0);
      return;
    }
    const hasUnfinished = suiteRuns.some(r => r.status === 'PENDING' || r.status === 'RUNNING');
    if (!hasUnfinished) return;

    const intervalId = setInterval(() => {
      setElapsedSeconds(Math.floor((Date.now() - suiteRunStartTime) / 1000));
    }, 1000);

    return () => clearInterval(intervalId);
  }, [showSuiteProgress, suiteRunStartTime, suiteRuns]);

  // Polling suite runs statuses
  useEffect(() => {
    if (!showSuiteProgress || suiteRuns.length === 0) return;

    const hasUnfinished = suiteRuns.some(r => r.status === 'PENDING' || r.status === 'RUNNING');
    if (!hasUnfinished) return;

    let isMounted = true;
    const intervalId = setInterval(async () => {
      try {
        const res = await api.get('test-runs/');
        if (!isMounted) return;

        const latestRuns = res.data;
        const updatedRuns = suiteRuns.map(r => {
          const match = latestRuns.find((lr: any) => lr.id === r.id);
          return match ? { ...r, status: match.status } : r;
        });

        const hasChanges = updatedRuns.some((r, i) => r.status !== suiteRuns[i].status);
        if (hasChanges) {
          setSuiteRuns(updatedRuns);
          const stillUnfinished = updatedRuns.some(r => r.status === 'PENDING' || r.status === 'RUNNING');
          if (!stillUnfinished) {
            onRefreshTests();
          }
        }
      } catch (err) {
        console.error('Error polling suite runs:', err);
      }
    }, 2000);

    return () => {
      isMounted = false;
      clearInterval(intervalId);
    };
  }, [showSuiteProgress, suiteRuns]);

  const formatDuration = (secs: number) => {
    const mins = Math.floor(secs / 60);
    const remainingSecs = Math.floor(secs % 60);
    return `${mins.toString().padStart(2, '0')}:${remainingSecs.toString().padStart(2, '0')}`;
  };

  const handleGenerateTests = async () => {
    setGenerating(true);
    setError('');
    setSuccessMsg('');
    try {
      const res = await api.post('test-cases/generate/', { app_id: appId });
      setSuccessMsg('Test suite generation started! Polling database...');
      if (res.data.task_id && onTaskTriggered) {
        onTaskTriggered(res.data.task_id);
      }
    } catch (err: any) {
      console.error(err);
      setError('Failed to trigger AI test case generation.');
      setGenerating(false);
    }
  };

  const handleRunTest = async (testCaseId: number) => {
    setExecutingTestCaseId(testCaseId);
    setError('');
    setSuccessMsg('');
    try {
      const response = await api.post('test-runs/execute/', { test_case_id: testCaseId });
      setSuccessMsg(`Test run execution started successfully.`);
      if (response.data.test_run_id) {
        onTestExecuted(response.data.test_run_id, response.data.task_id);
        
        const tc = testCases.find(t => t.id === testCaseId);
        setSuiteRuns([{
          id: response.data.test_run_id,
          testCaseId: testCaseId,
          title: tc?.title || `Test Case #${testCaseId}`,
          status: 'PENDING'
        }]);
        setSuiteRunStartTime(Date.now());
        setShowSuiteProgress(true);
      }
    } catch (err: any) {
      console.error(err);
      setError('Failed to execute test run.');
    } finally {
      setExecutingTestCaseId(null);
    }
  };

  const handleValidateTest = async (testCaseId: number) => {
    setValidatingIds(prev => ({ ...prev, [testCaseId]: true }));
    setError('');
    setSuccessMsg('');
    try {
      const res = await api.post(`test-cases/${testCaseId}/validate_test/`);
      setValidationResults(prev => ({ ...prev, [testCaseId]: res.data }));
      if (res.data.validation_status === 'VERIFIED') {
        setSuccessMsg('Test case verified successfully! All selectors match elements on the page.');
      } else {
        setError('Verification failed: Some selectors do not exist in the page structure. Click Auto-Fix to repair.');
      }
      onRefreshTests();
    } catch (err: any) {
      console.error(err);
      setError('Failed to validate test case elements.');
    } finally {
      setValidatingIds(prev => ({ ...prev, [testCaseId]: false }));
    }
  };

  const handleAutoFixTest = async (testCaseId: number) => {
    setFixingIds(prev => ({ ...prev, [testCaseId]: true }));
    setError('');
    setSuccessMsg('');
    try {
      const res = await api.post(`test-cases/${testCaseId}/auto_fix/`);
      setValidationResults(prev => ({ ...prev, [testCaseId]: res.data }));
      const fixedCount = res.data.corrections_made || 0;
      if (res.data.validation_status === 'VERIFIED') {
        setSuccessMsg(`Auto-fix completed! Corrected ${fixedCount} selectors. Test is now verified and executable.`);
      } else {
        setSuccessMsg(`Auto-fix made ${fixedCount} adjustments, but test case still needs review.`);
      }
      onRefreshTests();
    } catch (err: any) {
      console.error(err);
      setError('Failed to auto-fix test case selectors.');
    } finally {
      setFixingIds(prev => ({ ...prev, [testCaseId]: false }));
    }
  };

  const handleRunAllTests = async () => {
    if (testCases.length === 0) return;
    setExecutingAll(true);
    setError('');
    setSuccessMsg('');
    try {
      setSuccessMsg(`Queueing execution for all ${testCases.length} tests...`);
      const testCaseIds = testCases.map(tc => tc.id);
      const response = await api.post('test-runs/execute_batch/', { test_case_ids: testCaseIds });
      
      const runs = response.data.runs.map((r: any) => {
        const tc = testCases.find(t => t.id === r.test_case_id);
        return {
          id: r.test_run_id,
          testCaseId: r.test_case_id,
          title: tc?.title || `Test Case #${r.test_case_id}`,
          status: 'PENDING'
        };
      });
      
      setSuiteRuns(runs);
      setSuiteRunStartTime(Date.now());
      setShowSuiteProgress(true);
      setSuccessMsg(`Successfully queued all ${testCases.length} tests for execution.`);
    } catch (err: any) {
      console.error(err);
      setError('Failed to run all test cases.');
    } finally {
      setExecutingAll(false);
    }
  };

  const getValidationBadge = (status: string) => {
    switch (status) {
      case 'VERIFIED':
        return <span className="badge-validation verified" style={{
          backgroundColor: 'rgba(34, 197, 94, 0.15)',
          color: '#22c55e',
          border: '1px solid rgba(34, 197, 94, 0.3)',
          padding: '2px 8px',
          borderRadius: '4px',
          fontSize: '0.8rem',
          fontWeight: '600'
        }}>✓ Verified</span>;
      case 'BROKEN':
        return <span className="badge-validation broken" style={{
          backgroundColor: 'rgba(239, 68, 68, 0.15)',
          color: '#ef4444',
          border: '1px solid rgba(239, 68, 68, 0.3)',
          padding: '2px 8px',
          borderRadius: '4px',
          fontSize: '0.8rem',
          fontWeight: '600'
        }}>⚠️ Broken Selectors</span>;
      default:
        return <span className="badge-validation draft" style={{
          backgroundColor: 'rgba(113, 128, 150, 0.15)',
          color: '#a0aec0',
          border: '1px solid rgba(113, 128, 150, 0.3)',
          padding: '2px 8px',
          borderRadius: '4px',
          fontSize: '0.8rem',
          fontWeight: '600'
        }}>Draft (Unverified)</span>;
    }
  };

  return (
    <div className="glass-card test-cases-card">
      <div className="card-header tests-header">
        <div>
          <h3>📋 AI-Generated Test Suite</h3>
          <p className="card-subtitle">Complete test plans constructed from discovered page structures</p>
        </div>
        <div style={{ display: 'flex', gap: '10px' }}>
          {testCases.length > 0 && (
            <button 
              onClick={handleRunAllTests} 
              disabled={executingAll || !!activeTaskId} 
              className="btn-secondary btn-run-all"
              style={{
                backgroundColor: '#10b981',
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
              {executingAll ? 'Starting Runs...' : '▶ Run All Tests'}
            </button>
          )}
          
          <button 
            onClick={handleGenerateTests} 
            disabled={generating || !!activeTaskId} 
            className="btn-primary btn-generate"
          >
            {generating ? (
              <div className="loader-container-inline">
                <div className="spinner-small"></div>
                <span>Generating Suite...</span>
              </div>
            ) : (
              '✨ Generate Tests with AI'
            )}
          </button>
        </div>
      </div>

      {error && <div className="error-alert">{error}</div>}
      {successMsg && <div className="success-alert">{successMsg}</div>}

      {(() => {
        const completedCount = suiteRuns.filter(r => r.status === 'COMPLETED' || r.status === 'FAILED').length;
        const remainingCount = suiteRuns.length - completedCount;
        const totalCount = suiteRuns.length;
        const pct = totalCount > 0 ? Math.round((completedCount / totalCount) * 100) : 0;

        let estRemainingSeconds = 0;
        if (remainingCount > 0) {
          if (completedCount > 0) {
            const avgSecondsPerTest = elapsedSeconds / completedCount;
            estRemainingSeconds = Math.round(avgSecondsPerTest * remainingCount);
          } else {
            estRemainingSeconds = remainingCount * 15;
          }
        }

        return showSuiteProgress && suiteRuns.length > 0 ? (
          <div className="suite-progress-panel" style={{
            background: 'rgba(30, 41, 59, 0.4)',
            border: '1px solid rgba(255, 255, 255, 0.1)',
            borderRadius: '12px',
            padding: '20px',
            margin: '0 20px 20px 20px',
            backdropFilter: 'blur(8px)'
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
              <h4 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: '8px', color: '#60a5fa' }}>
                ⚡ AI Test Execution Status
              </h4>
              <button 
                onClick={() => setShowSuiteProgress(false)}
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: 'rgba(255,255,255,0.4)',
                  cursor: 'pointer',
                  fontSize: '0.9rem'
                }}
              >
                ✕ Close Tracker
              </button>
            </div>

            <div style={{ display: 'flex', gap: '24px', flexWrap: 'wrap', marginBottom: '16px' }}>
              <div style={{ flex: 1, minWidth: '200px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', marginBottom: '6px', color: 'rgba(255,255,255,0.7)' }}>
                  <span>Overall Progress</span>
                  <span>{completedCount} / {totalCount} Completed ({pct}%)</span>
                </div>
                <div style={{ height: '8px', background: 'rgba(255,255,255,0.08)', borderRadius: '4px', overflow: 'hidden' }}>
                  <div style={{
                    width: `${pct}%`,
                    height: '100%',
                    background: 'linear-gradient(90deg, #3b82f6 0%, #10b981 100%)',
                    borderRadius: '4px',
                    transition: 'width 0.5s ease-out'
                  }} />
                </div>
              </div>

              <div style={{ display: 'flex', gap: '20px', alignItems: 'center' }}>
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.4)', textTransform: 'uppercase' }}>Elapsed Time</div>
                  <div style={{ fontSize: '1.2rem', fontWeight: 'bold', color: '#f59e0b', fontFamily: 'monospace' }}>
                    {formatDuration(elapsedSeconds)}
                  </div>
                </div>
                
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.4)', textTransform: 'uppercase' }}>Est. Remaining</div>
                  <div style={{ fontSize: '1.2rem', fontWeight: 'bold', color: remainingCount > 0 ? '#10b981' : 'rgba(255,255,255,0.4)', fontFamily: 'monospace' }}>
                    {remainingCount > 0 ? formatDuration(estRemainingSeconds) : 'Finished'}
                  </div>
                </div>
              </div>
            </div>

            <div className="suite-runs-grid" style={{ 
              display: 'grid', 
              gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', 
              gap: '8px',
              maxHeight: '120px',
              overflowY: 'auto',
              paddingRight: '6px'
            }}>
              {suiteRuns.map((run) => {
                let badgeColor = '#94a3b8';
                let badgeBg = 'rgba(148, 163, 184, 0.15)';
                let statusText = 'Pending';
                
                if (run.status === 'RUNNING') {
                  badgeColor = '#3b82f6';
                  badgeBg = 'rgba(59, 130, 246, 0.15)';
                  statusText = 'Running';
                } else if (run.status === 'COMPLETED') {
                  badgeColor = '#10b981';
                  badgeBg = 'rgba(16, 185, 129, 0.15)';
                  statusText = 'Passed';
                } else if (run.status === 'FAILED') {
                  badgeColor = '#ef4444';
                  badgeBg = 'rgba(239, 68, 68, 0.15)';
                  statusText = 'Failed';
                }

                return (
                  <div key={run.id} style={{ 
                    display: 'flex', 
                    alignItems: 'center', 
                    justifyContent: 'space-between', 
                    padding: '6px 10px', 
                    background: 'rgba(255,255,255,0.02)', 
                    border: '1px solid rgba(255,255,255,0.05)',
                    borderRadius: '6px',
                    fontSize: '0.8rem'
                  }}>
                    <span style={{ 
                      whiteSpace: 'nowrap', 
                      overflow: 'hidden', 
                      textOverflow: 'ellipsis', 
                      maxWidth: '130px',
                      color: 'rgba(255,255,255,0.8)'
                    }} title={run.title}>
                      {run.title}
                    </span>
                    <span style={{
                      color: badgeColor,
                      background: badgeBg,
                      padding: '2px 6px',
                      borderRadius: '4px',
                      fontSize: '0.75rem',
                      fontWeight: '600'
                    }}>
                      {statusText}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        ) : null;
      })()}

      {testCases.length === 0 ? (
        <div className="empty-state">
          <p>No test cases generated yet. Click "Generate Tests with AI" to create them.</p>
        </div>
      ) : (
        <div className="test-cases-table-container">
          <div className="test-cases-list">
            {testCases.map((tc) => {
              const tcValResults = validationResults[tc.id];
              return (
                <div key={tc.id} className="test-case-item">
                  <div className="test-case-main-info">
                    <div className="test-case-title-row" style={{ display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap' }}>
                      <h5 style={{ margin: 0 }}>{tc.title}</h5>
                      <span className={`badge-ai ${tc.ai_generated ? 'badge-ai-model' : 'badge-ai-fallback'}`}>
                        {tc.ai_generated ? '🤖 AI Generated' : '📋 Fallback Template'}
                      </span>
                      {getValidationBadge(tc.validation_status)}
                    </div>
                    
                    <div className="test-steps-block" style={{ marginTop: '16px' }}>
                      <h6>Steps:</h6>
                      <ol className="steps-list">
                        {tc.steps.map((step, idx) => {
                          const stepDetails = tcValResults?.steps?.find((s: any) => s.step_index === idx);
                          const isInvalid = stepDetails && !stepDetails.valid;
                          
                          return (
                            <li key={idx} className="step-list-item" style={{ 
                              color: isInvalid ? '#ff4d4d' : 'inherit',
                              textDecoration: isInvalid ? 'line-through' : 'none'
                            }}>
                              <span className="step-action" style={{
                                backgroundColor: isInvalid ? 'rgba(255, 77, 77, 0.15)' : 'rgba(255, 255, 255, 0.08)',
                                border: isInvalid ? '1px solid rgba(255, 77, 77, 0.4)' : '1px solid rgba(255, 255, 255, 0.15)'
                              }}>{step.action.toUpperCase()}</span>
                              {step.action === 'navigate' && (
                                <> to <code className="step-code">{step.target}</code></>
                              )}
                              {step.action === 'fill' && (
                                <> field <code className="step-code">{step.selector}</code> with <code className="step-code">"{step.value}"</code></>
                              )}
                              {step.action === 'click' && (
                                <> element <code className="step-code">{step.selector}</code></>
                              )}
                              {step.action === 'wait' && (
                                <> for <code className="step-code">{step.value} ms</code></>
                              )}
                              {step.action === 'assert' && (
                                <> element <code className="step-code">{step.selector || 'body'}</code> contains text <code className="step-code">"{step.value}"</code></>
                              )}
                              {step.action === 'hover' && (
                                <> hover over element <code className="step-code">{step.selector}</code></>
                              )}
                              {step.action === 'scroll' && (
                                <> scroll {step.selector ? <>element <code className="step-code">{step.selector}</code> into view</> : <>page down by <code className="step-code">{step.value}px</code></>}</>
                              )}
                              {step.action === 'select' && (
                                <> select option <code className="step-code">"{step.value}"</code> in element <code className="step-code">{step.selector}</code></>
                              )}
                              {step.action === 'screenshot' && (
                                <> capture page screenshot {step.value && <>labeled <code className="step-code">"{step.value}"</code></>}</>
                              )}
                              
                              {isInvalid && (
                                <span className="step-error-msg" style={{ marginLeft: '10px', fontSize: '0.85rem', color: '#ff6666' }}>
                                  ({stepDetails.reason})
                                </span>
                              )}
                            </li>
                          );
                        })}
                      </ol>
                    </div>

                    <div className="expected-results-block" style={{ marginTop: '12px' }}>
                      <strong>Expected Outcome:</strong> {tc.expected_result}
                    </div>
                  </div>

                  <div className="test-case-actions" style={{ display: 'flex', flexDirection: 'column', gap: '8px', justifyContent: 'center' }}>
                    <button 
                      onClick={() => handleRunTest(tc.id)} 
                      disabled={executingTestCaseId === tc.id || !!activeTaskId}
                      className="btn-run-test"
                      style={{ width: '150px' }}
                    >
                      {executingTestCaseId === tc.id ? 'Running...' : '▶ Run Test'}
                    </button>
                    
                    <button 
                      onClick={() => handleValidateTest(tc.id)} 
                      disabled={validatingIds[tc.id] || fixingIds[tc.id] || !!activeTaskId}
                      className="btn-secondary"
                      style={{ 
                        width: '150px',
                        padding: '6px 12px',
                        fontSize: '0.85rem',
                        backgroundColor: '#4a5568',
                        color: 'white',
                        border: 'none',
                        borderRadius: '6px',
                        cursor: 'pointer'
                      }}
                    >
                      {validatingIds[tc.id] ? 'Verifying...' : '🔍 Validate'}
                    </button>

                    {tc.validation_status !== 'VERIFIED' && (
                      <button 
                        onClick={() => handleAutoFixTest(tc.id)} 
                        disabled={validatingIds[tc.id] || fixingIds[tc.id] || !!activeTaskId}
                        className="btn-secondary"
                        style={{ 
                          width: '150px',
                          padding: '6px 12px',
                          fontSize: '0.85rem',
                          backgroundColor: '#718096',
                          color: 'white',
                          border: 'none',
                          borderRadius: '6px',
                          cursor: 'pointer'
                        }}
                      >
                        {fixingIds[tc.id] ? 'Fixing...' : '🔧 Auto-Fix'}
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};
