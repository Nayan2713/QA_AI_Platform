import React from 'react';
import { Check, X, Zap, Sparkles } from 'lucide-react';

const comparisonRows = [
  {
    feature: 'Test Suite Setup Time',
    traditional: 'Days or weeks of writing Selenium/Cypress scripts',
    qaPlatform: 'Under 2 minutes via autonomous Playwright crawling',
    highlight: true,
  },
  {
    feature: 'UI Selector Maintenance',
    traditional: 'Breaks every release; requires constant manual repairs',
    qaPlatform: 'Self-heals dynamic selectors mid-execution automatically',
    highlight: true,
  },
  {
    feature: 'AI LLM Running Costs',
    traditional: 'Expensive per-token API charges (OpenAI/Claude)',
    qaPlatform: '$0 API costs using self-hosted local Ollama LLMs',
    highlight: true,
  },
  {
    feature: 'Visual & Layout Defect Scan',
    traditional: 'Manual screenshot comparisons by QA engineers',
    qaPlatform: 'Automated DOM geometry & visual contrast auditing',
    highlight: false,
  },
  {
    feature: 'Security & Web Vitals Audit',
    traditional: 'Separate third-party scanning tools required',
    qaPlatform: 'Native CSP, HSTS, CORS & LCP/CLS performance audits',
    highlight: false,
  },
];

export function ComparisonSection() {
  return (
    <section className="landing-section">
      <div className="section-header">
        <span className="eyebrow-badge">
          <Zap className="w-4 h-4 text-purple-400" /> Why QA Engineer MVP
        </span>
        <h2 className="section-title">
          Traditional QA vs <span className="gradient-text">QA Engineer MVP</span>
        </h2>
        <p className="section-subtitle">
          See why modern engineering teams are ditching fragile legacy automation for self-healing AI agents.
        </p>
      </div>

      <div className="comparison-table-wrapper">
        <table className="comparison-table">
          <thead>
            <tr>
              <th className="w-1/4">Capability</th>
              <th className="w-[37.5%] text-slate-300">Traditional Manual / Legacy QA</th>
              <th className="w-[37.5%] text-purple-200">
                {/* <span className="bg-purple-900/90 px-3.5 py-1.5 rounded-lg border border-purple-500/50 text-purple-100 shadow-sm inline-block"> */}
                ⚡ QA Engineer MVP
                {/* </span> */}
              </th>
            </tr>
          </thead>
          <tbody>
            {comparisonRows.map((row) => (
              <tr key={row.feature} className="hover:bg-purple-950/30 transition-colors">
                <td className="font-extrabold text-white">
                  <div className="flex items-start gap-2.5 pt-0.5">
                    {row.highlight && <Sparkles className="w-4 h-4 text-purple-400 shrink-0 mt-1" />}
                    <span className="text-white font-extrabold leading-snug">{row.feature}</span>
                  </div>
                </td>
                <td className="text-slate-300 font-medium">
                  <div className="flex items-start gap-3">
                    <X className="w-5 h-5 text-red-400 shrink-0 mt-0.5" />
                    <span className="leading-relaxed text-slate-300">{row.traditional}</span>
                  </div>
                </td>
                <td className="font-semibold text-purple-100 bg-purple-950/40">
                  <div className="flex items-start gap-3">
                    <Check className="w-5 h-5 text-emerald-400 shrink-0 mt-0.5" />
                    <span className="leading-relaxed font-bold text-white">{row.qaPlatform}</span>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
