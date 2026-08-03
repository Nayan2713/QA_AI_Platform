// frontend/src/components/QualityDashboard/QualityDashboard.tsx
// Complete React component for quality metrics display

import React, { useState, useEffect } from 'react';
import api from '../../lib/api';
import { LineChart, Line, BarChart, Bar, PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import './QualityDashboard.css';

interface QualityMetrics {
  grade: string;
  score: number;
  recommendations: string[];
}

interface ComponentScores {
  coverage: number;
  reliability: number;
  accuracy: number;
  relevance: number;
}

interface CoverageMetrics {
  page_coverage: number;
  form_coverage: number;
  workflow_coverage: number;
  overall: number;
}

interface ReliabilityMetrics {
  total_flaky_tests: number;
  total_stable_tests: number;
  avg_flakiness: number;
}

interface AccuracyMetrics {
  verified_bugs: number;
  false_positives: number;
  needs_review: number;
}

interface DashboardData {
  application_id: string;
  application_name: string;
  overall_quality: QualityMetrics;
  component_scores: ComponentScores;
  coverage: CoverageMetrics;
  reliability: ReliabilityMetrics;
  accuracy: AccuracyMetrics;
  test_health: {
    relevant_tests: number;
    avg_relevance: number;
  };
  api_health?: {
    total_apis: number;
    endpoints: Array<{
      id: number;
      method: string;
      url_pattern: string;
      bug_count: number;
      avg_latency: number;
      auth_type?: string;
    }>;
  };
}

const QualityDashboard: React.FC<{ applicationId: string }> = ({ applicationId }) => {
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<DashboardData | null>(null);
  
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);
  const [currentTask, setCurrentTask] = useState<any>(null);

  useEffect(() => {
    fetchDashboardData();
  }, [applicationId]);

  // Poll for background quality check status
  useEffect(() => {
    if (!activeTaskId) {
      setCurrentTask(null);
      return;
    }
    
    let isMounted = true;
    let pollCount = 0;
    const MAX_POLLS = 200; // Stop polling after 5 minutes
    
    const fetchTaskStatus = async () => {
      if (!isMounted || pollCount >= MAX_POLLS) return;
      pollCount++;
      
      try {
        const response = await api.get(`tasks/${activeTaskId}/`);
        if (!isMounted) return;
        
        setCurrentTask(response.data);
        
        if (response.data.status === 'success') {
          await fetchDashboardData();
          setActiveTaskId(null);
        } else if (response.data.status === 'failed') {
          setError(response.data.error || 'Full quality check failed');
          setActiveTaskId(null);
        }
      } catch (err) {
        console.error('Failed to poll quality check status:', err);
      }
    };
    
    fetchTaskStatus();
    const intervalId = setInterval(fetchTaskStatus, 1500);
    
    return () => {
      isMounted = false;
      clearInterval(intervalId);
    };
  }, [activeTaskId]);

  const fetchDashboardData = async () => {
    try {
      if (!data) setLoading(true);
      const response = await api.get(
        `quality/quality-dashboard/dashboard/?application_id=${applicationId}`
      );
      setData(response.data);
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.error || 'Failed to fetch quality metrics');
      console.error('Error:', err);
    } finally {
      setLoading(false);
    }
  };

  const runFullCheck = async () => {
    try {
      setRunning(true);
      setError(null);
      const response = await api.post(
        'quality/quality-dashboard/run_full_check/',
        { application_id: applicationId }
      );
      
      if (response.data.task_id) {
        setActiveTaskId(response.data.task_id);
      }
    } catch (err: any) {
      setError(err.response?.data?.error || 'Failed to start quality check');
    } finally {
      setRunning(false);
    }
  };

  if (loading) {
    return <div className="quality-dashboard loading">Loading quality metrics...</div>;
  }

  if (error && !data) {
    return <div className="quality-dashboard error">Error: {error}</div>;
  }

  if (!data) {
    return <div className="quality-dashboard">No data available</div>;
  }

  const gradeColor: { [key: string]: string } = {
    'A': '#10b981',
    'B': '#3b82f6',
    'C': '#f59e0b',
    'D': '#f97316',
    'F': '#ef4444'
  };

  const componentScoresData = [
    { name: 'Coverage', value: data.component_scores.coverage, fill: '#3b82f6' },
    { name: 'Reliability', value: data.component_scores.reliability, fill: '#10b981' },
    { name: 'Accuracy', value: data.component_scores.accuracy, fill: '#f59e0b' },
    { name: 'Relevance', value: data.component_scores.relevance, fill: '#8b5cf6' }
  ];

  const coverageData = [
    { name: 'Pages', coverage: data.coverage.page_coverage },
    { name: 'Forms', coverage: data.coverage.form_coverage },
    { name: 'Workflows', coverage: data.coverage.workflow_coverage }
  ];

  const accuracyData = [
    { name: 'Verified', value: data.accuracy.verified_bugs, fill: '#10b981' },
    { name: 'False Positives', value: data.accuracy.false_positives, fill: '#ef4444' },
    { name: 'Review', value: data.accuracy.needs_review, fill: '#f59e0b' }
  ];

  return (
    <div className="quality-dashboard">
      {/* Header */}
      <div className="dashboard-header">
        <div className="header-content">
          <h1>Quality Dashboard</h1>
          <p className="app-name">{data.application_name}</p>
        </div>
        <button 
          className="run-check-btn" 
          onClick={runFullCheck}
          disabled={running}
        >
          {running ? 'Running...' : 'Run Full Quality Check'}
        </button>
      </div>

      {/* Task Progress Tracker */}
      {currentTask && (
        <div className="glass-card task-progress-tracker" style={{
          margin: '0 0 24px 0',
          padding: '16px 20px',
          border: '1px solid rgba(255, 255, 255, 0.15)',
          background: 'rgba(30, 30, 40, 0.65)',
          backdropFilter: 'blur(16px)',
          borderRadius: '12px',
          boxShadow: '0 8px 32px 0 rgba(0, 0, 0, 0.37)'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
            <span style={{ fontSize: '0.9rem', fontWeight: 'bold', textTransform: 'uppercase', letterSpacing: '0.05em', color: '#a0a0ff' }}>
              ⚙️ Running Quality Audit
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
              {currentTask.result?.status_text || currentTask.error || 'Analyzing quality metrics...'}
            </span>
          </div>
        </div>
      )}

      {/* Overall Quality Score */}
      <div className="overall-score-card">
        <div className="grade-circle" style={{ backgroundColor: gradeColor[data.overall_quality.grade] }}>
          <span className="grade-text">{data.overall_quality.grade}</span>
        </div>
        <div className="score-details">
          <h2>Overall Quality Score</h2>
          <p className="score-value">{data.overall_quality.score.toFixed(1)}/100</p>
          <div className="score-bar">
            <div 
              className="score-fill" 
              style={{ 
                width: `${data.overall_quality.score}%`,
                backgroundColor: gradeColor[data.overall_quality.grade]
              }}
            />
          </div>
        </div>
      </div>

      {/* Component Scores */}
      <div className="component-scores-section">
        <h3>Component Scores</h3>
        <div className="scores-grid">
          {componentScoresData.map((component) => (
            <div key={component.name} className="score-card">
              <h4>{component.name}</h4>
              <div className="score-display">
                <span className="score-number">{component.value.toFixed(0)}%</span>
              </div>
              <div className="mini-bar">
                <div 
                  className="mini-fill" 
                  style={{ 
                    width: `${component.value}%`,
                    backgroundColor: component.fill
                  }}
                />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Charts Section */}
      <div className="charts-section">
        {/* Coverage Chart */}
        <div className="chart-card">
          <h3>Test Coverage</h3>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={coverageData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" />
              <YAxis domain={[0, 100]} />
              <Tooltip />
              <Bar dataKey="coverage" fill="#3b82f6" radius={[8, 8, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Bug Accuracy Pie Chart */}
        <div className="chart-card">
          <h3>Bug Detection Accuracy</h3>
          <ResponsiveContainer width="100%" height={300}>
            <PieChart>
              <Pie
                data={accuracyData}
                cx="50%"
                cy="50%"
                labelLine={false}
                label={({ name, value }) => `${name}: ${value}`}
                outerRadius={100}
                fill="#8884d8"
                dataKey="value"
              >
                {accuracyData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.fill} />
                ))}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Detailed Metrics */}
      <div className="detailed-metrics">
        <div className="metrics-card">
          <h3>📊 Coverage Metrics</h3>
          <div className="metric-item">
            <span>Page Coverage:</span>
            <strong>{data.coverage.page_coverage.toFixed(1)}%</strong>
          </div>
          <div className="metric-item">
            <span>Form Coverage:</span>
            <strong>{data.coverage.form_coverage.toFixed(1)}%</strong>
          </div>
          <div className="metric-item">
            <span>Overall Coverage:</span>
            <strong>{data.coverage.overall.toFixed(1)}%</strong>
          </div>
          <p className="target-note">Target: 80%+</p>
        </div>

        <div className="metrics-card">
          <h3>🔄 Test Reliability</h3>
          <div className="metric-item">
            <span>Stable Tests:</span>
            <strong>{data.reliability.total_stable_tests}</strong>
          </div>
          <div className="metric-item">
            <span>Flaky Tests:</span>
            <strong className="flaky-count">{data.reliability.total_flaky_tests}</strong>
          </div>
          <div className="metric-item">
            <span>Avg Flakiness:</span>
            <strong>{data.reliability.avg_flakiness.toFixed(1)}%</strong>
          </div>
          <p className="target-note">Target: &lt;10% flakiness</p>
        </div>

        <div className="metrics-card">
          <h3>✓ Bug Accuracy</h3>
          <div className="metric-item">
            <span>Verified Bugs:</span>
            <strong className="verified-count">{data.accuracy.verified_bugs}</strong>
          </div>
          <div className="metric-item">
            <span>False Positives:</span>
            <strong className="false-positive-count">{data.accuracy.false_positives}</strong>
          </div>
          <div className="metric-item">
            <span>Needs Review:</span>
            <strong>{data.accuracy.needs_review}</strong>
          </div>
          <p className="target-note">Target: &gt;90% accuracy</p>
        </div>

        <div className="metrics-card">
          <h3>🎯 Test Relevance</h3>
          <div className="metric-item">
            <span>Relevant Tests:</span>
            <strong>{data.test_health.relevant_tests}</strong>
          </div>
          <div className="metric-item">
            <span>Avg Relevance:</span>
            <strong>{data.test_health.avg_relevance.toFixed(1)}%</strong>
          </div>
          <p className="target-note">Target: &gt;80% relevance</p>
        </div>
      </div>

      {/* API catalog list */}
      {data.api_health && data.api_health.endpoints && data.api_health.endpoints.length > 0 && (
        <div className="recommendations-section api-catalog-section" style={{ marginTop: '24px', padding: '20px', background: 'rgba(255, 255, 255, 0.03)', borderRadius: '12px', border: '1px solid rgba(255, 255, 255, 0.1)' }}>
          <h3>🌐 Background API Catalog</h3>
          <div className="table-responsive" style={{ marginTop: '16px', overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', color: '#e2e8f0', fontSize: '0.9rem' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.1)', textAlign: 'left' }}>
                  <th style={{ padding: '12px 8px' }}>Method</th>
                  <th style={{ padding: '12px 8px' }}>URL Pattern</th>
                  <th style={{ padding: '12px 8px' }}>Auth Type</th>
                  <th style={{ padding: '12px 8px' }}>Linked Bugs</th>
                  <th style={{ padding: '12px 8px' }}>Avg Latency</th>
                </tr>
              </thead>
              <tbody>
                {data.api_health.endpoints.map((api: any) => {
                  const getMethodBadgeColor = (m: string) => {
                    switch (m.toUpperCase()) {
                      case 'GET': return '#10b981';
                      case 'POST': return '#3b82f6';
                      case 'PUT': return '#f59e0b';
                      case 'DELETE': return '#ef4444';
                      default: return '#718096';
                    }
                  };
                  return (
                    <tr key={api.id} style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.05)' }}>
                      <td style={{ padding: '10px 8px' }}>
                        <span style={{ 
                          backgroundColor: `${getMethodBadgeColor(api.method)}20`, 
                          color: getMethodBadgeColor(api.method),
                          border: `1px solid ${getMethodBadgeColor(api.method)}40`,
                          padding: '2px 6px',
                          borderRadius: '4px',
                          fontWeight: 'bold',
                          fontSize: '0.75rem'
                        }}>{api.method}</span>
                      </td>
                      <td style={{ padding: '10px 8px' }}><code>{api.url_pattern}</code></td>
                      <td style={{ padding: '10px 8px', textTransform: 'capitalize' }}>{api.auth_type || 'none'}</td>
                      <td style={{ padding: '10px 8px', color: api.bug_count > 0 ? '#ff4d4d' : '#10b981', fontWeight: 'bold' }}>
                        {api.bug_count > 0 ? `🐞 ${api.bug_count} Bugs` : '✓ 0 Bugs'}
                      </td>
                      <td style={{ padding: '10px 8px' }}>
                        {api.avg_latency > 0 ? `${api.avg_latency} ms` : 'N/A'}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Recommendations */}
      <div className="recommendations-section">
        <h3>💡 Recommendations</h3>
        <ul className="recommendations-list">
          {data.overall_quality.recommendations.map((rec, index) => (
            <li key={index}>{rec}</li>
          ))}
        </ul>
      </div>

      {/* Last Updated */}
      <div className="last-updated">
        Last updated: {new Date().toLocaleString()}
      </div>
    </div>
  );
};

export default QualityDashboard;