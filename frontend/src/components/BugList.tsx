import React, { useState } from 'react';
import { Bug } from '../lib/types';
import api from '../lib/api';

interface BugListProps {
  bugs: Bug[];
  onRefreshBugs?: () => void;
  onRunTestCase?: (testCaseId: number) => void;
  activeTaskId?: string | null;
}

export const BugList: React.FC<BugListProps> = ({ 
  bugs, 
  onRefreshBugs,
  onRunTestCase,
  activeTaskId
}) => {
  const [selectedBugId, setSelectedBugId] = useState<number | null>(null);
  const [filterSeverity, setFilterSeverity] = useState<string>('all');
  const [filterType, setFilterType] = useState<string>('all');
  const [filterStatus, setFilterStatus] = useState<string>('all');

  const toggleExpandBug = (id: number) => {
    setSelectedBugId(selectedBugId === id ? null : id);
  };

  const filteredBugs = bugs.filter(b => {
    const matchSeverity = filterSeverity === 'all' || b.severity.toLowerCase() === filterSeverity.toLowerCase();
    const matchType = filterType === 'all' || (b.bug_type && b.bug_type.toLowerCase() === filterType.toLowerCase());
    const matchStatus = filterStatus === 'all' || (b.status && b.status.toLowerCase() === filterStatus.toLowerCase());
    return matchSeverity && matchType && matchStatus;
  });

  return (
    <div className="glass-card bug-list-card">
      <div className="card-header bugs-header">
        <div>
          <h3>🐞 Bug and Defect Registry</h3>
          <p className="card-subtitle">AI-classified functional and presentation errors discovered during automation</p>
        </div>
        {onRefreshBugs && (
          <button onClick={onRefreshBugs} className="btn-secondary btn-refresh">
            🔄 Refresh Registry
          </button>
        )}
      </div>

      {/* Filters Panel */}
      <div className="bugs-filters-panel" style={{
        display: 'flex',
        gap: '16px',
        padding: '16px',
        background: 'rgba(255, 255, 255, 0.02)',
        borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
        marginBottom: '12px',
        alignItems: 'center',
        flexWrap: 'wrap'
      }}>
        <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'rgba(255, 255, 255, 0.6)' }}>Filters:</span>
        
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
          <label style={{ fontSize: '0.7rem', color: 'rgba(255, 255, 255, 0.4)', textTransform: 'uppercase' }}>Severity</label>
          <select 
            value={filterSeverity} 
            onChange={(e) => setFilterSeverity(e.target.value)}
            style={{
              background: 'rgba(20, 20, 30, 0.7)',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              borderRadius: '6px',
              color: '#fff',
              padding: '6px 12px',
              fontSize: '0.85rem'
            }}
          >
            <option value="all">All Severities</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
          <label style={{ fontSize: '0.7rem', color: 'rgba(255, 255, 255, 0.4)', textTransform: 'uppercase' }}>Bug Type</label>
          <select 
            value={filterType} 
            onChange={(e) => setFilterType(e.target.value)}
            style={{
              background: 'rgba(20, 20, 30, 0.7)',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              borderRadius: '6px',
              color: '#fff',
              padding: '6px 12px',
              fontSize: '0.85rem'
            }}
          >
            <option value="all">All Types</option>
            <option value="functional">Functional</option>
            <option value="ui">UI/Layout</option>
            <option value="permission">Permission</option>
            <option value="workflow">Workflow</option>
          </select>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
          <label style={{ fontSize: '0.7rem', color: 'rgba(255, 255, 255, 0.4)', textTransform: 'uppercase' }}>Status</label>
          <select 
            value={filterStatus} 
            onChange={(e) => setFilterStatus(e.target.value)}
            style={{
              background: 'rgba(20, 20, 30, 0.7)',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              borderRadius: '6px',
              color: '#fff',
              padding: '6px 12px',
              fontSize: '0.85rem'
            }}
          >
            <option value="all">All Statuses</option>
            <option value="open">Open</option>
            <option value="confirmed">Confirmed</option>
            <option value="resolved">Resolved</option>
          </select>
        </div>
      </div>

      {filteredBugs.length === 0 ? (
        <div className="empty-state">
          <div className="bug-free-icon">🛡️</div>
          <p>Zero bugs match the selected filters.</p>
        </div>
      ) : (
        <div className="bugs-table-container">
          <div className="bugs-list">
            {filteredBugs.map((bug) => {
              const isExpanded = selectedBugId === bug.id;
              return (
                <div 
                  key={bug.id} 
                  className={`bug-item severity-${bug.severity} ${isExpanded ? 'expanded' : ''}`}
                >
                  <div className="bug-item-summary" onClick={() => toggleExpandBug(bug.id)}>
                    <div className="bug-info-block">
                      <span className={`badge-severity severity-${bug.severity}`}>
                        {bug.severity.toUpperCase()}
                      </span>
                      <span className="bug-title">{bug.title}</span>
                    </div>
                    
                    <div className="bug-metadata-block" onClick={(e) => e.stopPropagation()}>
                      <span className="bug-app-url">{bug.app_url}</span>
                      
                      {bug.test_case_id && onRunTestCase && (
                        <button
                          onClick={() => onRunTestCase(bug.test_case_id!)}
                          disabled={!!activeTaskId}
                          className="btn-run-test btn-bug-rerun"
                          title="Run Associated Test Case"
                          style={{
                            background: '#dc2626',
                            color: '#fff',
                            border: 'none',
                            padding: '6px 12px',
                            borderRadius: '6px',
                            cursor: 'pointer',
                            fontSize: '0.8rem',
                            fontWeight: '600',
                            marginRight: '12px',
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '4px',
                            transition: 'all 0.2s'
                          }}
                        >
                          ▶ Run Test
                        </button>
                      )}
                      
                      <button 
                        onClick={() => toggleExpandBug(bug.id)}
                        className="btn-bug-expand-toggle"
                        style={{
                          background: 'rgba(255, 255, 255, 0.05)',
                          border: '1px solid var(--border-glass)',
                          color: 'var(--text-primary)',
                          borderRadius: '6px',
                          cursor: 'pointer',
                          padding: '6px 12px',
                          fontSize: '0.8rem',
                          fontWeight: '500',
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '4px'
                        }}
                      >
                        {isExpanded ? 'Collapse ˄' : 'Expand ˅'}
                      </button>
                    </div>
                  </div>

                  {isExpanded && (
                    <div className="bug-item-description">
                      <div className="desc-section">
                        <h6>Description & Trace:</h6>
                        <pre className="desc-text">{bug.description}</pre>
                      </div>
                      
                      {/* Step Execution Timeline */}
                      {bug.test_case_steps && bug.test_case_steps.length > 0 && (
                        <div className="bug-steps-timeline" style={{ marginTop: '20px', marginBottom: '20px' }}>
                          <h6 style={{ color: 'var(--text-primary)', marginBottom: '10px', fontSize: '0.9rem', fontWeight: '600' }}>
                            📋 Test Execution Steps & Timeline:
                          </h6>
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                            {bug.test_case_steps.map((step, idx) => {
                              const stepNum = idx + 1;
                              const stepResult = bug.test_run_results?.find(r => r.step_number === stepNum);
                              const isFailed = stepResult?.status === 'FAILED';
                              const isPassed = stepResult?.status === 'PASSED';
                              
                              let stepColor = 'rgba(255, 255, 255, 0.4)';
                              let stepBg = 'rgba(255, 255, 255, 0.02)';
                              let stepBorder = 'rgba(255, 255, 255, 0.08)';
                              let statusIcon = '⚪';
                              
                              if (isPassed) {
                                stepColor = '#10b981';
                                stepBg = 'rgba(16, 185, 129, 0.04)';
                                stepBorder = 'rgba(16, 185, 129, 0.15)';
                                statusIcon = '✅';
                              } else if (isFailed) {
                                stepColor = '#ff4d4d';
                                stepBg = 'rgba(255, 77, 77, 0.06)';
                                stepBorder = 'rgba(255, 77, 77, 0.25)';
                                statusIcon = '❌';
                              }

                              const actionStr = step.action.toUpperCase();
                              let details = '';
                              if (step.action === 'navigate') details = `to ${step.target}`;
                              else if (step.action === 'fill') details = `selector '${step.selector}' with '${step.value}'`;
                              else if (step.action === 'click') details = `selector '${step.selector}'`;
                              else if (step.action === 'wait') details = `for ${step.value}ms`;
                              else if (step.action === 'assert') details = `selector '${step.selector || 'body'}' contains '${step.value}'`;
                              else if (step.action === 'hover') details = `selector '${step.selector}'`;
                              else if (step.action === 'scroll') details = step.selector ? `selector '${step.selector}' into view` : `down by ${step.value}px`;
                              else if (step.action === 'select') details = `selector '${step.selector}' option '${step.value}'`;
                              else if (step.action === 'screenshot') details = step.value ? `label: '${step.value}'` : '';

                              return (
                                <div 
                                  key={idx}
                                  style={{
                                    display: 'flex',
                                    flexDirection: 'column',
                                    padding: '12px',
                                    background: stepBg,
                                    border: `1px solid ${stepBorder}`,
                                    borderRadius: '8px',
                                    color: stepColor,
                                    gap: '6px'
                                  }}
                                >
                                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontWeight: '600', fontSize: '0.85rem' }}>
                                    <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                                      {statusIcon} Step {stepNum}: {actionStr}
                                    </span>
                                    <span style={{ fontSize: '0.78rem', opacity: 0.8, color: 'rgba(255, 255, 255, 0.55)', fontFamily: 'monospace' }}>
                                      {details}
                                    </span>
                                  </div>
                                  {isFailed && stepResult?.error && (
                                    <div style={{
                                      marginTop: '6px',
                                      padding: '10px',
                                      background: 'rgba(0, 0, 0, 0.45)',
                                      borderRadius: '6px',
                                      fontFamily: 'Consolas, Monaco, monospace',
                                      fontSize: '0.8rem',
                                      color: '#ff8888',
                                      whiteSpace: 'pre-wrap',
                                      wordBreak: 'break-word',
                                      borderLeft: '3px solid #ff4d4d',
                                      boxShadow: 'inset 0 1px 4px rgba(0,0,0,0.5)'
                                    }}>
                                      {stepResult.error}
                                    </div>
                                  )}
                                  {isFailed && stepResult?.screenshot && (
                                    <div style={{ marginTop: '10px' }}>
                                      <span style={{ display: 'block', fontSize: '0.72rem', color: 'rgba(255, 255, 255, 0.4)', marginBottom: '4px', textTransform: 'uppercase' }}>
                                        📸 Failure Screenshot:
                                      </span>
                                      <img 
                                        src={(() => {
                                          const ss = stepResult.screenshot;
                                          const origin = api.defaults.baseURL?.replace('/api/', '') || 'http://127.0.0.1:8000';
                                          // Long strings are base64; short strings are file paths
                                          if (ss.length > 500) return `data:image/png;base64,${ss}`;
                                          if (ss.startsWith('http')) return ss;
                                          if (ss.startsWith('/')) return `${origin}${ss}`;
                                          return `${origin}/media/${ss}`;
                                        })()} 
                                        alt={`Step ${stepNum} Failure Screenshot`}
                                        style={{
                                          maxWidth: '100%',
                                          maxHeight: '300px',
                                          borderRadius: '6px',
                                          border: '1px solid rgba(255, 255, 255, 0.15)',
                                          boxShadow: '0 4px 16px rgba(0, 0, 0, 0.6)'
                                        }}
                                      />
                                    </div>
                                  )}
                                </div>
                              );
                            })}

                            {/* Render background verification or API failures listed as extra steps */}
                            {bug.test_run_results?.filter(r => r.step_number > bug.test_case_steps!.length).map((result, idx) => (
                              <div 
                                key={`extra-${idx}`}
                                style={{
                                  display: 'flex',
                                  flexDirection: 'column',
                                  padding: '12px',
                                  background: 'rgba(255, 77, 77, 0.05)',
                                  border: '1px solid rgba(255, 77, 77, 0.25)',
                                  borderRadius: '8px',
                                  color: '#ff4d4d',
                                  gap: '4px'
                                }}
                              >
                                <div style={{ fontWeight: '600', fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '6px' }}>
                                  ❌ Background Quality Verification failure
                                </div>
                                <div style={{
                                  marginTop: '6px',
                                  padding: '10px',
                                  background: 'rgba(0, 0, 0, 0.45)',
                                  borderRadius: '6px',
                                  fontFamily: 'Consolas, Monaco, monospace',
                                  fontSize: '0.8rem',
                                  color: '#ff8888',
                                  whiteSpace: 'pre-wrap',
                                  wordBreak: 'break-word',
                                  borderLeft: '3px solid #ff4d4d',
                                  boxShadow: 'inset 0 1px 4px rgba(0,0,0,0.5)'
                                }}>
                                  {result.error}
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                      
                      {bug.steps_to_reproduce && bug.steps_to_reproduce.length > 0 && (
                        <div className="repro-steps-section" style={{ marginTop: '16px', marginBottom: '16px' }}>
                          <h6 style={{ color: 'var(--text-primary)', marginBottom: '8px', fontSize: '0.9rem', fontWeight: '600' }}>
                            📝 Steps to Reproduce:
                          </h6>
                          <ol style={{ margin: '4px 0 0 16px', padding: 0, fontSize: '0.85rem', color: 'rgba(255,255,255,0.7)', listStyleType: 'decimal' }}>
                            {bug.steps_to_reproduce.map((step, sIdx) => (
                              <li key={sIdx} style={{ marginBottom: '4px' }}>{step}</li>
                            ))}
                          </ol>
                        </div>
                      )}

                      {bug.screenshot && (
                        <div className="bug-screenshot-gallery" style={{ marginTop: '16px', marginBottom: '16px' }}>
                          <h6 style={{ color: 'var(--text-primary)', marginBottom: '8px', fontSize: '0.9rem', fontWeight: '600' }}>
                            📸 Captured Bug Screenshot:
                          </h6>
                          <img 
                            src={(() => {
                              const ss = bug.screenshot;
                              const origin = api.defaults.baseURL?.replace('/api/', '') || 'http://127.0.0.1:8000';
                              // Already a full absolute URL (DRF returns full URL when request context is set)
                              if (ss.startsWith('http')) return ss;
                              // Starts with /media/ or / — prepend origin only
                              if (ss.startsWith('/')) return `${origin}${ss}`;
                              // Relative path like 'bugs/xxx.png' — add /media/ prefix
                              return `${origin}/media/${ss}`;
                            })()} 
                            alt="Captured Bug Screenshot" 
                            style={{
                              maxWidth: '100%',
                              maxHeight: '400px',
                              borderRadius: '8px',
                              border: '1px solid rgba(255, 255, 255, 0.15)',
                              boxShadow: '0 4px 16px rgba(0, 0, 0, 0.6)'
                            }}
                          />
                        </div>
                      )}

                      <div className="repro-section">
                        <h6>Bug Details:</h6>
                        <p>
                          {bug.test_case_title && <><strong>Failed Test Case:</strong> {bug.test_case_title}<br /></>}
                          {bug.bug_type && <><strong>Type:</strong> <span style={{ textTransform: 'capitalize' }}>{bug.bug_type}</span><br /></>}
                          {bug.status && <><strong>Status:</strong> <span style={{ color: '#60a5fa', fontWeight: 'bold' }}>{bug.status.toUpperCase()}</span><br /></>}
                          <strong>Logged on:</strong> {new Date(bug.created_at).toLocaleString()}
                        </p>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};
