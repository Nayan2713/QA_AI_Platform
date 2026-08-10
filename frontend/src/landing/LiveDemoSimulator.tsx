import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Search, Play, CheckCircle2, AlertTriangle, ShieldCheck, Cpu, ArrowRight, RefreshCw, Zap } from 'lucide-react';

export function LiveDemoSimulator() {
  const [targetUrl, setTargetUrl] = useState('https://my-app.com');
  const [isScanning, setIsScanning] = useState(false);
  const [scanStep, setScanStep] = useState<number>(0); // 0: idle, 1: crawling, 2: generating, 3: executing, 4: complete

  const handleStartScan = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (isScanning) return;

    setIsScanning(true);
    setScanStep(1);

    // Step sequence timer simulation
    setTimeout(() => setScanStep(2), 1200);
    setTimeout(() => setScanStep(3), 2600);
    setTimeout(() => {
      setScanStep(4);
      setIsScanning(false);
    }, 4200);
  };

  const handleReset = () => {
    setIsScanning(false);
    setScanStep(0);
  };

  return (
    <div className="live-demo-card">
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-2.5">
          <span className="w-3.5 h-3.5 rounded-full bg-red-500 inline-block shadow-md shadow-red-500/50" />
          <span className="w-3.5 h-3.5 rounded-full bg-amber-500 inline-block shadow-md shadow-amber-500/50" />
          <span className="w-3.5 h-3.5 rounded-full bg-emerald-500 inline-block shadow-md shadow-emerald-500/50" />
          <span className="text-sm font-mono text-purple-200 ml-2 font-bold tracking-wide">
            Interactive AI QA Simulator
          </span>
        </div>
        {scanStep === 4 && (
          <button
            onClick={handleReset}
            className="text-xs md:text-sm font-bold text-purple-300 hover:text-white flex items-center gap-1.5 transition-colors cursor-pointer px-3 py-1.5 rounded-lg bg-purple-950/80 border border-purple-500/30"
          >
            <RefreshCw className="w-4 h-4" /> Reset Demo
          </button>
        )}
      </div>

      {/* URL Input Bar */}
      <form onSubmit={handleStartScan} className="relative flex items-center mb-4" style={{ width: '100%' }}>
        <Search
          className="w-4 h-4 text-purple-400 absolute pointer-events-none z-10"
          style={{ left: '14px', top: '50%', transform: 'translateY(-50%)' }}
        />
        <input
          type="url"
          value={targetUrl}
          onChange={(e) => setTargetUrl(e.target.value)}
          disabled={isScanning}
          placeholder="Enter website URL (e.g. https://my-app.com)"
          className="w-full rounded-xl bg-slate-950/95 border border-purple-500/40 text-white font-mono text-xs sm:text-sm placeholder-slate-500 focus:outline-none focus:border-purple-400 transition-colors shadow-inner"
          style={{
            paddingLeft: '44px',
            paddingRight: '115px',
            paddingTop: '11px',
            paddingBottom: '11px',
            lineHeight: '1.2'
          }}
        />
        <button
          type="submit"
          disabled={isScanning}
          className="absolute px-3 sm:px-4 py-1.5 rounded-lg bg-gradient-to-r from-blue-600 via-purple-600 to-cyan-500 hover:from-blue-500 hover:to-purple-500 text-white font-bold text-xs shadow-md shadow-purple-500/30 transition-all flex items-center gap-1.5 disabled:opacity-50 cursor-pointer whitespace-nowrap z-10"
          style={{ right: '6px', top: '50%', transform: 'translateY(-50%)' }}
        >
          {isScanning ? (
            <>
              <RefreshCw className="w-3.5 h-3.5 animate-spin" /> <span>Scanning...</span>
            </>
          ) : (
            <>
              <Play className="w-3.5 h-3.5 fill-current" /> Run Test
            </>
          )}
        </button>
      </form>

      {/* Quick URL Preset Chips */}
      {scanStep === 0 && (
        <div className="flex items-center gap-1.5 sm:gap-2 mb-3 flex-wrap">
          <span className="text-[10px] sm:text-xs text-slate-400 font-bold uppercase tracking-wider">Try presets:</span>
          {['https://e-commerce-shop.demo', 'https://saas-dashboard.demo', 'https://fintech-api.demo'].map((preset) => (
            <button
              key={preset}
              type="button"
              onClick={() => {
                setTargetUrl(preset);
                handleStartScan();
              }}
              className="text-[10px] sm:text-xs px-2 sm:px-2.5 py-0.5 sm:py-1 rounded-md bg-purple-950/70 border border-purple-500/30 text-purple-300 hover:bg-purple-900/90 hover:text-white transition-all font-mono font-medium cursor-pointer"
            >
              {preset.replace('https://', '')}
            </button>
          ))}
        </div>
      )}

      {/* Scan Progress & Interactive Simulator Results */}
      <AnimatePresence mode="wait">
        {scanStep > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="space-y-3.5 sm:space-y-4 pt-3.5 sm:pt-4 border-t border-purple-500/20"
          >
            {/* Step 1: DOM Crawling */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between text-xs sm:text-base font-mono gap-1 sm:gap-2">
              <div className="flex items-center gap-2 sm:gap-2.5 text-slate-100 font-semibold">
                {scanStep > 1 ? (
                  <CheckCircle2 className="w-4 h-4 sm:w-5 sm:h-5 text-emerald-400 shrink-0" />
                ) : (
                  <RefreshCw className="w-4 h-4 sm:w-5 sm:h-5 text-blue-400 animate-spin shrink-0" />
                )}
                <span>1. Autonomous Playwright Crawler</span>
              </div>
              <span className="text-slate-300 font-medium pl-6 sm:pl-0 text-[11px] sm:text-sm">
                {scanStep > 1 ? '3 pages & 8 forms mapped' : 'Discovering DOM...'}
              </span>
            </div>

            {/* Step 2: Ollama AI Test Gen */}
            {scanStep >= 2 && (
              <motion.div
                initial={{ opacity: 0, y: 5 }}
                animate={{ opacity: 1, y: 0 }}
                className="flex flex-col sm:flex-row sm:items-center justify-between text-xs sm:text-base font-mono gap-1 sm:gap-2"
              >
                <div className="flex items-center gap-2 sm:gap-2.5 text-slate-100 font-semibold">
                  {scanStep > 2 ? (
                    <CheckCircle2 className="w-4 h-4 sm:w-5 sm:h-5 text-emerald-400 shrink-0" />
                  ) : (
                    <RefreshCw className="w-4 h-4 sm:w-5 sm:h-5 text-purple-400 animate-spin shrink-0" />
                  )}
                  <span>2. Ollama AI Test Case Generator</span>
                </div>
                <span className="text-slate-300 font-medium pl-6 sm:pl-0 text-[11px] sm:text-sm">
                  {scanStep > 2 ? '5 end-to-end scenarios' : 'Constructing tests...'}
                </span>
              </motion.div>
            )}

            {/* Step 3: Self-Healing Execution */}
            {scanStep >= 3 && (
              <motion.div
                initial={{ opacity: 0, y: 5 }}
                animate={{ opacity: 1, y: 0 }}
                className="flex flex-col sm:flex-row sm:items-center justify-between text-xs sm:text-base font-mono gap-1 sm:gap-2"
              >
                <div className="flex items-center gap-2 sm:gap-2.5 text-slate-100 font-semibold">
                  {scanStep > 3 ? (
                    <CheckCircle2 className="w-4 h-4 sm:w-5 sm:h-5 text-emerald-400 shrink-0" />
                  ) : (
                    <RefreshCw className="w-4 h-4 sm:w-5 sm:h-5 text-cyan-400 animate-spin shrink-0" />
                  )}
                  <span>3. Playwright Execution & Self-Healing</span>
                </div>
                <span className="text-cyan-300 font-extrabold pl-6 sm:pl-0 text-[11px] sm:text-sm">
                  {scanStep > 3 ? 'Auto-healed 1 broken selector' : 'Running steps...'}
                </span>
              </motion.div>
            )}

            {/* Step 4: Final Results Summary Badge */}
            {scanStep === 4 && (
              <motion.div
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                className="mt-4 sm:mt-5 p-4 sm:p-6 rounded-2xl bg-gradient-to-r from-purple-950/80 via-slate-950/95 to-blue-950/80 border-2 border-purple-500/40 flex flex-col sm:flex-row sm:items-center justify-between gap-3 sm:gap-4 shadow-xl"
              >
                <div className="flex items-center gap-3 sm:gap-4">
                  <div className="w-11 h-11 sm:w-14 sm:h-14 rounded-2xl bg-emerald-500/20 border-2 border-emerald-500/50 flex items-center justify-center text-emerald-300 font-black text-xl sm:text-2xl shadow-lg shrink-0">
                    A
                  </div>
                  <div>
                    <div className="font-black text-white text-sm sm:text-xl leading-snug">Quality Grade A (98.6%)</div>
                    <div className="text-[11px] sm:text-sm text-slate-200 font-medium mt-0.5">5 Passed · 0 Failed · 1 Security Header Notice</div>
                  </div>
                </div>

                <div className="text-left sm:text-right">
                  <span className="text-[10px] sm:text-sm font-black px-3 sm:px-4 py-1.5 sm:py-2 rounded-full bg-emerald-500/25 text-emerald-300 border border-emerald-500/50 uppercase tracking-wider shadow-md inline-block">
                    PASSED
                  </span>
                </div>
              </motion.div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
