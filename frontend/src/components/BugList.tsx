import React, { useState } from 'react';
import { Bug } from '../lib/types';

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

  const toggleExpandBug = (id: number) => {
    setSelectedBugId(selectedBugId === id ? null : id);
  };

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

      {bugs.length === 0 ? (
        <div className="empty-state">
          <div className="bug-free-icon">🛡️</div>
          <p>Zero bugs detected so far! Your site is healthy or tests have not failed.</p>
        </div>
      ) : (
        <div className="bugs-table-container">
          <div className="bugs-list">
            {bugs.map((bug) => {
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
                      
                      <div className="repro-section">
                        <h6>Test Run Details:</h6>
                        <p>
                          <strong>Failed Test Case:</strong> {bug.test_case_title}<br />
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
