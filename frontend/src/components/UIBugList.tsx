import React, { useState } from 'react';
import { Bug } from '../lib/types';
import api from '../lib/api';

interface UIBugListProps {
  appId?: number;
  bugs: Bug[];
  onRefreshBugs?: () => void;
}

export const UIBugList: React.FC<UIBugListProps> = ({
  appId,
  bugs,
  onRefreshBugs
}) => {
  const [selectedBugId, setSelectedBugId] = useState<number | null>(null);
  const [filterCategory, setFilterCategory] = useState<string>('all');
  const [filterSeverity, setFilterSeverity] = useState<string>('all');
  const [filterStatus, setFilterStatus] = useState<string>('all');
  const [searchTerm, setSearchTerm] = useState<string>('');
  const [lightboxImage, setLightboxImage] = useState<string | null>(null);
  
  // Modal state for reporting a UI Bug
  const [showReportModal, setShowReportModal] = useState<boolean>(false);
  const [newTitle, setNewTitle] = useState<string>('');
  const [newDescription, setNewDescription] = useState<string>('');
  const [newSeverity, setNewSeverity] = useState<string>('medium');
  const [newCategory, setNewCategory] = useState<string>('layout');
  const [newSelector, setNewSelector] = useState<string>('');
  const [newScreenshot, setNewScreenshot] = useState<string>('');
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [copiedId, setCopiedId] = useState<number | null>(null);

  // Filter only UI bugs
  const uiBugs = bugs.filter(b => {
    const isUI = !b.bug_type || b.bug_type === 'ui' || b.bug_type === 'ui_issue' || b.bug_type === 'ui_bug' || b.bug_type === 'visual';
    return isUI;
  });

  const filteredBugs = uiBugs.filter(bug => {
    const matchesSearch = bug.title.toLowerCase().includes(searchTerm.toLowerCase()) || 
                          bug.description.toLowerCase().includes(searchTerm.toLowerCase()) ||
                          (bug.element_selector && bug.element_selector.toLowerCase().includes(searchTerm.toLowerCase()));
    
    const matchesSeverity = filterSeverity === 'all' || bug.severity.toLowerCase() === filterSeverity.toLowerCase();
    const matchesStatus = filterStatus === 'all' || (bug.status || 'open').toLowerCase() === filterStatus.toLowerCase();
    
    let matchesCategory = true;
    if (filterCategory !== 'all') {
      const text = `${bug.title} ${bug.description}`.toLowerCase();
      if (filterCategory === 'layout') matchesCategory = text.includes('layout') || text.includes('align') || text.includes('overlap') || text.includes('margin') || text.includes('padding');
      else if (filterCategory === 'responsive') matchesCategory = text.includes('responsive') || text.includes('mobile') || text.includes('overflow') || text.includes('viewport');
      else if (filterCategory === 'contrast') matchesCategory = text.includes('contrast') || text.includes('color') || text.includes('text') || text.includes('font');
      else if (filterCategory === 'media') matchesCategory = text.includes('image') || text.includes('icon') || text.includes('svg') || text.includes('asset') || text.includes('broken');
    }

    return matchesSearch && matchesSeverity && matchesStatus && matchesCategory;
  });

  const handleUpdateStatus = async (bugId: number, status: string) => {
    try {
      await api.patch(`bugs/${bugId}/`, { status });
      if (onRefreshBugs) onRefreshBugs();
    } catch (err) {
      console.error('Failed to update UI bug status:', err);
    }
  };

  const handleCopySelector = (bugId: number, selector: string) => {
    navigator.clipboard.writeText(selector);
    setCopiedId(bugId);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const handleReportBugSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim()) return;

    setIsSubmitting(true);
    try {
      await api.post('bugs/report-ui-bug/', {
        app_id: appId,
        title: `[${newCategory.toUpperCase()}] ${newTitle.trim()}`,
        description: newDescription.trim(),
        severity: newSeverity,
        element_selector: newSelector.trim(),
        screenshot: newScreenshot.trim(),
        steps_to_reproduce: ['Inspect component UI', 'Verify visual anomaly on page']
      });

      setShowReportModal(false);
      setNewTitle('');
      setNewDescription('');
      setNewSelector('');
      setNewScreenshot('');
      if (onRefreshBugs) onRefreshBugs();
    } catch (err) {
      console.error('Failed to report UI bug:', err);
    } finally {
      setIsSubmitting(false);
    }
  };

  const openBugsCount = uiBugs.filter(b => (b.status || 'open') === 'open').length;
  const resolvedBugsCount = uiBugs.filter(b => b.status === 'resolved').length;

  return (
    <div className="ui-bugs-container" style={{ color: '#fff', display: 'flex', flexDirection: 'column', gap: '20px' }}>
      
      {/* Top Header Card */}
      <div className="ui-bugs-header" style={{
        background: 'linear-gradient(135deg, rgba(30, 41, 59, 0.8) 0%, rgba(15, 23, 42, 0.9) 100%)',
        border: '1px solid rgba(255, 255, 255, 0.1)',
        borderRadius: '16px',
        padding: '24px',
        backdropFilter: 'blur(10px)',
        boxShadow: '0 8px 32px rgba(0, 0, 0, 0.3)',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        flexWrap: 'wrap',
        gap: '16px'
      }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span style={{ fontSize: '1.8rem' }}>🎨</span>
            <h2 style={{ fontSize: '1.5rem', fontWeight: 700, margin: 0, background: 'linear-gradient(90deg, #38bdf8, #a855f7)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
              UI Bugs & Visual Defects Studio
            </h2>
          </div>
          <p style={{ margin: '6px 0 0 0', color: 'var(--text-muted, #94a3b8)', fontSize: '0.9rem' }}>
            Track, report, and inspect frontend layout issues, visual alignment anomalies, CSS selector defects, and viewport breakages.
          </p>
        </div>

        <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
          <div className="stat-pill" style={{ background: 'rgba(239, 68, 68, 0.15)', border: '1px solid rgba(239, 68, 68, 0.3)', padding: '8px 16px', borderRadius: '10px', textAlign: 'center' }}>
            <span style={{ fontSize: '0.75rem', color: '#f87171', display: 'block', fontWeight: 600 }}>OPEN ISSUES</span>
            <span style={{ fontSize: '1.2rem', fontWeight: 800, color: '#ef4444' }}>{openBugsCount}</span>
          </div>

          <div className="stat-pill" style={{ background: 'rgba(16, 185, 129, 0.15)', border: '1px solid rgba(16, 185, 129, 0.3)', padding: '8px 16px', borderRadius: '10px', textAlign: 'center' }}>
            <span style={{ fontSize: '0.75rem', color: '#34d399', display: 'block', fontWeight: 600 }}>RESOLVED</span>
            <span style={{ fontSize: '1.2rem', fontWeight: 800, color: '#10b981' }}>{resolvedBugsCount}</span>
          </div>

          {appId && (
            <button
              onClick={() => setShowReportModal(true)}
              style={{
                background: 'linear-gradient(135deg, #a855f7 0%, #6366f1 100%)',
                color: '#fff',
                border: 'none',
                padding: '10px 20px',
                borderRadius: '10px',
                fontWeight: 700,
                cursor: 'pointer',
                boxShadow: '0 4px 14px rgba(168, 85, 247, 0.4)',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '8px',
                fontSize: '0.9rem',
                transition: 'all 0.2s'
              }}
            >
              ➕ Report UI Bug
            </button>
          )}
        </div>
      </div>

      {/* Toolbar / Filters */}
      <div className="ui-bugs-toolbar" style={{
        display: 'flex',
        gap: '12px',
        flexWrap: 'wrap',
        alignItems: 'center',
        background: 'rgba(15, 23, 42, 0.6)',
        padding: '14px 18px',
        borderRadius: '12px',
        border: '1px solid rgba(255, 255, 255, 0.08)'
      }}>
        {/* Search */}
        <div style={{ flex: '1 1 240px' }}>
          <input
            type="text"
            placeholder="🔍 Search UI issues, selectors, title..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            style={{
              width: '100%',
              background: 'rgba(30, 41, 59, 0.8)',
              border: '1px solid rgba(255, 255, 255, 0.15)',
              borderRadius: '8px',
              padding: '8px 14px',
              color: '#fff',
              fontSize: '0.85rem'
            }}
          />
        </div>

        {/* Category filter */}
        <select
          value={filterCategory}
          onChange={(e) => setFilterCategory(e.target.value)}
          style={{
            background: 'rgba(30, 41, 59, 0.8)',
            border: '1px solid rgba(255, 255, 255, 0.15)',
            borderRadius: '8px',
            padding: '8px 12px',
            color: '#fff',
            fontSize: '0.85rem'
          }}
        >
          <option value="all">Category: All</option>
          <option value="layout">📐 Layout & Alignment</option>
          <option value="responsive">📱 Responsiveness</option>
          <option value="contrast">👁️ Color & Contrast</option>
          <option value="media">🖼️ Broken Assets</option>
        </select>

        {/* Severity filter */}
        <select
          value={filterSeverity}
          onChange={(e) => setFilterSeverity(e.target.value)}
          style={{
            background: 'rgba(30, 41, 59, 0.8)',
            border: '1px solid rgba(255, 255, 255, 0.15)',
            borderRadius: '8px',
            padding: '8px 12px',
            color: '#fff',
            fontSize: '0.85rem'
          }}
        >
          <option value="all">Severity: All</option>
          <option value="critical">🔴 Critical</option>
          <option value="high">🟠 High</option>
          <option value="medium">🟡 Medium</option>
          <option value="low">🔵 Low</option>
        </select>

        {/* Status filter */}
        <select
          value={filterStatus}
          onChange={(e) => setFilterStatus(e.target.value)}
          style={{
            background: 'rgba(30, 41, 59, 0.8)',
            border: '1px solid rgba(255, 255, 255, 0.15)',
            borderRadius: '8px',
            padding: '8px 12px',
            color: '#fff',
            fontSize: '0.85rem'
          }}
        >
          <option value="all">Status: All</option>
          <option value="open">Open</option>
          <option value="confirmed">Confirmed</option>
          <option value="resolved">Resolved</option>
        </select>
      </div>

      {/* Bug Items Grid/List */}
      {filteredBugs.length === 0 ? (
        <div style={{
          background: 'rgba(15, 23, 42, 0.4)',
          border: '1px dashed rgba(255, 255, 255, 0.15)',
          borderRadius: '16px',
          padding: '48px',
          textAlign: 'center'
        }}>
          <span style={{ fontSize: '3rem', display: 'block', marginBottom: '12px' }}>✨</span>
          <h3 style={{ fontSize: '1.2rem', fontWeight: 600, margin: '0 0 8px 0', color: '#f1f5f9' }}>
            No UI Bugs Found
          </h3>
          <p style={{ color: '#94a3b8', fontSize: '0.9rem', maxWidth: '420px', margin: '0 auto 20px auto' }}>
            {searchTerm || filterSeverity !== 'all' || filterStatus !== 'all'
              ? 'No UI bugs match your current filters. Try resetting search or dropdown filters.'
              : 'Zero visual defects reported! Click "Report UI Bug" to log any layout or styling issues.'}
          </p>
          {appId && (
            <button
              onClick={() => setShowReportModal(true)}
              style={{
                background: 'rgba(168, 85, 247, 0.2)',
                border: '1px solid rgba(168, 85, 247, 0.4)',
                color: '#c084fc',
                padding: '8px 18px',
                borderRadius: '8px',
                fontWeight: 600,
                cursor: 'pointer'
              }}
            >
              ➕ Report First UI Bug
            </button>
          )}
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          {filteredBugs.map(bug => {
            const isExpanded = selectedBugId === bug.id;
            const currentStatus = bug.status || 'open';
            
            return (
              <div
                key={bug.id}
                style={{
                  background: currentStatus === 'resolved' 
                    ? 'rgba(15, 23, 42, 0.4)' 
                    : 'linear-gradient(135deg, rgba(30, 41, 59, 0.6) 0%, rgba(15, 23, 42, 0.8) 100%)',
                  border: currentStatus === 'resolved' 
                    ? '1px solid rgba(16, 185, 129, 0.2)' 
                    : '1px solid rgba(255, 255, 255, 0.1)',
                  borderRadius: '14px',
                  overflow: 'hidden',
                  transition: 'all 0.2s',
                  boxShadow: '0 4px 16px rgba(0, 0, 0, 0.2)'
                }}
              >
                {/* Bug Summary Row */}
                <div
                  onClick={() => setSelectedBugId(isExpanded ? null : bug.id)}
                  style={{
                    padding: '16px 20px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    cursor: 'pointer',
                    gap: '16px',
                    flexWrap: 'wrap'
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flex: '1 1 300px' }}>
                    {/* Severity Pill */}
                    <span style={{
                      padding: '4px 10px',
                      borderRadius: '6px',
                      fontSize: '0.75rem',
                      fontWeight: 700,
                      textTransform: 'uppercase',
                      letterSpacing: '0.5px',
                      background: bug.severity === 'critical' ? 'rgba(239, 68, 68, 0.2)' :
                                  bug.severity === 'high' ? 'rgba(249, 115, 22, 0.2)' :
                                  bug.severity === 'medium' ? 'rgba(234, 179, 8, 0.2)' : 'rgba(59, 130, 246, 0.2)',
                      color: bug.severity === 'critical' ? '#ef4444' :
                             bug.severity === 'high' ? '#f97316' :
                             bug.severity === 'medium' ? '#eab308' : '#3b82f6',
                      border: `1px solid ${
                        bug.severity === 'critical' ? 'rgba(239, 68, 68, 0.4)' :
                        bug.severity === 'high' ? 'rgba(249, 115, 22, 0.4)' :
                        bug.severity === 'medium' ? 'rgba(234, 179, 8, 0.4)' : 'rgba(59, 130, 246, 0.4)'
                      }`
                    }}>
                      {bug.severity}
                    </span>

                    {/* Title */}
                    <span style={{
                      fontWeight: 600,
                      fontSize: '1rem',
                      color: currentStatus === 'resolved' ? '#94a3b8' : '#f8fafc',
                      textDecoration: currentStatus === 'resolved' ? 'line-through' : 'none'
                    }}>
                      🎨 {bug.title}
                    </span>
                  </div>

                  {/* Right Actions & Badge */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }} onClick={(e) => e.stopPropagation()}>
                    {/* Status badge */}
                    <select
                      value={currentStatus}
                      onChange={(e) => handleUpdateStatus(bug.id, e.target.value)}
                      style={{
                        background: currentStatus === 'resolved' ? 'rgba(16, 185, 129, 0.2)' : 'rgba(30, 41, 59, 0.9)',
                        border: currentStatus === 'resolved' ? '1px solid #10b981' : '1px solid rgba(255, 255, 255, 0.2)',
                        color: currentStatus === 'resolved' ? '#34d399' : '#fff',
                        borderRadius: '6px',
                        padding: '4px 10px',
                        fontSize: '0.8rem',
                        fontWeight: 600,
                        cursor: 'pointer'
                      }}
                    >
                      <option value="open" style={{ background: '#0f172a', color: '#ef4444' }}>🔴 Open</option>
                      <option value="confirmed" style={{ background: '#0f172a', color: '#eab308' }}>🟡 Confirmed</option>
                      <option value="resolved" style={{ background: '#0f172a', color: '#10b981' }}>🟢 Resolved</option>
                    </select>

                    {/* Toggle Collapse */}
                    <button
                      onClick={() => setSelectedBugId(isExpanded ? null : bug.id)}
                      style={{
                        background: 'rgba(255, 255, 255, 0.05)',
                        border: '1px solid rgba(255, 255, 255, 0.1)',
                        color: '#94a3b8',
                        borderRadius: '6px',
                        padding: '4px 10px',
                        fontSize: '0.8rem',
                        cursor: 'pointer'
                      }}
                    >
                      {isExpanded ? 'Collapse ˄' : 'Details ˅'}
                    </button>
                  </div>
                </div>

                {/* Expanded Details Panel */}
                {isExpanded && (
                  <div style={{
                    padding: '20px',
                    borderTop: '1px solid rgba(255, 255, 255, 0.08)',
                    background: 'rgba(15, 23, 42, 0.5)',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '16px'
                  }}>
                    {/* Element selector badge if available */}
                    {bug.element_selector && (
                      <div style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        background: 'rgba(30, 41, 59, 0.9)',
                        padding: '10px 14px',
                        borderRadius: '8px',
                        border: '1px solid rgba(56, 189, 248, 0.3)'
                      }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', overflow: 'hidden' }}>
                          <span style={{ fontSize: '0.8rem', color: '#38bdf8', fontWeight: 600 }}>DOM Selector:</span>
                          <code style={{ fontSize: '0.85rem', color: '#f43f5e', background: 'rgba(0,0,0,0.3)', padding: '2px 6px', borderRadius: '4px' }}>
                            {bug.element_selector}
                          </code>
                        </div>
                        <button
                          onClick={() => handleCopySelector(bug.id, bug.element_selector!)}
                          style={{
                            background: copiedId === bug.id ? 'rgba(16, 185, 129, 0.2)' : 'rgba(255, 255, 255, 0.1)',
                            border: 'none',
                            color: copiedId === bug.id ? '#34d399' : '#fff',
                            padding: '4px 10px',
                            borderRadius: '6px',
                            fontSize: '0.75rem',
                            cursor: 'pointer',
                            fontWeight: 600
                          }}
                        >
                          {copiedId === bug.id ? '✓ Copied' : '📋 Copy Selector'}
                        </button>
                      </div>
                    )}

                    {/* Description */}
                    <div>
                      <h4 style={{ fontSize: '0.85rem', color: '#94a3b8', margin: '0 0 6px 0', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                        Description & Visual Analysis
                      </h4>
                      <p style={{ margin: 0, fontSize: '0.95rem', lineHeight: '1.5', color: '#e2e8f0', whiteSpace: 'pre-wrap' }}>
                        {bug.description || 'No description provided.'}
                      </p>
                    </div>

                    {/* Steps to Reproduce */}
                    {bug.steps_to_reproduce && bug.steps_to_reproduce.length > 0 && (
                      <div>
                        <h4 style={{ fontSize: '0.85rem', color: '#94a3b8', margin: '0 0 6px 0', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                          Steps to Reproduce
                        </h4>
                        <ol style={{ margin: 0, paddingLeft: '20px', color: '#cbd5e1', fontSize: '0.9rem' }}>
                          {bug.steps_to_reproduce.map((step, idx) => (
                            <li key={idx} style={{ marginBottom: '4px' }}>{step}</li>
                          ))}
                        </ol>
                      </div>
                    )}

                    {/* Screenshot Preview */}
                    {bug.screenshot && (
                      <div>
                        <h4 style={{ fontSize: '0.85rem', color: '#94a3b8', margin: '0 0 8px 0', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                          Captured Screenshot
                        </h4>
                        <div
                          onClick={() => setLightboxImage(bug.screenshot!)}
                          style={{
                            maxWidth: '400px',
                            maxHeight: '220px',
                            borderRadius: '8px',
                            overflow: 'hidden',
                            border: '1px solid rgba(255, 255, 255, 0.15)',
                            cursor: 'zoom-in',
                            position: 'relative'
                          }}
                        >
                          <img
                            src={bug.screenshot}
                            alt="UI Bug Screenshot"
                            style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                          />
                          <div style={{
                            position: 'absolute',
                            bottom: '8px',
                            right: '8px',
                            background: 'rgba(0,0,0,0.7)',
                            padding: '4px 8px',
                            borderRadius: '4px',
                            fontSize: '0.75rem',
                            color: '#fff'
                          }}>
                            🔍 Click to expand
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Lightbox Modal for Screenshots */}
      {lightboxImage && (
        <div
          onClick={() => setLightboxImage(null)}
          style={{
            position: 'fixed',
            top: 0, left: 0, right: 0, bottom: 0,
            background: 'rgba(0, 0, 0, 0.85)',
            zIndex: 9999,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '24px',
            backdropFilter: 'blur(6px)'
          }}
        >
          <img
            src={lightboxImage}
            alt="Enlarged UI Bug"
            style={{ maxWidth: '90vw', maxHeight: '90vh', borderRadius: '12px', boxShadow: '0 12px 48px rgba(0,0,0,0.5)' }}
          />
        </div>
      )}

      {/* Report UI Bug Modal */}
      {showReportModal && (
        <div style={{
          position: 'fixed',
          top: 0, left: 0, right: 0, bottom: 0,
          background: 'rgba(0, 0, 0, 0.75)',
          zIndex: 9000,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '20px',
          backdropFilter: 'blur(6px)'
        }}>
          <div style={{
            background: 'linear-gradient(135deg, #1e293b 0%, #0f172a 100%)',
            border: '1px solid rgba(255, 255, 255, 0.15)',
            borderRadius: '16px',
            padding: '28px',
            maxWidth: '540px',
            width: '100%',
            boxShadow: '0 20px 50px rgba(0,0,0,0.5)',
            color: '#fff'
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
              <h3 style={{ margin: 0, fontSize: '1.3rem', fontWeight: 700 }}>🎨 Report UI Bug / Defect</h3>
              <button
                onClick={() => setShowReportModal(false)}
                style={{ background: 'none', border: 'none', color: '#94a3b8', fontSize: '1.2rem', cursor: 'pointer' }}
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleReportBugSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '0.85rem', color: '#94a3b8', marginBottom: '6px' }}>Bug Title *</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Navigation logo overlapping on mobile screens"
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                  style={{
                    width: '100%',
                    background: 'rgba(30, 41, 59, 0.9)',
                    border: '1px solid rgba(255, 255, 255, 0.2)',
                    borderRadius: '8px',
                    padding: '10px 14px',
                    color: '#fff',
                    fontSize: '0.9rem'
                  }}
                />
              </div>

              <div style={{ display: 'flex', gap: '12px' }}>
                <div style={{ flex: 1 }}>
                  <label style={{ display: 'block', fontSize: '0.85rem', color: '#94a3b8', marginBottom: '6px' }}>UI Category</label>
                  <select
                    value={newCategory}
                    onChange={(e) => setNewCategory(e.target.value)}
                    style={{
                      width: '100%',
                      background: 'rgba(30, 41, 59, 0.9)',
                      border: '1px solid rgba(255, 255, 255, 0.2)',
                      borderRadius: '8px',
                      padding: '10px 14px',
                      color: '#fff',
                      fontSize: '0.9rem'
                    }}
                  >
                    <option value="layout">📐 Layout & Alignment</option>
                    <option value="responsive">📱 Responsiveness</option>
                    <option value="contrast">👁️ Color & Contrast</option>
                    <option value="media">🖼️ Broken Image/Asset</option>
                  </select>
                </div>

                <div style={{ flex: 1 }}>
                  <label style={{ display: 'block', fontSize: '0.85rem', color: '#94a3b8', marginBottom: '6px' }}>Severity</label>
                  <select
                    value={newSeverity}
                    onChange={(e) => setNewSeverity(e.target.value)}
                    style={{
                      width: '100%',
                      background: 'rgba(30, 41, 59, 0.9)',
                      border: '1px solid rgba(255, 255, 255, 0.2)',
                      borderRadius: '8px',
                      padding: '10px 14px',
                      color: '#fff',
                      fontSize: '0.9rem'
                    }}
                  >
                    <option value="low">🔵 Low</option>
                    <option value="medium">🟡 Medium</option>
                    <option value="high">🟠 High</option>
                    <option value="critical">🔴 Critical</option>
                  </select>
                </div>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.85rem', color: '#94a3b8', marginBottom: '6px' }}>DOM Element Selector (Optional)</label>
                <input
                  type="text"
                  placeholder="e.g. .header-nav > #logo-img or button.submit-btn"
                  value={newSelector}
                  onChange={(e) => setNewSelector(e.target.value)}
                  style={{
                    width: '100%',
                    background: 'rgba(30, 41, 59, 0.9)',
                    border: '1px solid rgba(255, 255, 255, 0.2)',
                    borderRadius: '8px',
                    padding: '10px 14px',
                    color: '#fff',
                    fontSize: '0.9rem'
                  }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.85rem', color: '#94a3b8', marginBottom: '6px' }}>Screenshot URL (Optional)</label>
                <input
                  type="url"
                  placeholder="https://example.com/screenshot.png"
                  value={newScreenshot}
                  onChange={(e) => setNewScreenshot(e.target.value)}
                  style={{
                    width: '100%',
                    background: 'rgba(30, 41, 59, 0.9)',
                    border: '1px solid rgba(255, 255, 255, 0.2)',
                    borderRadius: '8px',
                    padding: '10px 14px',
                    color: '#fff',
                    fontSize: '0.9rem'
                  }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.85rem', color: '#94a3b8', marginBottom: '6px' }}>Description</label>
                <textarea
                  rows={3}
                  placeholder="Describe the UI issue, expected behavior vs actual visual behavior..."
                  value={newDescription}
                  onChange={(e) => setNewDescription(e.target.value)}
                  style={{
                    width: '100%',
                    background: 'rgba(30, 41, 59, 0.9)',
                    border: '1px solid rgba(255, 255, 255, 0.2)',
                    borderRadius: '8px',
                    padding: '10px 14px',
                    color: '#fff',
                    fontSize: '0.9rem',
                    resize: 'vertical'
                  }}
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px', marginTop: '10px' }}>
                <button
                  type="button"
                  onClick={() => setShowReportModal(false)}
                  style={{
                    background: 'transparent',
                    border: '1px solid rgba(255, 255, 255, 0.2)',
                    color: '#fff',
                    padding: '10px 18px',
                    borderRadius: '8px',
                    cursor: 'pointer'
                  }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  style={{
                    background: 'linear-gradient(135deg, #a855f7 0%, #6366f1 100%)',
                    border: 'none',
                    color: '#fff',
                    padding: '10px 22px',
                    borderRadius: '8px',
                    fontWeight: 700,
                    cursor: 'pointer'
                  }}
                >
                  {isSubmitting ? 'Saving...' : 'Report UI Bug'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

    </div>
  );
};
