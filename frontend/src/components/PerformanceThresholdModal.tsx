import React, { useState, useEffect } from 'react';
import api from '../lib/api';

interface PerformanceThresholdModalProps {
  appId: number;
  isOpen: boolean;
  onClose: () => void;
  onSaved?: () => void;
}

export const PerformanceThresholdModal: React.FC<PerformanceThresholdModalProps> = ({
  appId,
  isOpen,
  onClose,
  onSaved
}) => {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [apiWarning, setApiWarning] = useState(500);
  const [apiCritical, setApiCritical] = useState(2000);
  const [pageWarning, setPageWarning] = useState(3000);
  const [pageCritical, setPageCritical] = useState(8000);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen && appId) {
      setLoading(true);
      api.get(`applications/${appId}/performance-thresholds/`)
        .then(res => {
          if (res.data) {
            setApiWarning(res.data.api_latency_warning_ms || 500);
            setApiCritical(res.data.api_latency_critical_ms || 2000);
            setPageWarning(res.data.page_load_warning_ms || 3000);
            setPageCritical(res.data.page_load_critical_ms || 8000);
          }
        })
        .catch(err => console.error("Failed to load thresholds:", err))
        .finally(() => setLoading(false));
    }
  }, [isOpen, appId]);

  if (!isOpen) return null;

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setMessage(null);
    try {
      await api.patch(`applications/${appId}/performance-thresholds/`, {
        api_latency_warning_ms: Number(apiWarning),
        api_latency_critical_ms: Number(apiCritical),
        page_load_warning_ms: Number(pageWarning),
        page_load_critical_ms: Number(pageCritical),
      });
      setMessage("Thresholds updated successfully!");
      if (onSaved) onSaved();
      setTimeout(() => {
        onClose();
        setMessage(null);
      }, 1000);
    } catch (err: any) {
      setMessage(err.response?.data?.detail || "Failed to update thresholds.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-overlay" style={{
      position: 'fixed',
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      backgroundColor: 'rgba(0, 0, 0, 0.75)',
      backdropFilter: 'blur(8px)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 1000
    }}>
      <div className="glass-card modal-content" style={{
        width: '100%',
        maxWidth: '520px',
        padding: '28px',
        borderRadius: '16px',
        border: '1px solid rgba(255, 255, 255, 0.12)',
        boxShadow: '0 20px 50px rgba(0,0,0,0.8)'
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
          <h3 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: '8px', color: '#fff' }}>
            ⚡ Performance Latency Thresholds
          </h3>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#aaa', fontSize: '1.2rem', cursor: 'pointer' }}>✕</button>
        </div>

        {loading ? (
          <div style={{ textAlign: 'center', padding: '24px', color: '#aaa' }}>Loading thresholds...</div>
        ) : (
          <form onSubmit={handleSave} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <p style={{ fontSize: '0.85rem', color: 'rgba(255,255,255,0.6)', margin: 0 }}>
              Set response time boundaries (in milliseconds). Exceeding these limits will automatically log performance bugs during execution.
            </p>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '0.8rem', color: '#eab308', marginBottom: '4px', fontWeight: 600 }}>
                  API Warning (ms)
                </label>
                <input
                  type="number"
                  value={apiWarning}
                  onChange={(e) => setApiWarning(Number(e.target.value))}
                  style={{
                    width: '100%',
                    padding: '8px 12px',
                    borderRadius: '8px',
                    border: '1px solid rgba(255,255,255,0.15)',
                    background: 'rgba(0,0,0,0.3)',
                    color: '#fff'
                  }}
                  required
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.8rem', color: '#ef4444', marginBottom: '4px', fontWeight: 600 }}>
                  API Critical (ms)
                </label>
                <input
                  type="number"
                  value={apiCritical}
                  onChange={(e) => setApiCritical(Number(e.target.value))}
                  style={{
                    width: '100%',
                    padding: '8px 12px',
                    borderRadius: '8px',
                    border: '1px solid rgba(255,255,255,0.15)',
                    background: 'rgba(0,0,0,0.3)',
                    color: '#fff'
                  }}
                  required
                />
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '0.8rem', color: '#eab308', marginBottom: '4px', fontWeight: 600 }}>
                  Page Load Warning (ms)
                </label>
                <input
                  type="number"
                  value={pageWarning}
                  onChange={(e) => setPageWarning(Number(e.target.value))}
                  style={{
                    width: '100%',
                    padding: '8px 12px',
                    borderRadius: '8px',
                    border: '1px solid rgba(255,255,255,0.15)',
                    background: 'rgba(0,0,0,0.3)',
                    color: '#fff'
                  }}
                  required
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.8rem', color: '#ef4444', marginBottom: '4px', fontWeight: 600 }}>
                  Page Load Critical (ms)
                </label>
                <input
                  type="number"
                  value={pageCritical}
                  onChange={(e) => setPageCritical(Number(e.target.value))}
                  style={{
                    width: '100%',
                    padding: '8px 12px',
                    borderRadius: '8px',
                    border: '1px solid rgba(255,255,255,0.15)',
                    background: 'rgba(0,0,0,0.3)',
                    color: '#fff'
                  }}
                  required
                />
              </div>
            </div>

            {message && (
              <div style={{
                padding: '8px 12px',
                borderRadius: '8px',
                fontSize: '0.85rem',
                background: message.includes('success') ? 'rgba(34, 197, 94, 0.15)' : 'rgba(239, 68, 68, 0.15)',
                color: message.includes('success') ? '#4ade80' : '#f87171',
                border: `1px solid ${message.includes('success') ? 'rgba(34, 197, 94, 0.3)' : 'rgba(239, 68, 68, 0.3)'}`
              }}>
                {message}
              </div>
            )}

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px', marginTop: '12px' }}>
              <button
                type="button"
                onClick={onClose}
                style={{
                  padding: '8px 16px',
                  borderRadius: '8px',
                  border: '1px solid rgba(255,255,255,0.2)',
                  background: 'transparent',
                  color: '#fff',
                  cursor: 'pointer'
                }}
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={saving}
                style={{
                  padding: '8px 20px',
                  borderRadius: '8px',
                  border: 'none',
                  background: 'linear-gradient(135deg, #eab308 0%, #ca8a04 100%)',
                  color: '#000',
                  fontWeight: 600,
                  cursor: saving ? 'not-allowed' : 'pointer'
                }}
              >
                {saving ? 'Saving...' : 'Save Thresholds'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
};
