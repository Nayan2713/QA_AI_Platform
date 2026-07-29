import React, { useState } from 'react';
import api from '../lib/api';
import { Application } from '../lib/types';

interface AppFormProps {
  onAppCreated: (newApp: Application) => void;
  onCancel: () => void;
}

export const AppForm: React.FC<AppFormProps> = ({ onAppCreated, onCancel }) => {
  const [url, setUrl] = useState('');
  const [loginUrl, setLoginUrl] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [industry, setIndustry] = useState('');
  const [useLlmInCrawl, setUseLlmInCrawl] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const extractErrorMessage = (err: any): string => {
    const respData = err.response?.data;
    if (!respData) return err.message || 'Failed to add application';

    // Handle wrapped custom renderer data structure
    const innerData = respData.data || respData;
    const detailObj = innerData.detail || innerData;

    if (typeof detailObj === 'string') return detailObj;

    if (typeof detailObj === 'object' && detailObj !== null) {
      if (detailObj.url) {
        return Array.isArray(detailObj.url) ? detailObj.url[0] : String(detailObj.url);
      }
      if (detailObj.non_field_errors) {
        return Array.isArray(detailObj.non_field_errors) ? detailObj.non_field_errors[0] : String(detailObj.non_field_errors);
      }
      if (detailObj.username) {
        return Array.isArray(detailObj.username) ? detailObj.username[0] : String(detailObj.username);
      }
      if (detailObj.password) {
        return Array.isArray(detailObj.password) ? detailObj.password[0] : String(detailObj.password);
      }

      const firstKey = Object.keys(detailObj)[0];
      if (firstKey) {
        const val = detailObj[firstKey];
        if (Array.isArray(val)) return `${firstKey}: ${val[0]}`;
        if (typeof val === 'string') return `${firstKey}: ${val}`;
        if (typeof val === 'object' && val !== null) {
          const subKey = Object.keys(val)[0];
          if (subKey && Array.isArray(val[subKey])) return val[subKey][0];
        }
      }
    }

    return 'Failed to add application. Please check the provided URL.';
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!url) {
      setError('Application URL is required');
      return;
    }

    setLoading(true);
    setError('');

    try {
      const response = await api.post<Application>('applications/', {
        url,
        login_url: loginUrl || null,
        username: username || null,
        password: password || null,
        industry: industry || null,
        use_llm_in_crawl: useLlmInCrawl,
      });
      onAppCreated(response.data);
      setUrl('');
      setLoginUrl('');
      setUsername('');
      setPassword('');
      setIndustry('');
      setUseLlmInCrawl(false);
    } catch (err: any) {
      console.error(err);
      const errorMsg = extractErrorMessage(err);
      setError(errorMsg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="glass-card form-card">
      <div className="card-header">
        <h3>🚀 Add New Application URL</h3>
        <p className="card-subtitle">Register your web application to begin automated QA flows</p>
      </div>

      <form onSubmit={handleSubmit} className="app-form">
        {error && <div className="error-alert">{error}</div>}

        <div className="form-group">
          <label htmlFor="app-url">Application Target URL *</label>
          <input
            id="app-url"
            type="url"
            placeholder="https://example.com"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            required
            className="form-input"
          />
          <span className="input-tip">The landing page or base URL of the site you want to test.</span>
        </div>

        <div className="form-group">
          <label htmlFor="industry">Industry / Domain (Optional)</label>
          <select
            id="industry"
            value={industry}
            onChange={(e) => setIndustry(e.target.value)}
            className="form-input"
            style={{ width: '100%', padding: '0.75rem', borderRadius: '8px', border: '1px solid var(--border-glass)', background: '#120e24', color: '#f3f4f6', cursor: 'pointer' }}
          >
            <option value="" style={{ background: '#161127', color: '#f3f4f6' }}>Auto-Detect (AI)</option>
            <option value="E-commerce" style={{ background: '#161127', color: '#f3f4f6' }}>E-Commerce</option>
            <option value="FinTech" style={{ background: '#161127', color: '#f3f4f6' }}>FinTech / Banking</option>
            <option value="Healthcare" style={{ background: '#161127', color: '#f3f4f6' }}>Healthcare</option>
            <option value="SaaS" style={{ background: '#161127', color: '#f3f4f6' }}>SaaS / B2B</option>
            <option value="Recruitment" style={{ background: '#161127', color: '#f3f4f6' }}>HR / Recruitment</option>
            <option value="Real Estate" style={{ background: '#161127', color: '#f3f4f6' }}>Real Estate</option>
          </select>
          <span className="input-tip">Guides the AI to prioritize specific workflows (e.g. Shopping Cart for E-Commerce).</span>
        </div>

        <div className="form-group checkbox-group" style={{ display: 'flex', alignItems: 'flex-start', margin: '1.5rem 0' }}>
          <input
            id="use-llm-in-crawl"
            type="checkbox"
            checked={useLlmInCrawl}
            onChange={(e) => setUseLlmInCrawl(e.target.checked)}
            style={{ marginRight: '0.75rem', marginTop: '0.25rem', width: '1.25rem', height: '1.25rem', cursor: 'pointer' }}
          />
          <div>
            <label htmlFor="use-llm-in-crawl" style={{ fontWeight: '600', cursor: 'pointer', color: 'var(--text)' }}>
              Enable AI page summarization during discovery (Slow)
            </label>
            <span className="input-tip" style={{ display: 'block', marginTop: '0.25rem' }}>
              Summarizes page layouts using LLM/API key during the crawl. Disable this to make site discovery run much faster.
            </span>
          </div>
        </div>

        <fieldset className="form-fieldset">
          <legend>🔑 Optional Login Credentials (For Authenticated Crawling)</legend>
          <p className="fieldset-tip">Provide these if the crawler needs to bypass a login page to discover inner pages.</p>

          <div className="form-group">
            <label htmlFor="login-url">Login Page URL</label>
            <input
              id="login-url"
              type="url"
              placeholder="https://example.com/login"
              value={loginUrl}
              onChange={(e) => setLoginUrl(e.target.value)}
              className="form-input"
            />
          </div>

          <div className="form-grid">
            <div className="form-group">
              <label htmlFor="username">Username / Email</label>
              <input
                id="username"
                type="text"
                placeholder="qa-test-user"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="form-input"
              />
            </div>

            <div className="form-group">
              <label htmlFor="password">Password</label>
              <input
                id="password"
                type="password"
                placeholder="••••••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="form-input"
              />
            </div>
          </div>
        </fieldset>

        <div className="form-actions">
          <button type="button" onClick={onCancel} className="btn-secondary" disabled={loading}>
            Cancel
          </button>
          <button type="submit" className="btn-primary" disabled={loading}>
            {loading ? 'Adding Site...' : 'Add and Proceed'}
          </button>
        </div>
      </form>
    </div>
  );
};
