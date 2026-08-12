import React, { useRef } from 'react';
import { motion, useScroll, useTransform } from 'framer-motion';
import { Globe, Map, Cpu, ShieldCheck } from 'lucide-react';

const steps = [
  {
    number: '01',
    title: 'Point It at Your Site',
    description: 'Enter any staging or production URL. Configure login credentials or custom HTTP headers in seconds.',
    icon: <Globe className="w-7 h-7 text-purple-400" />,

  },
  {
    number: '02',
    title: 'It Maps Your App',
    description: 'Playwright crawlers autonomously traverse routes, extract input forms, buttons, workflows, and API endpoints.',
    icon: <Map className="w-7 h-7 text-blue-400" />,

  },
  {
    number: '03',
    title: 'AI Generates & Runs Tests',
    description: 'Autonomous AI models construct multi-step test cases, execute headless browser steps, and auto-heal selectors.',
    icon: <Cpu className="w-7 h-7 text-indigo-400" />,

  },
  {
    number: '04',
    title: 'Get Bugs & Quality Scores',
    description: 'Stream step logs, error traces, base64 screenshots, security findings, and Web Vitals metrics to your dashboard.',
    icon: <ShieldCheck className="w-7 h-7 text-emerald-400" />,

  },
];

export function TimelineSection() {
  const containerRef = useRef<HTMLDivElement>(null);

  const { scrollYProgress } = useScroll({
    target: containerRef,
    offset: ['start end', 'end center'],
  });

  const pathLength = useTransform(scrollYProgress, [0.1, 0.9], [0, 1]);

  return (
    <section id="how-it-works" ref={containerRef} className="landing-section">
      <div className="section-header">
        <span className="eyebrow-badge">
          <span className="pulse-dot" /> Simple 4-Step Process
        </span>
        <h2 className="section-title">
          How <span className="gradient-text">QA Engineer MVP</span> Works
        </h2>
        <p className="section-subtitle">
          From zero test coverage to fully autonomous, self-healing test automation in under 2 minutes.
        </p>
      </div>

      <div className="relative w-full">
        {/* SVG Drawing Connector Line (Desktop Horizontal) */}
        <div className="hidden lg:block absolute top-1/2 left-0 right-0 -translate-y-12 pointer-events-none z-0 px-12">
          <svg className="w-full h-12 overflow-visible" viewBox="0 0 1000 40" fill="none">
            <path
              d="M 50 20 L 950 20"
              stroke="rgba(139, 92, 246, 0.2)"
              strokeWidth="4"
              strokeDasharray="8 8"
            />
            <motion.path
              d="M 50 20 L 950 20"
              stroke="url(#timelineGradientHorizontal)"
              strokeWidth="5"
              strokeLinecap="round"
              style={{ pathLength }}
            />
            <defs>
              <linearGradient id="timelineGradientHorizontal" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stopColor="#2563EB" />
                <stop offset="50%" stopColor="#8B5CF6" />
                <stop offset="100%" stopColor="#06B6D4" />
              </linearGradient>
            </defs>
          </svg>
        </div>

        {/* Vertical SVG Connector Line (Mobile) */}
        <div className="lg:hidden absolute top-4 bottom-4 left-6 w-1 pointer-events-none z-0">
          <svg className="w-full h-full overflow-visible" fill="none">
            <path d="M 2 0 L 2 1000" stroke="rgba(139, 92, 246, 0.2)" strokeWidth="4" strokeDasharray="6 6" />
            <motion.path
              d="M 2 0 L 2 1000"
              stroke="url(#timelineGradientVertical)"
              strokeWidth="5"
              strokeLinecap="round"
              style={{ pathLength }}
            />
            <defs>
              <linearGradient id="timelineGradientVertical" x1="0%" y1="0%" x2="0%" y2="100%">
                <stop offset="0%" stopColor="#2563EB" />
                <stop offset="50%" stopColor="#8B5CF6" />
                <stop offset="100%" stopColor="#06B6D4" />
              </linearGradient>
            </defs>
          </svg>
        </div>

        {/* Step Cards Grid - Spacious Uncompressed Layout */}
        <div className="timeline-grid relative z-10 w-full pl-10 lg:pl-0">
          {steps.map((step, index) => (
            <div
              key={index}
              className="timeline-step-card space-y-6"
            >
              <div>
                <div className="w-16 h-16 rounded-2xl bg-purple-950/80 border border-purple-500/40 flex items-center justify-center shrink-0 mb-6 shadow-md mt-2">
                  {step.icon}
                </div>

                <h3 className="text-2xl font-extrabold text-white tracking-tight mb-3">{step.title}</h3>
                <p className="text-base text-slate-200 leading-relaxed font-normal">{step.description}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
