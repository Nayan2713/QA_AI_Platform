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
  const [error, setError] = useState('');
  const [successMsg, setSuccessMsg] = useState('');

  useEffect(() => {
    if (!activeTaskId) {
      setGenerating(false);
      setSuccessMsg('');
    }
  }, [activeTaskId]);

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
      
      // Let parent component know a test run has been triggered
      if (response.data.test_run_id) {
        onTestExecuted(response.data.test_run_id, response.data.task_id);
      }
    } catch (err: any) {
      console.error(err);
      setError('Failed to execute test run.');
    } finally {
      setExecutingTestCaseId(null);
    }
  };

  const handleRunAllTests = async () => {
    if (testCases.length === 0) return;
    setExecutingAll(true);
    setError('');
    setSuccessMsg('');
    try {
      setSuccessMsg(`Queueing execution for all ${testCases.length} tests...`);
      for (const tc of testCases) {
        const response = await api.post('test-runs/execute/', { test_case_id: tc.id });
        if (response.data.test_run_id) {
          onTestExecuted(response.data.test_run_id, response.data.task_id);
        }
      }
      setSuccessMsg(`Successfully queued all ${testCases.length} tests for execution.`);
    } catch (err: any) {
      console.error(err);
      setError('Failed to run all test cases.');
    } finally {
      setExecutingAll(false);
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

      {testCases.length === 0 ? (
        <div className="empty-state">
          <p>No test cases generated yet. Click "Generate Tests with AI" to create them.</p>
        </div>
      ) : (
        <div className="test-cases-table-container">
          <div className="test-cases-list">
            {testCases.map((tc) => (
              <div key={tc.id} className="test-case-item">
                <div className="test-case-main-info">
                  <div className="test-case-title-row">
                    <h5>{tc.title}</h5>
                    <span className={`badge-ai ${tc.ai_generated ? 'badge-ai-model' : 'badge-ai-fallback'}`}>
                      {tc.ai_generated ? '🤖 AI Generated' : '📋 Fallback Template'}
                    </span>
                  </div>
                  
                  <div className="test-steps-block">
                    <h6>Steps:</h6>
                    <ol className="steps-list">
                      {tc.steps.map((step, idx) => (
                        <li key={idx} className="step-list-item">
                          <span className="step-action">{step.action.toUpperCase()}</span>
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
                        </li>
                      ))}
                    </ol>
                  </div>

                  <div className="expected-results-block">
                    <strong>Expected:</strong> {tc.expected_result}
                  </div>
                </div>

                <div className="test-case-actions">
                  <button 
                    onClick={() => handleRunTest(tc.id)} 
                    disabled={executingTestCaseId === tc.id || !!activeTaskId}
                    className="btn-run-test"
                  >
                    {executingTestCaseId === tc.id ? 'Starting...' : '▶ Run Test'}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
