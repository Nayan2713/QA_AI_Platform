import React, { useState, useEffect } from 'react';
import api from '../lib/api';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

interface LoadTestItem {
  id: number;
  api_endpoint_pattern: string;
  method: string;
  concurrency: number;
  total_requests: number;
  p50_ms: number;
  p95_ms: number;
  p99_ms: number;
  error_rate: number;
  requests_per_second: number;
  created_at: string;
}

interface WebVitalsItem {
  id: number;
  page_title: string;
  url: string;
  lcp_ms: number;
  cls: number;
  ttfb_ms: number;
  performance_score: number;
  created_at: string;
}

interface LoadTestResultsPanelProps {
  appId: number;
  onOpenSettings: () => void;
}

export const LoadTestResultsPanel: React.FC<LoadTestResultsPanelProps> = ({ appId, onOpenSettings }) => {
  const [loadResults, setLoadResults] = useState<LoadTestItem[]>([]);
  const [vitalsResults, setVitalsResults] = useState<WebVitalsItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [startingLoadTest, setStartingLoadTest] = useState(false);
  const [startingVitals, setStartingVitals] = useState(false);
  const [concurrency, setConcurrency] = useState(20);
  const [duration, setDuration] = useState(30);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [loadRes, vitalsRes] = await Promise.all([
        api.get(`applications/${appId}/load-test-results/`),
        api.get(`applications/${appId}/web-vitals-results/`)
      ]);
      setLoadResults(Array.isArray(loadRes.data) ? loadRes.data : loadRes.data.results || []);
      setVitalsResults(Array.isArray(vitalsRes.data) ? vitalsRes.data : vitalsRes.data.results || []);
    } catch (err) {
      console.error("Error fetching performance metrics:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (appId) {
      fetchData();
    }
  }, [appId]);

  const handleRunLoadTest = async () => {
    setStartingLoadTest(true);
    try {
      await api.post(`applications/${appId}/load-test/`, { concurrency, duration_seconds: duration });
      setTimeout(fetchData, 4000);
    } catch (err) {
      console.error("Failed to start load test:", err);
    } finally {
      setStartingLoadTest(false);
    }
  };

  const handleRunWebVitals = async () => {
    setStartingVitals(true);
    try {
      await api.post(`applications/${appId}/web-vitals/`, {});
      setTimeout(fetchData, 4000);
    } catch (err) {
      console.error("Failed to trigger Web Vitals scan:", err);
    } finally {
      setStartingVitals(false);
    }
  };

  const chartData = loadResults.map(item => ({
    name: `${item.method} ${item.api_endpoint_pattern ? item.api_endpoint_pattern.substring(0, 15) : 'root'}`,
    p50: item.p50_ms,
    p95: item.p95_ms,
    p99: item.p99_ms
  }));

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* Top Action Bar */}
      <div className="glass-card" style={{ padding: '20px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '16px' }}>
        <div>
          <h3 style={{ margin: 0, color: '#fff', display: 'flex', alignItems: 'center', gap: '8px' }}>
            ⚡ Performance & Concurrent Load Testing
          </h3>
          <p style={{ margin: '4px 0 0 0', fontSize: '0.85rem', color: 'rgba(255,255,255,0.6)' }}>
            Benchmark concurrent traffic throughput, latency percentiles (p50/p95/p99), and Core Web Vitals.
          </p>
        </div>

        <div style={{ display: 'flex', gap: '12px', alignItems: 'center', flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ fontSize: '0.8rem', color: 'rgba(255,255,255,0.6)' }}>Users:</span>
            <input
              type="number"
              value={concurrency}
              onChange={(e) => setConcurrency(Number(e.target.value))}
              style={{ width: '60px', padding: '4px 8px', borderRadius: '6px', background: 'rgba(0,0,0,0.4)', border: '1px solid rgba(255,255,255,0.15)', color: '#fff' }}
            />
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ fontSize: '0.8rem', color: 'rgba(255,255,255,0.6)' }}>Secs:</span>
            <input
              type="number"
              value={duration}
              onChange={(e) => setDuration(Number(e.target.value))}
              style={{ width: '60px', padding: '4px 8px', borderRadius: '6px', background: 'rgba(0,0,0,0.4)', border: '1px solid rgba(255,255,255,0.15)', color: '#fff' }}
            />
          </div>

          <button
            onClick={handleRunLoadTest}
            disabled={startingLoadTest}
            style={{
              padding: '8px 16px',
              borderRadius: '8px',
              border: 'none',
              background: 'linear-gradient(135deg, #eab308 0%, #ca8a04 100%)',
              color: '#000',
              fontWeight: 600,
              cursor: startingLoadTest ? 'not-allowed' : 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px'
            }}
          >
            {startingLoadTest ? 'Starting...' : '🚀 Run Load Test'}
          </button>

          <button
            onClick={handleRunWebVitals}
            disabled={startingVitals}
            style={{
              padding: '8px 16px',
              borderRadius: '8px',
              border: '1px solid rgba(168, 85, 247, 0.4)',
              background: 'rgba(168, 85, 247, 0.15)',
              color: '#c084fc',
              fontWeight: 600,
              cursor: startingVitals ? 'not-allowed' : 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px'
            }}
          >
            {startingVitals ? 'Scanning...' : '🎯 Scan Core Web Vitals'}
          </button>

          <button
            onClick={onOpenSettings}
            style={{
              padding: '8px 14px',
              borderRadius: '8px',
              border: '1px solid rgba(255,255,255,0.2)',
              background: 'transparent',
              color: '#fff',
              cursor: 'pointer'
            }}
          >
            ⚙️ Thresholds
          </button>
        </div>
      </div>

      {/* Core Web Vitals Cards */}
      {vitalsResults.length > 0 && (
        <div className="glass-card" style={{ padding: '20px' }}>
          <h4 style={{ margin: '0 0 16px 0', color: '#c084fc', display: 'flex', alignItems: 'center', gap: '8px' }}>
            🎯 Core Web Vitals & Lighthouse Scores
          </h4>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '16px' }}>
            {vitalsResults.map((v) => (
              <div key={v.id} style={{
                background: 'rgba(255, 255, 255, 0.03)',
                border: '1px solid rgba(255, 255, 255, 0.08)',
                borderRadius: '12px',
                padding: '16px',
                display: 'flex',
                flexDirection: 'column',
                gap: '8px'
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: '0.85rem', fontWeight: 600, color: '#fff', wordBreak: 'break-all' }}>
                    {v.page_title || v.url}
                  </span>
                  <span style={{
                    fontSize: '1rem',
                    fontWeight: 700,
                    padding: '4px 10px',
                    borderRadius: '20px',
                    background: v.performance_score >= 90 ? 'rgba(34,197,94,0.2)' : v.performance_score >= 50 ? 'rgba(234,179,8,0.2)' : 'rgba(239,68,68,0.2)',
                    color: v.performance_score >= 90 ? '#4ade80' : v.performance_score >= 50 ? '#facc15' : '#f87171',
                    border: `1px solid ${v.performance_score >= 90 ? 'rgba(34,197,94,0.4)' : v.performance_score >= 50 ? 'rgba(234,179,8,0.4)' : 'rgba(239,68,68,0.4)'}`
                  }}>
                    {v.performance_score}/100
                  </span>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '8px', marginTop: '8px', fontSize: '0.8rem', color: 'rgba(255,255,255,0.7)' }}>
                  <div>LCP: <strong>{v.lcp_ms}ms</strong></div>
                  <div>CLS: <strong>{v.cls}</strong></div>
                  <div>TTFB: <strong>{v.ttfb_ms}ms</strong></div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Latency Comparison Chart */}
      {chartData.length > 0 && (
        <div className="glass-card" style={{ padding: '20px' }}>
          <h4 style={{ margin: '0 0 16px 0', color: '#eab308' }}>
            📊 Latency Percentiles (p50 / p95 / p99) per Endpoint
          </h4>
          <div style={{ width: '100%', height: 300 }}>
            <ResponsiveContainer>
              <BarChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" />
                <XAxis dataKey="name" stroke="rgba(255,255,255,0.5)" tick={{ fontSize: 12 }} />
                <YAxis stroke="rgba(255,255,255,0.5)" tick={{ fontSize: 12 }} unit="ms" />
                <Tooltip contentStyle={{ background: '#1a1a24', border: '1px solid rgba(255,255,255,0.2)', borderRadius: '8px' }} />
                <Legend />
                <Bar dataKey="p50" fill="#3b82f6" name="p50 (ms)" />
                <Bar dataKey="p95" fill="#eab308" name="p95 (ms)" />
                <Bar dataKey="p99" fill="#ef4444" name="p99 (ms)" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Load Test Results Table */}
      <div className="glass-card" style={{ padding: '20px' }}>
        <h4 style={{ margin: '0 0 16px 0', color: '#fff' }}>📋 Recent Load Test Results</h4>
        {loadResults.length === 0 ? (
          <div style={{ padding: '24px', textAlign: 'center', color: 'rgba(255,255,255,0.5)' }}>
            No load tests executed yet. Click "🚀 Run Load Test" above to start benchmarking.
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem', color: '#fff' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.1)', textAlign: 'left' }}>
                  <th style={{ padding: '10px' }}>Endpoint</th>
                  <th style={{ padding: '10px' }}>Concurrency</th>
                  <th style={{ padding: '10px' }}>Reqs</th>
                  <th style={{ padding: '10px' }}>RPS</th>
                  <th style={{ padding: '10px' }}>p50 (ms)</th>
                  <th style={{ padding: '10px' }}>p95 (ms)</th>
                  <th style={{ padding: '10px' }}>p99 (ms)</th>
                  <th style={{ padding: '10px' }}>Error Rate</th>
                </tr>
              </thead>
              <tbody>
                {loadResults.map((r) => (
                  <tr key={r.id} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                    <td style={{ padding: '10px', fontFamily: 'monospace' }}>
                      <span style={{ padding: '2px 6px', borderRadius: '4px', background: 'rgba(255,255,255,0.1)', marginRight: '6px' }}>{r.method || 'GET'}</span>
                      {r.api_endpoint_pattern || 'Root URL'}
                    </td>
                    <td style={{ padding: '10px' }}>{r.concurrency}c</td>
                    <td style={{ padding: '10px' }}>{r.total_requests}</td>
                    <td style={{ padding: '10px', fontWeight: 600, color: '#38bdf8' }}>{r.requests_per_second}/s</td>
                    <td style={{ padding: '10px' }}>{r.p50_ms}</td>
                    <td style={{ padding: '10px', color: '#facc15' }}>{r.p95_ms}</td>
                    <td style={{ padding: '10px', color: '#f87171' }}>{r.p99_ms}</td>
                    <td style={{ padding: '10px', color: r.error_rate > 0 ? '#f87171' : '#4ade80' }}>
                      {(r.error_rate * 100).toFixed(1)}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
