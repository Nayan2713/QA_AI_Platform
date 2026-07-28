import React, { useState, useEffect } from 'react';
import api from '../lib/api';
import { TestCase } from '../lib/types';
import { TestCaseFormModal } from './TestCaseFormModal';
import { BulkUploadModal } from './BulkUploadModal';

const getTestCategory = (tc: TestCase): 'Access Control' | 'Industry Flow' | 'Generic' => {
  if (tc.category) {
    return tc.category;
  }
  const title = tc.title;
  if (title.startsWith('[Access Control]')) {
    return 'Access Control';
  }
  const titleLower = title.toLowerCase();
  const isIndustryJourney = 
    title.includes('→') ||
    titleLower.includes('add to cart') ||
    titleLower.includes('cart total') ||
    titleLower.includes('empty-cart') ||
    titleLower.includes('out-of-stock') ||
    titleLower.includes('discount code') ||
    titleLower.includes('2fa') ||
    titleLower.includes('balance display') ||
    titleLower.includes('insufficient funds') ||
    titleLower.includes('transaction history') ||
    titleLower.includes('timeout') ||
    titleLower.includes('appointment booking') ||
    titleLower.includes('medical form') ||
    titleLower.includes('job application') ||
    titleLower.includes('resume upload') ||
    titleLower.includes('candidate status') ||
    titleLower.includes('duplicate-application') ||
    titleLower.includes('leave request') ||
    titleLower.includes('payroll') ||
    titleLower.includes('user invite') ||
    titleLower.includes('settings persistence') ||
    titleLower.includes('subscription');
    
  if (isIndustryJourney) {
    return 'Industry Flow';
  }
  return 'Generic';
};

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
  const [selectedModel, setSelectedModel] = useState('auto');
  const [categoryFilter, setCategoryFilter] = useState<'All' | 'Generic' | 'Industry Flow' | 'Access Control'>('All');

  // Manual & Bulk Test Case Management
  const [showModal, setShowModal] = useState(false);
  const [showBulkModal, setShowBulkModal] = useState(false);
  const [editingTestCase, setEditingTestCase] = useState<TestCase | null>(null);

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

  const handleValidateTest = async (testCaseId: number) => {
    setValidatingIds(prev => ({ ...prev, [testCaseId]: true }));
    setError('');
    setSuccessMsg('');
    try {
      const response = await api.post(`test-cases/${testCaseId}/validate_test/`);
      setValidationResults(prev => ({ ...prev, [testCaseId]: response.data }));
      setSuccessMsg(`Validation completed: ${response.data.status}`);
      onRefreshTests();
    } catch (err: any) {
      console.error(err);
      setError('Failed to validate test case selector integrity.');
    } finally {
      setValidatingIds(prev => ({ ...prev, [testCaseId]: false }));
    }
  };

  const handleAutoFixTest = async (testCaseId: number) => {
    setFixingIds(prev => ({ ...prev, [testCaseId]: true }));
    setError('');
    setSuccessMsg('');
    try {
      const response = await api.post(`test-cases/${testCaseId}/auto_fix/`);
      setSuccessMsg(`Auto-fix applied! Repaired ${response.data.fixed_count || 0} selector(s).`);
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
    
    const initialRuns = testCases.map(tc => ({
      id: Date.now() + tc.id,
      testCaseId: tc.id,
      title: tc.title,
      status: 'PENDING'
    }));
    setSuiteRuns(initialRuns);
    setSuiteRunStartTime(Date.now());
    setShowSuiteProgress(true);

    try {
      const testCaseIds = testCases.map(tc => tc.id);
      const response = await api.post('test-runs/execute_batch/', { test_case_ids: testCaseIds, model_choice: selectedModel });
      
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
      if (runs.length > 0) {
        onTestExecuted(runs[0].id, runs[0].task_id);
      }
      setSuccessMsg(`Queued all ${testCases.length} tests for execution.`);
    } catch (err: any) {
      console.error(err);
      setError('Failed to run all test cases.');
      setShowSuiteProgress(false);
      setSuiteRuns([]);
    } finally {
      setExecutingAll(false);
    }
  };

  const handleAddManual = () => {
    setEditingTestCase(null);
    setShowModal(true);
  };

  const handleEdit = (tc: TestCase) => {
    setEditingTestCase(tc);
    setShowModal(true);
  };

  const handleDelete = async (id: number) => {
    if (!window.confirm('Are you sure you want to delete this test case?')) return;
    try {
      await api.delete(`test-cases/${id}/`);
      setSuccessMsg('Test case deleted successfully.');
      onRefreshTests();
    } catch (err: any) {
      console.error(err);
      setError('Failed to delete test case.');
    }
  };

  const handleGenerateTests = async () => {
    setGenerating(true);
    setError('');
    setSuccessMsg('');
    try {
      const res = await api.post('test-cases/generate/', { app_id: appId, model_choice: selectedModel });
      setSuccessMsg('AI Test suite generation started...');
      if (res.data.task_id && onTaskTriggered) {
        onTaskTriggered(res.data.task_id);
      }
    } catch (err: any) {
      console.error(err);
      setError('Failed to trigger AI test case generation.');
      setGenerating(false);
    }
  };

  const handleStopGeneration = async () => {
    try {
      await api.post(`applications/${appId}/stop-all/`);
      setGenerating(false);
      setSuccessMsg('All tasks stopped.');
      onRefreshTests();
    } catch (err) {
      console.error('Failed to stop tasks:', err);
      setError('Failed to stop the tasks.');
    }
  };

  const handleRunTest = async (testCaseId: number) => {
    setExecutingTestCaseId(testCaseId);
    setError('');
    const tc = testCases.find(t => t.id === testCaseId);
    const tempRunId = Date.now();
    setSuiteRuns([{
      id: tempRunId,
      testCaseId: testCaseId,
      title: tc?.title || `Test Case #${testCaseId}`,
      status: 'PENDING'
    }]);
    setSuiteRunStartTime(Date.now());
    setShowSuiteProgress(true);

    try {
      const response = await api.post('test-runs/execute/', { test_case_id: testCaseId, model_choice: selectedModel });
      setSuccessMsg(`Test run execution started.`);
      if (response.data.task_id && onTaskTriggered) {
        onTaskTriggered(response.data.task_id);
      }
      onTestExecuted(response.data.test_run_id, response.data.task_id);
    } catch (err: any) {
      console.error(err);
      setError('Failed to execute test run.');
      setShowSuiteProgress(false);
    } finally {
      setExecutingTestCaseId(null);
    }
  };

  const getStepActionClass = (action: string) => {
    switch (action.toLowerCase()) {
      case 'navigate': return 'step-action-navigate';
      case 'click': return 'step-action-click';
      case 'fill': return 'step-action-fill';
      case 'wait': return 'step-action-wait';
      case 'assert': return 'step-action-assert';
      default: return 'step-action-badge';
    }
  };

  return (
    <div className="glass-card test-cases-card animate-slide-up" style={{ padding: '24px' }}>
      {/* Tier 1 Header: Title & AI Actions */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '16px', marginBottom: '20px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <h3 style={{ margin: 0, fontSize: '1.25rem', fontWeight: 700 }}>📋 AI-Generated Test Suite</h3>
            <span style={{
              fontSize: '0.75rem',
              fontWeight: 700,
              padding: '3px 10px',
              borderRadius: '20px',
              backgroundColor: 'rgba(139, 92, 246, 0.15)',
              color: '#c084fc',
              border: '1px solid rgba(139, 92, 246, 0.3)'
            }}>
              {testCases.length} Scenarios
            </span>
          </div>
          <p className="card-subtitle" style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginTop: '4px' }}>
            Automated test scenarios synthesized from discovered page forms, buttons, and user journeys
          </p>
        </div>

        <div style={{ display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap' }}>
          <select 
            value={selectedModel}
            onChange={(e) => setSelectedModel(e.target.value)}
            disabled={generating || !!activeTaskId}
            style={{
              backgroundColor: 'rgba(11, 8, 22, 0.6)',
              color: '#ffffff',
              border: '1px solid rgba(255, 255, 255, 0.15)',
              padding: '9px 12px',
              borderRadius: '8px',
              cursor: 'pointer',
              fontWeight: 600,
              fontSize: '0.82rem',
              outline: 'none'
            }}
          >
            <option value="auto">Auto-Select LLM Router</option>
            <option value="ollama_qwen">Ollama / Qwen (Local)</option>
            <option value="ollama_groq">Ollama / Groq (Local)</option>
            <option value="openai">ChatGPT / OpenAI (Cloud)</option>
          </select>

          <button 
            onClick={handleGenerateTests} 
            disabled={generating || !!activeTaskId} 
            className="btn-primary"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '9px 16px',
              borderRadius: '8px',
              fontWeight: 600,
              fontSize: '0.85rem'
            }}
          >
            {generating ? (
              <>
                <div className="spinner-small"></div>
                <span>Generating Suite...</span>
              </>
            ) : (
              '✨ Generate Tests with AI'
            )}
          </button>

          {testCases.length > 0 && (
            <button 
              onClick={handleRunAllTests} 
              disabled={executingAll || !!activeTaskId} 
              style={{
                backgroundColor: '#10b981',
                color: '#ffffff',
                border: 'none',
                padding: '9px 16px',
                borderRadius: '8px',
                cursor: 'pointer',
                fontWeight: 600,
                fontSize: '0.85rem',
                display: 'flex',
                alignItems: 'center',
                gap: '6px'
              }}
            >
              {executingAll ? 'Executing Batch...' : '▶ Run All Tests'}
            </button>
          )}

          {(generating || activeTaskId) && (
            <button 
              onClick={handleStopGeneration} 
              style={{
                backgroundColor: 'rgba(239, 68, 68, 0.2)',
                color: '#ff8888',
                border: '1px solid rgba(239, 68, 68, 0.4)',
                padding: '9px 14px',
                borderRadius: '8px',
                cursor: 'pointer',
                fontWeight: 600,
                fontSize: '0.82rem'
              }}
            >
              🛑 Stop
            </button>
          )}
        </div>
      </div>

      {/* Tier 2 Header: Category Filter & Manual Action */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        paddingTop: '14px',
        borderTop: '1px solid rgba(255, 255, 255, 0.08)',
        marginBottom: '20px',
        flexWrap: 'wrap',
        gap: '12px'
      }}>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontWeight: 600, marginRight: '4px' }}>CATEGORY:</span>
          {(['All', 'Generic', 'Industry Flow', 'Access Control'] as const).map((cat) => (
            <button
              key={cat}
              onClick={() => setCategoryFilter(cat)}
              style={{
                backgroundColor: categoryFilter === cat ? '#3b82f6' : 'rgba(255, 255, 255, 0.04)',
                color: categoryFilter === cat ? '#fff' : 'var(--text-muted)',
                border: `1px solid ${categoryFilter === cat ? '#3b82f6' : 'rgba(255, 255, 255, 0.08)'}`,
                padding: '5px 12px',
                borderRadius: '20px',
                cursor: 'pointer',
                fontSize: '0.78rem',
                fontWeight: 600,
                transition: 'all 0.2s'
              }}
            >
              {cat}
            </button>
          ))}
        </div>

        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <button 
            onClick={() => setShowBulkModal(true)} 
            style={{
              backgroundColor: 'rgba(16, 185, 129, 0.12)',
              color: '#34d399',
              border: '1px solid rgba(16, 185, 129, 0.3)',
              padding: '6px 14px',
              borderRadius: '8px',
              cursor: 'pointer',
              fontWeight: 600,
              fontSize: '0.8rem',
              display: 'flex',
              alignItems: 'center',
              gap: '6px'
            }}
          >
            📁 Bulk Upload
          </button>
          <button 
            onClick={handleAddManual} 
            style={{
              backgroundColor: 'rgba(59, 130, 246, 0.12)',
              color: '#60a5fa',
              border: '1px solid rgba(59, 130, 246, 0.3)',
              padding: '6px 14px',
              borderRadius: '8px',
              cursor: 'pointer',
              fontWeight: 600,
              fontSize: '0.8rem',
              display: 'flex',
              alignItems: 'center',
              gap: '6px'
            }}
          >
            ➕ Add Manual Test
          </button>
        </div>
      </div>

      {error && <div className="error-alert">{error}</div>}
      {successMsg && (
        <div className="success-alert" style={{
          backgroundColor: 'rgba(16, 185, 129, 0.18)',
          color: '#6ee7b7',
          border: '1px solid rgba(16, 185, 129, 0.4)',
          padding: '12px 18px',
          borderRadius: '10px',
          marginBottom: '20px',
          fontSize: '0.92rem',
          fontWeight: '600',
          display: 'flex',
          alignItems: 'center',
          gap: '10px',
          boxShadow: '0 4px 20px rgba(16, 185, 129, 0.15)'
        }}>
          <span style={{ fontSize: '1.2rem' }}>🎉</span>
          <span>{successMsg}</span>
        </div>
      )}

      {/* Test Cases Cards List */}
      {testCases.length === 0 ? (
        <div className="empty-state-card">
          <svg className="empty-state-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ color: '#8b5cf6' }}>
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
            <polyline points="14 2 14 8 20 8"></polyline>
            <line x1="16" y1="13" x2="8" y2="13"></line>
            <line x1="16" y1="17" x2="8" y2="17"></line>
            <polyline points="10 9 9 9 8 9"></polyline>
          </svg>
          <h4 className="empty-state-title">No Test Scenarios Generated Yet</h4>
          <p className="empty-state-desc">
            Click "Generate Tests with AI" above to synthesize complete test suites using discovered site structures.
          </p>
          <button onClick={handleGenerateTests} className="btn-primary" style={{ padding: '8px 20px' }}>
            ✨ Generate Tests with AI
          </button>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {(() => {
            const filtered = testCases.filter(tc => {
              if (categoryFilter === 'All') return true;
              return getTestCategory(tc) === categoryFilter;
            });

            if (filtered.length === 0) {
              return (
                <div style={{ padding: '32px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.9rem' }}>
                  No test scenarios match the selected category filter "{categoryFilter}".
                </div>
              );
            }

            return filtered.map((tc) => {
              const tcValResults = validationResults[tc.id];
              const category = getTestCategory(tc);
              const isVerified = tc.validation_status === 'VERIFIED';
              const isBroken = tc.validation_status === 'BROKEN';

              return (
                <div 
                  key={tc.id} 
                  style={{
                    background: 'rgba(11, 8, 22, 0.45)',
                    border: '1px solid rgba(255, 255, 255, 0.08)',
                    borderRadius: '12px',
                    padding: '20px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '16px',
                    transition: 'all 0.2s ease'
                  }}
                >
                  {/* Card Header Top Row: Title, Badges & Action Toolbar */}
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '12px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
                      <h4 style={{ margin: 0, fontSize: '1.05rem', fontWeight: 700, color: '#fff' }}>{tc.title}</h4>
                      
                      {category === 'Access Control' && (
                        <span style={{ padding: '2px 8px', borderRadius: '12px', fontSize: '0.7rem', fontWeight: 600, backgroundColor: 'rgba(239, 68, 68, 0.15)', color: '#f87171', border: '1px solid rgba(239, 68, 68, 0.3)' }}>
                          Access Control
                        </span>
                      )}
                      {category === 'Industry Flow' && (
                        <span style={{ padding: '2px 8px', borderRadius: '12px', fontSize: '0.7rem', fontWeight: 600, backgroundColor: 'rgba(59, 130, 246, 0.15)', color: '#60a5fa', border: '1px solid rgba(59, 130, 246, 0.3)' }}>
                          Industry Flow
                        </span>
                      )}

                      <span className="model-badge model-gpt">
                        🤖 {tc.ai_generated ? (tc.model_used || 'AI Generated') : 'Manual'}
                      </span>

                      <span style={{
                        padding: '2px 8px', borderRadius: '12px', fontSize: '0.7rem', fontWeight: 600,
                        backgroundColor: isVerified ? 'rgba(16, 185, 129, 0.15)' : isBroken ? 'rgba(239, 68, 68, 0.15)' : 'rgba(156, 163, 175, 0.12)',
                        color: isVerified ? '#34d399' : isBroken ? '#f87171' : '#9ca3af',
                        border: `1px solid ${isVerified ? 'rgba(16, 185, 129, 0.3)' : isBroken ? 'rgba(239, 68, 68, 0.3)' : 'rgba(156, 163, 175, 0.25)'}`
                      }}>
                        {isVerified ? '✓ Verified' : isBroken ? '⚠️ Broken' : 'Draft (Unverified)'}
                      </span>
                    </div>

                    {/* Sleek Horizontal Action Toolbar */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <button 
                        onClick={() => handleRunTest(tc.id)} 
                        disabled={executingTestCaseId === tc.id || !!activeTaskId}
                        style={{
                          backgroundColor: '#10b981',
                          color: '#fff',
                          border: 'none',
                          padding: '6px 14px',
                          borderRadius: '6px',
                          fontWeight: 600,
                          fontSize: '0.8rem',
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '4px'
                        }}
                      >
                        {executingTestCaseId === tc.id ? 'Running...' : '▶ Run'}
                      </button>
                      
                      <button 
                        onClick={() => handleValidateTest(tc.id)} 
                        disabled={validatingIds[tc.id] || fixingIds[tc.id] || !!activeTaskId}
                        style={{ 
                          padding: '6px 12px',
                          fontSize: '0.78rem',
                          backgroundColor: 'rgba(255, 255, 255, 0.05)',
                          color: '#d1d5db',
                          border: '1px solid rgba(255, 255, 255, 0.12)',
                          borderRadius: '6px',
                          cursor: 'pointer',
                          fontWeight: 600
                        }}
                      >
                        {validatingIds[tc.id] ? 'Verifying...' : '🔍 Validate'}
                      </button>

                      {!isVerified && (
                        <button 
                          onClick={() => handleAutoFixTest(tc.id)} 
                          disabled={validatingIds[tc.id] || fixingIds[tc.id] || !!activeTaskId}
                          style={{ 
                            padding: '6px 12px',
                            fontSize: '0.78rem',
                            backgroundColor: 'rgba(139, 92, 246, 0.15)',
                            color: '#c084fc',
                            border: '1px solid rgba(139, 92, 246, 0.3)',
                            borderRadius: '6px',
                            cursor: 'pointer',
                            fontWeight: 600
                          }}
                        >
                          {fixingIds[tc.id] ? 'Fixing...' : '🪄 Auto-Fix'}
                        </button>
                      )}
                      
                      <button 
                        onClick={() => handleEdit(tc)} 
                        disabled={!!activeTaskId}
                        style={{ 
                          padding: '6px 10px',
                          fontSize: '0.78rem',
                          backgroundColor: 'transparent',
                          color: '#a5b4fc',
                          border: '1px solid rgba(165, 180, 252, 0.25)',
                          borderRadius: '6px',
                          cursor: 'pointer'
                        }}
                      >
                        ✏️ Edit
                      </button>

                      <button 
                        onClick={() => handleDelete(tc.id)} 
                        disabled={!!activeTaskId}
                        style={{ 
                          padding: '6px 10px',
                          fontSize: '0.78rem',
                          backgroundColor: 'rgba(239, 68, 68, 0.1)',
                          color: '#ef4444',
                          border: '1px solid rgba(239, 68, 68, 0.25)',
                          borderRadius: '6px',
                          cursor: 'pointer'
                        }}
                      >
                        🗑️
                      </button>
                    </div>
                  </div>

                  {/* Step Timeline List */}
                  <div style={{
                    background: 'rgba(0, 0, 0, 0.3)',
                    borderRadius: '8px',
                    padding: '14px 16px',
                    border: '1px solid rgba(255, 255, 255, 0.04)'
                  }}>
                    <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 700, letterSpacing: '0.5px' }}>
                      STEPS ({tc.steps.length}):
                    </span>
                    <ol style={{ listStyle: 'none', padding: 0, margin: '10px 0 0 0', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                      {tc.steps.map((step, idx) => {
                        const stepDetails = tcValResults?.steps?.find((s: any) => s.step_index === idx);
                        const isInvalid = stepDetails && !stepDetails.valid;
                        
                        return (
                          <li key={idx} style={{ 
                            fontSize: '0.82rem',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '10px',
                            color: isInvalid ? '#ff4d4d' : '#e5e7eb'
                          }}>
                            <span style={{
                              width: '20px', height: '20px', borderRadius: '50%',
                              backgroundColor: 'rgba(255, 255, 255, 0.06)',
                              fontSize: '0.7rem', fontWeight: 700, color: 'var(--text-muted)',
                              display: 'flex', alignItems: 'center', justifyContent: 'center'
                            }}>
                              {idx + 1}
                            </span>

                            <span className={`step-action-badge ${getStepActionClass(step.action)}`}>
                              {step.action.toUpperCase()}
                            </span>

                            <span style={{ flex: 1 }}>
                              {step.action === 'navigate' && <> to <code className="step-code">{step.target}</code></>}
                              {step.action === 'fill' && <> field <code className="step-code">{step.selector}</code> with <code className="step-code">"{step.value}"</code></>}
                              {step.action === 'click' && <> element <code className="step-code">{step.selector}</code></>}
                              {step.action === 'wait' && <> for <code className="step-code">{step.value} ms</code></>}
                              {step.action === 'assert' && <> element <code className="step-code">{step.selector || 'body'}</code> contains text <code className="step-code">"{step.value}"</code></>}
                            </span>

                            {isInvalid && (
                              <span style={{ fontSize: '0.78rem', color: '#ff6666' }}>
                                ({stepDetails.reason})
                              </span>
                            )}
                          </li>
                        );
                      })}
                    </ol>
                  </div>

                  <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                    <strong style={{ color: '#d1d5db' }}>Expected Outcome:</strong> {tc.expected_result}
                  </div>
                </div>
              );
            });
          })()}
        </div>
      )}

      {showModal && (
        <TestCaseFormModal
          appId={appId}
          testCase={editingTestCase}
          onClose={() => setShowModal(false)}
          onSuccess={() => {
            setShowModal(false);
            setSuccessMsg(`Test case ${editingTestCase ? 'updated' : 'created'} successfully.`);
            onRefreshTests();
          }}
        />
      )}

      {showBulkModal && (
        <BulkUploadModal
          appId={appId}
          onClose={() => setShowBulkModal(false)}
          onSuccess={(msg) => {
            setShowBulkModal(false);
            setSuccessMsg(msg || '🎉 Bulk test cases imported successfully! Your test cases are ready below in the Test Suite.');
            onRefreshTests();
          }}
        />
      )}
    </div>
  );
};
