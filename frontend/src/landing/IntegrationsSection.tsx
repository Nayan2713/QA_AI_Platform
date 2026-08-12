import React from 'react';
import { GitBranch, MessageSquare, Terminal, Server, Layers, Cpu, Database, Zap } from 'lucide-react';

const integrations = [
  { name: 'GitHub Actions', category: 'CI/CD Pipeline', icon: <GitBranch className="w-9 h-9 text-purple-300" /> },
  { name: 'Slack', category: 'Real-time Alerts', icon: <MessageSquare className="w-9 h-9 text-emerald-300" /> },
  { name: 'Playwright', category: 'Browser Automation', icon: <Terminal className="w-9 h-9 text-blue-300" /> },
  { name: 'Docker', category: 'Container Infra', icon: <Server className="w-9 h-9 text-cyan-300" /> },
  { name: 'Jira', category: 'Issue Tracking', icon: <Layers className="w-9 h-9 text-indigo-300" /> },
  { name: 'Autonomous LLM', category: 'Self-Hosted AI', icon: <Cpu className="w-9 h-9 text-violet-300" /> },
  { name: 'PostgreSQL', category: 'Database Storage', icon: <Database className="w-9 h-9 text-blue-300" /> },
  { name: 'Vercel', category: 'Deployment Webhooks', icon: <Zap className="w-9 h-9 text-purple-300" /> },
];

export function IntegrationsSection() {
  return (
    <section id="integrations" className="landing-section">
      <div className="section-header">
        <span className="eyebrow-badge">
          <Terminal className="w-4 h-4 text-purple-400" /> Developer Ecosystem
        </span>
        <h2 className="section-title">
          Fits Seamlessly Into Your <span className="gradient-text">Existing Stack</span>
        </h2>
        <p className="section-subtitle">
          Trigger automated QA test suites on every git push, pull request, or scheduled cron job.
        </p>
      </div>

      <div className="integrations-grid">
        {integrations.map((item) => (
          <div key={item.name} className="integration-card">
            <div className="integration-icon-box">
              {item.icon}
            </div>
            <h3 className="integration-name">{item.name}</h3>
            <span className="integration-tag">
              {item.category}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}
