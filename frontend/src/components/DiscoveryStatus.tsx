import React, { useState, useEffect } from 'react';
import api from '../lib/api';
import { PageDetail } from '../lib/types';

interface DiscoveryStatusProps {
  appId: number;
  appStatus: string;
  discoverySource?: string;
  onDiscoveryComplete: () => void;
}

export const DiscoveryStatus: React.FC<DiscoveryStatusProps> = ({
  appId,
  appStatus,
  discoverySource,
  onDiscoveryComplete
}) => {
  const [pages, setPages] = useState<PageDetail[]>([]);
  const [loading, setLoading] = useState(false);
  const [expandedPageId, setExpandedPageId] = useState<number | null>(null);

  const fetchDiscoveredPages = async () => {
    try {
      const response = await api.get<PageDetail[]>(`applications/${appId}/pages/`);
      setPages(response.data);
    } catch (err) {
      console.error('Failed to fetch discovered pages:', err);
    }
  };

  // Poll for status updates while discovery is active
  useEffect(() => {
    let intervalId: any;
    
    if (appStatus === 'DISCOVERING') {
      setLoading(true);
      fetchDiscoveredPages();
      
      intervalId = setInterval(async () => {
        try {
          const statusRes = await api.get(`applications/${appId}/status/`);
          if (statusRes.data.status !== 'DISCOVERING') {
            setLoading(false);
            clearInterval(intervalId);
            onDiscoveryComplete();
          }
          fetchDiscoveredPages();
        } catch (err) {
          console.error(err);
          setLoading(false);
          clearInterval(intervalId);
        }
      }, 2000);
    } else {
      setLoading(false);
      fetchDiscoveredPages();
    }

    return () => {
      if (intervalId) clearInterval(intervalId);
    };
  }, [appId, appStatus]);

  const toggleExpandPage = (id: number) => {
    setExpandedPageId(expandedPageId === id ? null : id);
  };

  return (
    <div className="glass-card discovery-status-card">
      <div className="card-header discovery-header">
        <div>
          <h3>🔍 Site Discovery Status</h3>
          <p className="card-subtitle">
            Source: <span className="badge-source">{discoverySource || (loading ? 'Detecting routing...' : 'None')}</span>
          </p>
        </div>
        <div>
          {loading ? (
            <div className="loader-container">
              <div className="spinner"></div>
              <span className="pulsing-text">Discovering Pages...</span>
            </div>
          ) : (
            <span className="badge-status status-success">Discovery Finished</span>
          )}
        </div>
      </div>

      <div className="discovery-stats">
        <div className="stat-box">
          <span className="stat-val">{pages.length}</span>
          <span className="stat-label">Pages Found</span>
        </div>
        <div className="stat-box">
          <span className="stat-val">
            {pages.reduce((acc, p) => acc + (p.forms?.length || 0), 0)}
          </span>
          <span className="stat-label">Forms Found</span>
        </div>
        <div className="stat-box">
          <span className="stat-val">
            {pages.reduce((acc, p) => acc + (p.buttons?.length || 0), 0)}
          </span>
          <span className="stat-label">Buttons Found</span>
        </div>
      </div>

      {pages.length === 0 ? (
        <div className="empty-state">
          <p>No pages discovered yet. Click "Start Discovery" above to analyze the website.</p>
        </div>
      ) : (
        <div className="discovered-pages-list">
          <h4>🌐 Discovered Pages Structure</h4>
          {pages.map((page) => {
            const isExpanded = expandedPageId === page.id;
            return (
              <div key={page.id} className={`discovered-page-item ${isExpanded ? 'expanded' : ''}`}>
                <div className="page-item-header" onClick={() => toggleExpandPage(page.id)}>
                  <div className="page-info">
                    <span className="page-title">{page.title || 'Untitled Page'}</span>
                    <span className="page-url">{page.url}</span>
                  </div>
                  <div className="page-badges">
                    {page.forms?.length > 0 && (
                      <span className="badge badge-form">{page.forms.length} forms</span>
                    )}
                    {page.buttons?.length > 0 && (
                      <span className="badge badge-button">{page.buttons.length} buttons</span>
                    )}
                    <span className="expand-indicator">{isExpanded ? '▼' : '▶'}</span>
                  </div>
                </div>

                {isExpanded && (
                  <div className="page-item-details">
                    {page.forms && page.forms.length > 0 && (
                      <div className="details-section">
                        <h5>📝 Forms</h5>
                        {page.forms.map((form, fIdx) => (
                          <div key={fIdx} className="details-form-item">
                            <div className="form-meta">
                              <strong>Form ID:</strong> <code>{form.id}</code> | 
                              <strong> Action:</strong> <code>{form.action || '/'}</code> | 
                              <strong> Method:</strong> <code>{form.method.toUpperCase()}</code>
                            </div>
                            <ul className="form-fields-list">
                              {form.fields.map((fld, fldIdx) => (
                                <li key={fldIdx}>
                                  🏷️ Name: <code>{fld.name}</code> (type: <code>{fld.type}</code>
                                  {fld.id ? `, id: ${fld.id}` : ''})
                                </li>
                              ))}
                            </ul>
                          </div>
                        ))}
                      </div>
                    )}

                    {page.buttons && page.buttons.length > 0 && (
                      <div className="details-section">
                        <h5>🔘 Buttons / Interactive Elements</h5>
                        <ul className="details-buttons-list">
                          {page.buttons.map((btn, bIdx) => (
                            <li key={bIdx}>
                              <strong>"{btn.text || 'unnamed'}"</strong> - Selector: <code>{btn.selector}</code>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {!page.forms?.length && !page.buttons?.length && (
                      <p className="no-elements-tip">No forms or buttons detected on this page.</p>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
