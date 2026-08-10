import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Zap,
  ArrowRight,
  Shield,
  CheckCircle2,
  Lock,
  Globe,
  Sparkles,
  Bot,
  Activity,
  Cpu,
  Terminal,
  Bell,
  Code,
  Share2,
  MessageSquare,
  X,
  Menu,
  Eye,
  EyeOff,
  User as UserIcon,
  Mail,
  AlertCircle,
  FileCode2,
} from 'lucide-react';

import { Hero3DScene } from './Hero3DScene';
import { FeatureCard } from './FeatureCard';
import { TimelineSection } from './TimelineSection';
import { IntegrationsSection } from './IntegrationsSection';
import { TestimonialsSection } from './TestimonialsSection';
import { LiveDemoSimulator } from './LiveDemoSimulator';
import { AutonomousArchitecture3D } from './AutonomousArchitecture3D';
import { ComparisonSection } from './ComparisonSection';
import './LandingPage.css';

interface LandingPageProps {
  onLoginSuccess?: (token: string, username: string) => void;
  onOpenAuthModal?: (isLoginMode: boolean) => void;
  authError?: string;
  authSuccess?: string;
  authLoading?: boolean;
  onAuthSubmit?: (e: React.FormEvent, isLogin: boolean, email: string, pass: string, user: string) => void;
}

export function MagneticButton({
  children,
  className,
  onClick,
  type = 'button',
}: {
  children: React.ReactNode;
  className?: string;
  onClick?: () => void;
  type?: 'button' | 'submit' | 'reset';
}) {
  const ref = React.useRef<HTMLButtonElement>(null);
  const [position, setPosition] = React.useState({ x: 0, y: 0 });

  const handleMouseMove = (e: React.MouseEvent<HTMLButtonElement>) => {
    if (!ref.current) return;
    const { left, top, width, height } = ref.current.getBoundingClientRect();
    const x = (e.clientX - (left + width / 2)) * 0.35;
    const y = (e.clientY - (top + height / 2)) * 0.35;
    setPosition({ x, y });
  };

  const handleMouseLeave = () => {
    setPosition({ x: 0, y: 0 });
  };

  return (
    <motion.button
      ref={ref}
      type={type}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
      animate={{ x: position.x, y: position.y }}
      transition={{ type: 'spring', stiffness: 300, damping: 20, mass: 0.5 }}
      onClick={onClick}
      className={className}
    >
      {children}
    </motion.button>
  );
}

import { useNavigate, useLocation } from 'react-router-dom';

