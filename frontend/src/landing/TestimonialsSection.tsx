import React, { useState } from 'react';
import { Star, Quote } from 'lucide-react';

const testimonials = [
  {
    id: 1,
    quote:
      'QA Engineer MVP eliminated 95% of our manual regression testing workload. Pointing it at our staging URL generates realistic user scenarios that execute flawlessly with self-healing Playwright scripts.',
    author: 'Sarah Chen',
    role: 'VP of Engineering',
    company: 'FintechFlow',
    avatar: 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=150&auto=format&fit=crop&q=80',
    rating: 5,
  },
  {
    id: 2,
    quote:
      'The self-healing tests are pure magic. When our design team refactored CSS classes across our app, QA Engineer MVP dynamically repaired element selectors mid-run with zero test suite breakage.',
    author: 'Marcus Vance',
    role: 'Lead QA Architect',
    company: 'CloudScale AI',
    avatar: 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=150&auto=format&fit=crop&q=80',
    rating: 5,
  },
  {
    id: 3,
    quote:
      'We went from zero automation to catching visual UI overlaps, missing CSP headers, and latency spikes automatically on every PR build. It’s like having an entire QA department on autopilot.',
    author: 'Elena Rostova',
    role: 'Head of Product',
    company: 'SaaSify Inc.',
    avatar: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=150&auto=format&fit=crop&q=80',
    rating: 5,
  },
];

export function TestimonialsSection() {
  const [activeIdx, setActiveIdx] = useState(1);

  return (
    <section id="testimonials" className="landing-section">
      <div className="section-header">
        <span className="eyebrow-badge">
          <Quote className="w-4 h-4 text-purple-400" /> Loved by Engineers
        </span>
        <h2 className="section-title">
          Trusted by <span className="gradient-text">High-Velocity Teams</span>
        </h2>
        <p className="section-subtitle">
          See how engineering leaders automate regression testing and ship bug-free software faster.
        </p>
      </div>

      <div className="relative">
        <div className="testimonials-grid items-stretch">
          {testimonials.map((t, idx) => {
            const isActive = idx === activeIdx;

            return (
              <div
                key={t.id}
                onClick={() => setActiveIdx(idx)}
                className={`p-7 md:p-8 rounded-3xl border-2 transition-all duration-300 cursor-pointer relative flex flex-col justify-between h-full ${isActive
                    ? 'bg-slate-900/98 border-emerald-400/70 shadow-2xl shadow-emerald-500/20 z-10'
                    : 'bg-slate-950/90 border-purple-500/30 shadow-lg hover:bg-slate-900/90 hover:border-purple-500/50 opacity-90 hover:opacity-100'
                  }`}
              >
                <div>
                  {/* Big Green Quote Icon (Double 6s - Reference Match) */}
                  <div className="text-emerald-400/90 mb-3">
                    <Quote className="w-8 h-8 fill-emerald-400/20 text-emerald-400" />
                  </div>

                  {/* Quote Text */}
                  <p className="text-slate-200 text-sm md:text-base leading-relaxed mb-6 font-normal italic">
                    "{t.quote}"
                  </p>
                </div>

                {/* Bottom Section: Stars + Author Info Row (Always aligned at same Y-height) */}
                <div className="mt-auto space-y-4 pt-4 border-t border-purple-500/20">
                  <div className="flex items-center gap-1">
                    {[...Array(t.rating)].map((_, i) => (
                      <Star key={i} className="w-4 h-4 fill-amber-400 text-amber-400" />
                    ))}
                  </div>

                  <div className="flex items-center gap-3.5">
                    <img
                      src={t.avatar}
                      alt={t.author}
                      className="w-12 h-12 rounded-full object-cover border-2 border-emerald-500/50 shadow-md shrink-0"
                    />
                    <div>
                      <h4 className="font-extrabold text-white text-sm md:text-base leading-snug">{t.author}</h4>
                      <p className="text-xs text-slate-300 font-medium mt-0.5">{t.role} at <span className="font-bold text-emerald-300">{t.company}</span></p>
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
