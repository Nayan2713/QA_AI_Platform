import React, { useState, useEffect } from 'react';
import api from '../lib/api';
import { TestCase } from '../lib/types';

interface TestCaseListProps {
  appId: number;
  testCases: TestCase[];
  onTestExecuted: (testRunId: number) => void;
  onRefreshTests: () => void;
}

export const TestCaseList: React.FC<TestCaseListProps> = ({
  appId,
  testCases,
  onTestExecuted,
  onRefreshTests
}) => {
  const [generating, setGenerating] = useState(false);
  const [executingTestCaseId, setExecutingTestCaseId] = useState<number | null>(null);
  const [error, setError] = useState('');
  const [successMsg, setSuccessMsg] = useState('');

  const handleGenerateTests = async () => {
    setGenerating(true);
    setError('');
    setSuccessMsg('');
    try {
      await api.post('test-cases/generate/', { app_id: appId });
      setSuccessMsg('Test suite generation started! Polling database...');
      // Wait a moment for generation task to run, then refresh
      setTimeout(() => {
        onRefreshTests();
        setGenerating(false);
        setSuccessMsg('');
      }, 5000);
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
        onTestExecuted(response.data.test_run_id);
      }
    } catch (err: any) {
      console.error(err);
      setError('Failed to execute test run.');
    } finally {
      setExecutingTestCaseId(null);
    }
  };

  return (
    <div className="glass-card test-cases-card">
      <div className="card-header tests-header">
        <div>
          <h3>📋 AI-Generated Test Suite</h3>
          <p className="card-subtitle">Complete test plans constructed from discovered page structures</p>
        </div>
        <button 
          onClick={handleGenerateTests} 
          disabled={generating} 
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
                    disabled={executingTestCaseId === tc.id}
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