export function LandingPage({
  onLoginSuccess,
  onOpenAuthModal,
  authError,
  authSuccess,
  authLoading,
  onAuthSubmit,
}: LandingPageProps) {
  const navigate = useNavigate();
  const location = useLocation();

  const [isScrolled, setIsScrolled] = useState(false);
  const [showAuthModal, setShowAuthModal] = useState(false);
  const [isLoginMode, setIsLoginMode] = useState(true);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [username, setUsername] = useState('');

  // Sync route URL with modal state
  useEffect(() => {
    if (location.pathname === '/login') {
      setShowAuthModal(true);
      setIsLoginMode(true);
    } else if (location.pathname === '/signup' || location.pathname === '/register') {
      setShowAuthModal(true);
      setIsLoginMode(false);
    } else if (location.pathname === '/dashboard') {
      setShowAuthModal(true);
      setIsLoginMode(true);
      navigate('/login', { replace: true });
    } else if (location.pathname === '/') {
      setShowAuthModal(false);
    }
  }, [location.pathname, navigate]);

  useEffect(() => {
    if (typeof window !== 'undefined') {
      if ('scrollRestoration' in window.history) {
        window.history.scrollRestoration = 'manual';
      }
      window.scrollTo(0, 0);
    }

    const handleScroll = () => {
      setIsScrolled(window.scrollY > 20);
    };
    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setShowAuthModal(false);
        setMobileMenuOpen(false);
        if (location.pathname === '/login' || location.pathname === '/signup' || location.pathname === '/register') {
          navigate('/');
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [location.pathname, navigate]);

  const handleOpenAuth = (mode: 'login' | 'register') => {
    const target = mode === 'login' ? '/login' : '/signup';
    setIsLoginMode(mode === 'login');
    setShowAuthModal(true);
    setMobileMenuOpen(false);
    navigate(target);
    if (onOpenAuthModal) onOpenAuthModal(mode === 'login');
  };

  const handleCloseModal = () => {
    setShowAuthModal(false);
    setMobileMenuOpen(false);
    navigate('/');
  };

  const handleFormSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (onAuthSubmit) {
      onAuthSubmit(e, isLoginMode, email, password, username);
    }
  };

  return (
    <div className="landing-root">
      {/* Cyber Grid & Background Gradient Blobs */}
      <div className="cyber-grid" />
      <div className="blob-container">
        <div className="gradient-blob blob-1" />
        <div className="gradient-blob blob-2" />
        <div className="gradient-blob blob-3" />
      </div>

      {/* Glass Navbar */}
      <nav className={`landing-nav ${isScrolled ? 'scrolled' : ''}`}>
        <div className="nav-content">
          <a href="#" className="brand-logo">
            <div className="brand-icon">⚡</div>
            <span>QA Engineer MVP</span>
          </a>

          <ul className="nav-links hidden md:flex">
            <li><a href="#features" className="nav-link">Features</a></li>
            <li><a href="#how-it-works" className="nav-link">How It Works</a></li>
            <li><a href="#integrations" className="nav-link">Integrations</a></li>
            <li><a href="#testimonials" className="nav-link">Testimonials</a></li>
            <li>
              <a
                href={(import.meta as any).env.VITE_API_URL ? `${(import.meta as any).env.VITE_API_URL.replace(/\/api\/?$/, '')}/api/docs/` : "/api/docs/"}
                target="_blank"
                rel="noopener noreferrer"
                className="nav-link"
              >
                API Docs
              </a>
            </li>
          </ul>

          <div className="nav-actions hidden md:flex">
            <button onClick={() => handleOpenAuth('login')} className="btn-login">
              Login
            </button>
            <button onClick={() => handleOpenAuth('register')} className="btn-gradient">
              Get Started
            </button>
          </div>

          <button
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="md:hidden p-2 rounded-xl text-slate-300 hover:bg-purple-900/30 transition-colors"
            aria-label="Toggle Menu"
          >
            {mobileMenuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
          </button>
        </div>

        {/* Mobile Slide Drawer */}
        <AnimatePresence>
          {mobileMenuOpen && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              className="md:hidden border-t border-purple-500/20 bg-slate-950/95 backdrop-blur-xl px-6 py-6 space-y-4 overflow-hidden"
            >
              <a href="#features" onClick={() => setMobileMenuOpen(false)} className="block font-semibold text-slate-300 hover:text-purple-400 py-1">
                Features
              </a>
              <a href="#how-it-works" onClick={() => setMobileMenuOpen(false)} className="block font-semibold text-slate-300 hover:text-purple-400 py-1">
                How It Works
              </a>
              <a href="#integrations" onClick={() => setMobileMenuOpen(false)} className="block font-semibold text-slate-300 hover:text-purple-400 py-1">
                Integrations
              </a>
              <a href="#testimonials" onClick={() => setMobileMenuOpen(false)} className="block font-semibold text-slate-300 hover:text-purple-400 py-1">
                Testimonials
              </a>
              <a
                href={(import.meta as any).env.VITE_API_URL ? `${(import.meta as any).env.VITE_API_URL.replace(/\/api\/?$/, '')}/api/docs/` : "/api/docs/"}
                target="_blank"
                rel="noopener noreferrer"
                onClick={() => setMobileMenuOpen(false)}
                className="block font-semibold text-slate-300 hover:text-purple-400 py-1"
              >
                API Docs
              </a>
              <div className="pt-4 border-t border-purple-500/20 flex flex-col gap-3">
                <button onClick={() => handleOpenAuth('login')} className="w-full py-3 rounded-xl font-bold border border-purple-500/30 text-white hover:bg-purple-900/30">
                  Login
                </button>
                <button onClick={() => handleOpenAuth('register')} className="w-full py-3 rounded-xl font-bold bg-gradient-to-r from-blue-600 to-purple-600 text-white shadow-md">
                  Get Started
                </button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </nav>

      {/* HERO SECTION WITH 3D CENTERPIECE & LIVE SIMULATOR */}
      <section className="hero-section">
        <motion.div
          initial={{ opacity: 0, x: -30 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.8 }}
          className="hero-content"
        >


          <h1 className="hero-headline">
            Autonomous Quality Assurance <br />
            <span className="gradient-text">That Thinks & Self-Heals</span>
          </h1>

          <p className="hero-subheadline font-medium text-slate-200">
            Point QA Engineer MVP at any URL. Our autonomous AI agents crawl your app, generate multi-step test cases, execute Playwright browser tests, self-heal broken selectors, and catch bugs automatically.
          </p>

          <div className="hero-cta-group mb-6">
            <MagneticButton onClick={() => handleOpenAuth('register')} className="btn-gradient px-7 py-3 text-sm font-bold shadow-xl shadow-purple-500/30">
              Start Free Trial <ArrowRight className="w-4 h-4 ml-1" />
            </MagneticButton>
            <a href="#how-it-works" className="btn-ghost px-6 py-3 text-sm font-semibold">
              See How It Works
            </a>
          </div>

          {/* Interactive Live URL Simulator */}
          <LiveDemoSimulator />
        </motion.div>

        {/* 3D Scene Centerpiece Container */}
        <div className="hero-3d-wrapper">
          <Hero3DScene />

          {/* Floating Stat Badges */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: [0, -8, 0] }}
            transition={{ duration: 5, repeat: Infinity, ease: 'easeInOut', delay: 0.2 }}
            className="floating-stat-badge top-4 left-2 border-purple-500/40 text-white"
          >
            <div className="w-9 h-9 rounded-full bg-purple-500/20 border border-purple-500/40 flex items-center justify-center text-purple-400">
              🎯
            </div>
            <div>
              <div className="font-extrabold text-sm text-white">98.6% Accuracy</div>
              <div className="text-xs text-slate-400 font-normal">AI Defect Classifier</div>
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: [0, 8, 0] }}
            transition={{ duration: 6, repeat: Infinity, ease: 'easeInOut', delay: 0.8 }}
            className="floating-stat-badge bottom-12 right-2 border-blue-500/40 text-white"
          >
            <div className="w-9 h-9 rounded-full bg-blue-500/20 border border-blue-500/40 flex items-center justify-center text-blue-400">
              ⚡
            </div>
            <div>
              <div className="font-extrabold text-sm text-white">10x Faster QA</div>
              <div className="text-xs text-slate-400 font-normal">Parallel Playwright Workers</div>
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: [0, -6, 0] }}
            transition={{ duration: 4.5, repeat: Infinity, ease: 'easeInOut', delay: 1.4 }}
            className="floating-stat-badge top-1/2 -right-4 border-emerald-500/40 text-white hidden sm:flex"
          >
            <div className="w-9 h-9 rounded-full bg-emerald-500/20 border border-emerald-500/40 flex items-center justify-center text-emerald-400">
              🛡️
            </div>
            <div>
              <div className="font-extrabold text-sm text-white">Zero Flaky Tests</div>
              <div className="text-xs text-slate-400 font-normal">Self-Healing Selectors</div>
            </div>
          </motion.div>
        </div>
      </section>

      {/* TRUST STRIP MARQUEE */}
      <div className="py-12 border-y border-purple-500/15 bg-slate-950/40 backdrop-blur-md">
        <div className="max-w-7xl mx-auto px-6 text-center">
          <p className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-8">
            POWERING HIGH-VELOCITY QA AT TECH LEADERS
          </p>

          <div className="marquee-container">
            <div className="marquee-content">
              {['VERCEL', 'SUPABASE', 'LINEAR', 'STRIPE', 'DATADOG', 'CLOUDFLARE', 'POSTMAN', 'RETOOL', 'VERCEL', 'SUPABASE', 'LINEAR', 'STRIPE'].map((brand, i) => (
                <div key={i} className="partner-logo">
                  <Zap className="w-4 h-4 text-purple-400" />
                  <span>{brand}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* FEATURES SECTION WITH VISUAL SNIPPETS */}
      <section id="features" className="landing-section">
        <div className="section-header">
          <span className="eyebrow-badge">
            <Sparkles className="w-4 h-4 text-purple-400" /> Autonomous Capabilities
          </span>
          <h2 className="section-title">
            Everything QA, <span className="gradient-text">Fully Automated</span>
          </h2>
          <p className="section-subtitle">
            Eliminate fragile manual test writing. Our self-learning agents crawl, generate, execute, and heal your test suites continuously.
          </p>
        </div>

        <div className="features-grid">
          <FeatureCard
            title="Autonomous Discovery"
            description="Playwright crawlers map pages, forms, buttons, accessibility roles, and REST API endpoints automatically."
            icon={<Globe className="w-6 h-6" />}
            // badge="Auto-Crawl"
            animationType="radar"
            interactiveSnippet={
              <div className="text-[11px] font-mono text-purple-300 space-y-1 bg-slate-950/80 p-2.5 rounded-lg border border-purple-500/20">
                <div className="flex items-center gap-1.5"><Globe className="w-3 h-3 text-purple-400" /> <span>https://app.demo</span></div>
                <div className="pl-3 text-slate-400">├── /login [Form: email, pass]</div>
                <div className="pl-3 text-slate-400">└── /checkout [API: /api/pay]</div>
              </div>
            }
          />
          <FeatureCard
            title="AI Test Suite Gen"
            description="Self-hosted Ollama LLM converts DOM structures into realistic multi-step user scenarios and edge case tests."
            icon={<Bot className="w-6 h-6" />}
            // badge="AI Powered"
            animationType="sparkle"
            interactiveSnippet={
              <div className="text-[11px] font-mono text-slate-300 bg-slate-950/80 p-2.5 rounded-lg border border-purple-500/20 flex items-center justify-between">
                <span>test_user_signup_flow.py</span>
                <span className="text-emerald-400 font-bold">Ollama Qwen</span>
              </div>
            }
          />
          <FeatureCard
            title="Self-Healing Tests"
            description="Dynamic selector repair fixes broken CSS/XPath selectors mid-execution whenever your frontend UI code changes."
            icon={<Zap className="w-6 h-6" />}
            // badge="Zero Maintenance"
            animationType="snap"
            interactiveSnippet={
              <div className="text-[11px] font-mono space-y-1 bg-slate-950/80 p-2.5 rounded-lg border border-purple-500/20">
                <div className="text-red-400 line-through">button#submit-v1</div>
                <div className="text-emerald-400 flex items-center gap-1"><CheckCircle2 className="w-3 h-3" /> button[data-testid="pay"]</div>
              </div>
            }
          />
          <FeatureCard
            title="Bug & UI Defect Catch"
            description="Detects functional errors, broken links, visual text overlaps, low color contrast, and element clipping."
            icon={<Activity className="w-6 h-6" />}
            // badge="Smart Vision"
            animationType="pulse"
            interactiveSnippet={
              <div className="text-[11px] font-mono bg-slate-950/80 p-2.5 rounded-lg border border-purple-500/20 flex items-center justify-between">
                <span className="text-amber-300 font-bold">OVERLAP_TEXT</span>
                <span className="px-1.5 py-0.5 rounded bg-red-500/20 text-red-400 border border-red-500/30 text-[10px]">CRITICAL</span>
              </div>
            }
          />
          <FeatureCard
            title="Security Scanner"
            description="Inspects target sites for missing CSP, HSTS, CORS misconfigurations, unencrypted fields, and API vulnerabilities."
            icon={<Shield className="w-6 h-6" />}
            // badge="SecOps Ready"
            animationType="shield"
            interactiveSnippet={
              <div className="text-[11px] font-mono text-emerald-400 bg-slate-950/80 p-2.5 rounded-lg border border-purple-500/20 flex items-center gap-1.5">
                <Shield className="w-3.5 h-3.5 text-emerald-400" />
                <span>100% CSP & CORS Verified</span>
              </div>
            }
          />
          <FeatureCard
            title="Performance Web Vitals"
            description="Captures LCP, CLS, TTFB, and page latency budgets using native browser PerformanceObserver hooks."
            icon={<Cpu className="w-6 h-6" />}
            // badge="Real User Vitals"
            animationType="gauge"
            interactiveSnippet={
              <div className="text-[11px] font-mono text-slate-300 bg-slate-950/80 p-2.5 rounded-lg border border-purple-500/20 flex items-center justify-between">
                <span>LCP: 0.8s</span>
                <span className="text-cyan-400 font-bold">TTFB: 110ms</span>
              </div>
            }
          />
          <FeatureCard
            title="Quality Grade Score"
            description="Computes page coverage, form coverage, flakiness percentages, and overall app health grade (A through F)."
            icon={<Code className="w-6 h-6" />}
            // badge="Grade A-F"
            animationType="chart"
            interactiveSnippet={
              <div className="text-[11px] font-mono text-purple-300 bg-slate-950/80 p-2.5 rounded-lg border border-purple-500/20 flex items-center justify-between">
                <span>App Health Score</span>
                <span className="text-emerald-400 font-extrabold">Grade A (98.6%)</span>
              </div>
            }
          />
          <FeatureCard
            title="Real-Time Alerts"
            description="Live Server-Sent Events (SSE) stream instant failure alerts, step logs, and screenshots directly to your screen."
            icon={<Bell className="w-6 h-6" />}
            // badge="Live Stream"
            animationType="bell"
            interactiveSnippet={
              <div className="text-[11px] font-mono text-slate-300 bg-slate-950/80 p-2.5 rounded-lg border border-purple-500/20 flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                <span>SSE Stream Connected</span>
              </div>
            }
          />
        </div>
      </section>

      {/* 3D AUTONOMOUS QA ARCHITECTURE SECTION */}
      <AutonomousArchitecture3D />

      {/* COMPARISON MATRIX SECTION */}
      <ComparisonSection />

      {/* HOW IT WORKS TIMELINE */}
      <TimelineSection />

      {/* INTEGRATIONS SECTION */}
      <IntegrationsSection />

      {/* TESTIMONIALS SECTION */}
      <TestimonialsSection />

      {/* FINAL CTA BAND */}
      <section className="px-6">
        <div className="final-cta-section">
          <div className="final-cta-blob -top-20 -left-20 w-80 h-80 bg-purple-600/40" />
          <div className="final-cta-blob -bottom-20 -right-20 w-80 h-80 bg-cyan-600/30" />

          <div className="relative z-10 max-w-3xl mx-auto">


            <h2 className="text-4xl md:text-5xl font-extrabold mb-6 tracking-tight shimmer-text">
              Ready to Automate Your QA Engineering?
            </h2>

            <p className="text-lg text-slate-300 mb-10 leading-relaxed">
              Join thousands of developers shipping bug-free software at 10x speed. No complex setup or code changes required.
            </p>

            <div className="flex justify-center">
              <MagneticButton
                onClick={() => handleOpenAuth('register')}
                className="btn-gradient px-10 py-4.5 text-lg font-extrabold shadow-2xl shadow-purple-500/40 inline-flex items-center gap-2"
              >
                <span>Start Free Trial Now</span>
                <ArrowRight className="w-5 h-5" />
              </MagneticButton>
            </div>
          </div>
        </div>
      </section>

      {/* FOOTER */}
      <footer className="landing-footer">
        <div className="footer-container">
          <div className="space-y-4">
            <div className="flex items-center gap-2.5 font-extrabold text-xl text-white">
              <div className="w-8 h-8 rounded-lg bg-gradient-to-r from-blue-600 to-purple-600 flex items-center justify-center text-white text-sm shadow-md">
                ⚡
              </div>
              <span>QA Engineer MVP</span>
            </div>
            <p className="text-sm text-slate-300 max-w-xs leading-relaxed">
              The autonomous Quality Assurance platform that crawls, generates AI tests, self-heals, and catches defects automatically.
            </p>
          </div>

          <div>
            <h4 className="font-bold text-white text-sm mb-4">Product</h4>
            <ul className="space-y-2.5 text-sm text-slate-300 font-medium">
              <li><a href="#features" className="hover:text-purple-300 transition-colors">Autonomous Discovery</a></li>
              <li><a href="#features" className="hover:text-purple-300 transition-colors">AI Test Case Generator</a></li>
              <li><a href="#features" className="hover:text-purple-300 transition-colors">Self-Healing Selectors</a></li>
              <li><a href="#features" className="hover:text-purple-300 transition-colors">Security Scanner</a></li>
            </ul>
          </div>

          <div>
            <h4 className="font-bold text-white text-sm mb-4">Company</h4>
            <ul className="space-y-2.5 text-sm text-slate-300 font-medium">
              <li><a href="#" className="hover:text-purple-300 transition-colors">About Us</a></li>
              <li><a href="#" className="hover:text-purple-300 transition-colors">Careers</a></li>
              <li><a href="#" className="hover:text-purple-300 transition-colors">Blog</a></li>
              <li><a href="#" className="hover:text-purple-300 transition-colors">Contact</a></li>
            </ul>
          </div>

          <div>
            <h4 className="font-bold text-white text-sm mb-4">Resources</h4>
            <ul className="space-y-2.5 text-sm text-slate-300 font-medium">
              <li>
                <a
                  href={(import.meta as any).env.VITE_API_URL ? `${(import.meta as any).env.VITE_API_URL.replace(/\/api\/?$/, '')}/api/docs/` : "/api/docs/"}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:text-purple-300 transition-colors"
                  title="Open Interactive OpenAPI 3.0 Documentation"
                >
                  Documentation
                </a>
              </li>
              <li>
                <a
                  href={(import.meta as any).env.VITE_API_URL ? `${(import.meta as any).env.VITE_API_URL.replace(/\/api\/?$/, '')}/api/docs/` : "/api/docs/"}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:text-purple-300 transition-colors"
                  title="Open Interactive OpenAPI 3.0 Documentation"
                >
                  Playwright Integration
                </a>
              </li>
              <li>
                <a
                  href={(import.meta as any).env.VITE_API_URL ? `${(import.meta as any).env.VITE_API_URL.replace(/\/api\/?$/, '')}/api/docs/` : "/api/docs/"}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:text-purple-300 transition-colors"
                  title="Open Interactive OpenAPI 3.0 Documentation"
                >
                  API Reference
                </a>
              </li>
              <li>
                <a
                  href={(import.meta as any).env.VITE_API_URL ? `${(import.meta as any).env.VITE_API_URL.replace(/\/api\/?$/, '')}/api/docs/` : "/api/docs/"}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:text-purple-300 transition-colors"
                  title="Open Interactive OpenAPI 3.0 Documentation"
                >
                  Community Discord
                </a>
              </li>
            </ul>
          </div>

          <div>
            <h4 className="font-bold text-white text-sm mb-4">Legal</h4>
            <ul className="space-y-2.5 text-sm text-slate-300 font-medium">
              <li><a href="#" className="hover:text-purple-300 transition-colors">Privacy Policy</a></li>
              <li><a href="#" className="hover:text-purple-300 transition-colors">Terms of Service</a></li>
              <li><a href="#" className="hover:text-purple-300 transition-colors">Security</a></li>
            </ul>
          </div>
        </div>

        <div className="max-w-7xl mx-auto px-6 pt-12 mt-12 border-t border-purple-500/20 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-slate-400">
          <div>
            © 2026 QA Engineer MVP, Inc. All rights reserved.
          </div>
          <div className="flex items-center gap-6">
            <a href="#" className="hover:text-white transition-colors" title="Global Web"><Globe className="w-4 h-4 text-slate-300" /></a>
            <a href="#" className="hover:text-white transition-colors" title="Community"><MessageSquare className="w-4 h-4 text-slate-300" /></a>
            <a href="#" className="hover:text-white transition-colors" title="Share"><Share2 className="w-4 h-4 text-slate-300" /></a>
          </div>
        </div>
      </footer>

      {/* AUTH MODAL OVERLAY */}
      <AnimatePresence>
        {showAuthModal && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="auth-modal-overlay"
            onClick={handleCloseModal}
          >
            <motion.div
              initial={{ scale: 0.9, y: 20, opacity: 0 }}
              animate={{ scale: 1, y: 0, opacity: 1 }}
              exit={{ scale: 0.9, y: 20, opacity: 0 }}
              transition={{ type: 'spring', damping: 25, stiffness: 300 }}
              className="auth-modal-card"
              onClick={(e) => e.stopPropagation()}
            >
              <button
                onClick={handleCloseModal}
                className="absolute top-4 right-4 p-2 text-slate-400 hover:text-white rounded-full hover:bg-purple-900/30 transition-colors"
                aria-label="Close modal"
              >
                <X className="w-5 h-5" />
              </button>

              {/* Top Title & Logo Header */}
              <div className="text-center mb-6 pt-2">
                <div className="w-12 h-12 rounded-2xl bg-gradient-to-r from-blue-600 to-purple-600 text-white flex items-center justify-center font-extrabold text-xl mx-auto mb-3 shadow-lg shadow-purple-500/30">
                  ⚡
                </div>
                <h3 className="text-2xl md:text-3xl font-black text-white tracking-tight">
                  {isLoginMode ? 'Welcome Back' : 'Create QA Space'}
                </h3>
                <p className="text-xs md:text-sm text-slate-300 font-medium mt-1">
                  {isLoginMode ? 'Log in to manage your automated test runs' : 'Register your developer space to begin testing'}
                </p>
              </div>

              {/* Mode Switcher Tabs with Prominent Big Buttons */}
              <div className="grid grid-cols-2 p-1.5 bg-slate-950 rounded-2xl mb-6 border-2 border-purple-500/30 shadow-xl gap-2">
                <button
                  type="button"
                  onClick={() => {
                    setIsLoginMode(true);
                    navigate('/login');
                  }}
                  className={`py-3.5 px-4 text-sm md:text-base font-black rounded-xl transition-all cursor-pointer text-center ${isLoginMode
                    ? 'bg-gradient-to-r from-blue-600 via-purple-600 to-purple-600 text-white shadow-xl shadow-purple-500/40 border border-purple-400/50'
                    : 'bg-slate-900/90 text-slate-200 hover:text-white hover:bg-slate-800/80 border border-purple-500/20'
                    }`}
                >
                  Log In
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setIsLoginMode(false);
                    navigate('/signup');
                  }}
                  className={`py-3.5 px-4 text-sm md:text-base font-black rounded-xl transition-all cursor-pointer text-center ${!isLoginMode
                    ? 'bg-gradient-to-r from-blue-600 via-purple-600 to-purple-600 text-white shadow-xl shadow-purple-500/40 border border-purple-400/50'
                    : 'bg-slate-900/90 text-slate-200 hover:text-white hover:bg-slate-800/80 border border-purple-500/20'
                    }`}
                >
                  Sign Up Free
                </button>
              </div>

              {authError && (
                <div className="mb-5 p-3.5 rounded-xl bg-red-950/80 border border-red-500/50 text-red-200 text-sm font-semibold flex items-center gap-2">
                  <AlertCircle className="w-4.5 h-4.5 shrink-0 text-red-400" />
                  <span>{authError}</span>
                </div>
              )}
              {authSuccess && (
                <div className="mb-5 p-3.5 rounded-xl bg-emerald-950/80 border border-emerald-500/50 text-emerald-200 text-sm font-semibold flex items-center gap-2">
                  <CheckCircle2 className="w-4.5 h-4.5 shrink-0 text-emerald-400" />
                  <span>{authSuccess}</span>
                </div>
              )}

              <form onSubmit={handleFormSubmit} className="space-y-5">
                {!isLoginMode && (
                  <div>
                    <label className="block text-xs font-bold text-slate-200 uppercase tracking-wider mb-2">
                      Username *
                    </label>
                    <div className="auth-input-group">
                      <UserIcon className="auth-input-icon" />
                      <input
                        type="text"
                        required
                        value={username}
                        onChange={(e) => setUsername(e.target.value)}
                        placeholder="qa_engineer"
                      />
                    </div>
                  </div>
                )}

                <div>
                  <label className="block text-xs font-bold text-slate-200 uppercase tracking-wider mb-2">
                    Email Address *
                  </label>
                  <div className="auth-input-group">
                    <Mail className="auth-input-icon" />
                    <input
                      type="email"
                      required
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="name@company.com"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-bold text-slate-200 uppercase tracking-wider mb-2">
                    Password *
                  </label>
                  <div className="auth-input-group">
                    <Lock className="auth-input-icon" />
                    <input
                      type={showPassword ? 'text' : 'password'}
                      required
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="••••••••••••"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute right-3.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white p-1 z-10 cursor-pointer"
                    >
                      {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                </div>

                <button
                  type="submit"
                  disabled={authLoading}
                  className="w-full py-4.5 rounded-2xl bg-gradient-to-r from-blue-600 via-purple-600 to-cyan-500 hover:from-blue-500 hover:to-purple-500 text-white font-black text-base md:text-lg shadow-2xl shadow-purple-500/40 border border-purple-400/30 transition-all disabled:opacity-50 mt-6 cursor-pointer"
                >
                  {authLoading ? 'Processing...' : isLoginMode ? 'Log In to QA Space' : 'Create Free Account'}
                </button>
              </form>

              <div className="text-center mt-6 pt-5 border-t border-purple-500/20">
                <button
                  type="button"
                  onClick={() => {
                    const nextMode = !isLoginMode;
                    setIsLoginMode(nextMode);
                    navigate(nextMode ? '/login' : '/signup');
                  }}
                  className="text-xs md:text-sm font-bold text-purple-300 hover:text-purple-200 transition-colors cursor-pointer"
                >
                  {isLoginMode ? "Don't have an account? Sign up free" : 'Already registered? Log in'}
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
