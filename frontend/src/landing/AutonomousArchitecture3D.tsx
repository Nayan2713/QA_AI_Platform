import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { ShieldCheck, Cpu, Globe, CheckCircle2, Zap, Lock, Sparkles, Terminal, Activity } from 'lucide-react';

export function AutonomousArchitecture3D() {
  const [rotateX, setRotateX] = useState(0);
  const [rotateY, setRotateY] = useState(0);
  const [activeNode, setActiveNode] = useState<number | null>(null);

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    const card = e.currentTarget.getBoundingClientRect();
    const centerX = card.left + card.width / 2;
    const centerY = card.top + card.height / 2;
    const mouseX = e.clientX - centerX;
    const mouseY = e.clientY - centerY;

    // Subtle 3D tilt calculation (max +/- 10 deg)
    const rY = (mouseX / (card.width / 2)) * 8;
    const rX = -(mouseY / (card.height / 2)) * 8;

    setRotateX(rX);
    setRotateY(rY);
  };

  const handleMouseLeave = () => {
    setRotateX(0);
    setRotateY(0);
    setActiveNode(null);
  };

  const nodes = [
    {
      id: 1,
      title: 'DOM & App Discovery',
      status: 'Mapped 100% ✓',
      icon: <Globe className="w-5 h-5 text-emerald-400" />,
      color: 'emerald',
      positionClass: 'top-4 left-4 sm:top-8 sm:left-8',
      floatAnim: { y: [-6, 6, -6] },
      floatDuration: 4.2,
      activeBorder: 'border-emerald-400/80 shadow-emerald-500/40',
      badgeBg: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/40',
      pulseColor: '#10B981',
    },
    {
      id: 2,
      title: 'Ollama AI Test Gen',
      status: 'Scenarios Secured',
      icon: <Cpu className="w-5 h-5 text-blue-400" />,
      color: 'blue',
      positionClass: 'top-4 right-4 sm:top-8 sm:right-8',
      floatAnim: { y: [6, -6, 6] },
      floatDuration: 4.8,
      activeBorder: 'border-blue-400/80 shadow-blue-500/40',
      badgeBg: 'bg-blue-500/15 text-blue-300 border-blue-500/40',
      pulseColor: '#3B82F6',
    },
    {
      id: 3,
      title: 'Self-Healing Engine',
      status: 'Zero Flaky Selectors',
      icon: <Zap className="w-5 h-5 text-purple-400" />,
      color: 'purple',
      positionClass: 'bottom-4 left-4 sm:bottom-8 sm:left-8',
      floatAnim: { y: [5, -7, 5] },
      floatDuration: 3.9,
      activeBorder: 'border-purple-400/80 shadow-purple-500/40',
      badgeBg: 'bg-purple-500/15 text-purple-300 border-purple-500/40',
      pulseColor: '#A855F7',
    },
    {
      id: 4,
      title: 'Security & UI Audit',
      status: 'Audit Attached',
      icon: <Lock className="w-5 h-5 text-cyan-400" />,
      color: 'cyan',
      positionClass: 'bottom-4 right-4 sm:bottom-8 sm:right-8',
      floatAnim: { y: [-7, 5, -7] },
      floatDuration: 4.5,
      activeBorder: 'border-cyan-400/80 shadow-cyan-500/40',
      badgeBg: 'bg-cyan-500/15 text-cyan-300 border-cyan-500/40',
      pulseColor: '#06B6D4',
    },
  ];

  return (
    <section className="w-full max-w-5xl mx-auto py-16 px-4 flex flex-col items-center justify-center text-center relative z-10">
      <div className="section-header text-center mb-12 max-w-2xl mx-auto">
        <div className="eyebrow-badge mb-3">
          <Sparkles className="w-4 h-4 text-purple-400" />
          <span>Real-Time Autonomous Architecture</span>
        </div>
        <h2 className="section-title">
          3D Orchestration of Every QA Layer
        </h2>
        <p className="section-subtitle">
          Continuous background scanning, dynamic selector repair, AI test generation, and deep visual audit synced in one central hub.
        </p>
      </div>

      {/* 3D Glass Interactive Stage Container */}
      <div
        className="w-full max-w-4xl mx-auto flex justify-center items-center perspective-1000"
        style={{ perspective: '1000px' }}
        onMouseMove={handleMouseMove}
        onMouseLeave={handleMouseLeave}
      >
        <motion.div
          animate={{
            rotateX,
            rotateY,
          }}
          transition={{ type: 'spring', stiffness: 220, damping: 22 }}
          className="relative w-full rounded-3xl bg-slate-950/85 border-2 border-purple-500/35 p-6 sm:p-12 shadow-2xl backdrop-blur-2xl min-h-[460px] sm:min-h-[520px] flex items-center justify-center overflow-visible"
          style={{ transformStyle: 'preserve-3d' }}
        >
          {/* Subtle Ambient Background Gradients */}
          <div className="absolute inset-0 rounded-3xl bg-gradient-to-tr from-purple-950/30 via-slate-950/90 to-cyan-950/30 pointer-events-none" />
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-80 h-80 bg-purple-500/15 blur-3xl rounded-full pointer-events-none" />

          {/* Floating Background Ambient Particles */}
          {[...Array(6)].map((_, i) => (
            <motion.div
              key={i}
              animate={{
                y: [0, -20, 0],
                x: [0, i % 2 === 0 ? 15 : -15, 0],
                opacity: [0.3, 0.8, 0.3],
              }}
              transition={{
                duration: 5 + i * 1.2,
                repeat: Infinity,
                ease: 'easeInOut',
                delay: i * 0.8,
              }}
              className="absolute w-2 h-2 rounded-full bg-cyan-400/40 pointer-events-none"
              style={{
                top: `${20 + i * 12}%`,
                left: `${15 + (i * 14) % 70}%`,
              }}
            />
          ))}

          {/* Concentric Pulsing Radar Orbit Rings */}
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-56 sm:w-72 h-56 sm:h-72 rounded-full border border-dashed border-purple-500/40 pointer-events-none" />
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-80 sm:w-[380px] h-80 sm:h-[380px] rounded-full border border-purple-500/20 pointer-events-none" />

          {/* Continuous Rotating Radar Sweep Beam */}
          <motion.div
            animate={{ rotate: 360 }}
            transition={{ duration: 10, repeat: Infinity, ease: 'linear' }}
            className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-64 sm:w-88 h-64 sm:h-88 pointer-events-none"
          >
            <div
              className="w-1/2 h-1/2 origin-bottom-right"
              style={{
                background: 'conic-gradient(from 0deg at 100% 100%, rgba(168, 85, 247, 0.3) 0deg, rgba(6, 182, 212, 0.1) 45deg, transparent 90deg)',
              }}
            />
          </motion.div>

          {/* Dotted Connecting Lines to Satellite Quadrants */}
          <svg className="absolute inset-0 w-full h-full pointer-events-none stroke-purple-500/35" style={{ strokeDasharray: '4 4' }}>
            <line x1="50%" y1="50%" x2="20%" y2="20%" strokeWidth="1.5" />
            <line x1="50%" y1="50%" x2="80%" y2="20%" strokeWidth="1.5" />
            <line x1="50%" y1="50%" x2="20%" y2="80%" strokeWidth="1.5" />
            <line x1="50%" y1="50%" x2="80%" y2="80%" strokeWidth="1.5" />
          </svg>

          {/* CENTRAL NODE: Autonomous AI QA Hub with Pulsing Rings & 3D Z-Elevation */}
          <div className="relative z-20 flex items-center justify-center" style={{ transform: 'translateZ(50px)' }}>
            <motion.div
              animate={{ scale: [1, 1.35, 1], opacity: [0.6, 0, 0.6] }}
              transition={{ duration: 3, repeat: Infinity, ease: 'easeInOut' }}
              className="absolute w-36 h-36 rounded-full border-2 border-cyan-400/50 pointer-events-none"
            />
            <motion.div
              animate={{ scale: [1, 1.25, 1], opacity: [0.5, 0.1, 0.5] }}
              transition={{ duration: 3, repeat: Infinity, ease: 'easeInOut', delay: 0.5 }}
              className="absolute w-44 h-44 rounded-full border border-purple-400/40 pointer-events-none"
            />

            <motion.div
              whileHover={{ scale: 1.1, rotateZ: 2 }}
              className="relative w-28 h-28 sm:w-36 sm:h-36 rounded-3xl bg-gradient-to-b from-slate-900 via-purple-950/90 to-slate-950 border-2 border-purple-400/70 flex flex-col items-center justify-center p-4 shadow-2xl shadow-purple-500/50 cursor-pointer text-center"
            >
              <div className="absolute -inset-1 rounded-3xl bg-gradient-to-r from-blue-600 via-purple-600 to-cyan-500 opacity-60 blur-md animate-pulse pointer-events-none" />
              <div className="relative z-10 w-11 h-11 sm:w-14 sm:h-14 rounded-2xl bg-gradient-to-tr from-purple-600 via-indigo-600 to-cyan-500 flex items-center justify-center text-white text-2xl font-black mb-1.5 shadow-lg shadow-purple-500/40">
                ⚡
              </div>
              <div className="relative z-10 text-[11px] sm:text-xs font-black text-white tracking-wider uppercase">
                AI QA Core
              </div>
              <div className="relative z-10 text-[9px] sm:text-[10px] font-bold text-emerald-400 flex items-center gap-0.5 mt-0.5">
                <CheckCircle2 className="w-3 h-3 text-emerald-400 inline shrink-0" /> Verified
              </div>
            </motion.div>
          </div>

          {/* 4 SATELLITE FLOATING & DRAGGABLE UNBOXED NODES WITH 3D MOTION */}
          {nodes.map((node) => (
            <motion.div
              key={node.id}
              drag
              dragConstraints={{ left: -70, right: 70, top: -70, bottom: 70 }}
              dragElastic={0.2}
              animate={node.floatAnim}
              transition={{ duration: node.floatDuration, repeat: Infinity, ease: 'easeInOut' }}
              onHoverStart={() => setActiveNode(node.id)}
              onHoverEnd={() => setActiveNode(null)}
              whileHover={{ scale: 1.1, zIndex: 40 }}
              whileDrag={{ scale: 1.15, zIndex: 50, cursor: 'grabbing' }}
              className={`absolute z-20 ${node.positionClass} flex items-center gap-3 cursor-grab select-none transition-all drop-shadow-xl`}
              style={{ transform: 'translateZ(40px)' }}
            >
              <div className="w-10 h-10 sm:w-11 sm:h-11 rounded-2xl bg-slate-900/90 border border-purple-400/40 flex items-center justify-center shrink-0 shadow-lg shadow-purple-500/20 backdrop-blur-md">
                {node.icon}
              </div>
              <div className="text-left whitespace-nowrap">
                <div className="text-xs sm:text-sm font-extrabold text-white drop-shadow-md">
                  {node.title}
                </div>
                <div
                  className={`text-[10px] sm:text-xs font-bold mt-0.5 ${
                    node.color === 'emerald'
                      ? 'text-emerald-400'
                      : node.color === 'blue'
                      ? 'text-blue-400'
                      : node.color === 'purple'
                      ? 'text-purple-300'
                      : 'text-cyan-400'
                  } drop-shadow-sm flex items-center gap-1`}
                >
                  {node.status}
                </div>
              </div>
            </motion.div>
          ))}
        </motion.div>
      </div>
    </section>
  );
}
