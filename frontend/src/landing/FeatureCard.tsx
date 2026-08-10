import React, { useRef, useState } from 'react';
import { motion, TargetAndTransition } from 'framer-motion';

interface FeatureCardProps {
  title: string;
  description: string;
  icon: React.ReactNode;
  badge?: string;
  animationType: 'radar' | 'pulse' | 'snap' | 'sparkle' | 'shield' | 'gauge' | 'chart' | 'bell';
  interactiveSnippet?: React.ReactNode;
}

export function FeatureCard({
  title,
  description,
  icon,
  badge,
  animationType,
  interactiveSnippet,
}: FeatureCardProps) {
  const cardRef = useRef<HTMLDivElement>(null);
  const [rotX, setRotX] = useState(0);
  const [rotY, setRotY] = useState(0);

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!cardRef.current) return;
    const rect = cardRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    const centerX = rect.width / 2;
    const centerY = rect.height / 2;

    const rotateX = ((y - centerY) / centerY) * -10;
    const rotateY = ((x - centerX) / centerX) * 10;

    setRotX(rotateX);
    setRotY(rotateY);

    cardRef.current.style.setProperty('--mouse-x', `${x}px`);
    cardRef.current.style.setProperty('--mouse-y', `${y}px`);
  };

  const handleMouseLeave = () => {
    setRotX(0);
    setRotY(0);
  };

  const getIconAnimation = (): TargetAndTransition => {
    switch (animationType) {
      case 'radar':
        return { rotate: [0, 360], transition: { duration: 6, repeat: Infinity, ease: 'linear' as const } };
      case 'pulse':
        return { scale: [1, 1.2, 1], transition: { duration: 2, repeat: Infinity, ease: 'easeInOut' as const } };
      case 'snap':
        return { y: [0, -6, 0], rotate: [0, -8, 0], transition: { duration: 1.8, repeat: Infinity, ease: 'easeInOut' as const } };
      case 'shield':
        return { scale: [1, 1.15, 1], rotate: [0, 5, -5, 0], transition: { duration: 2.5, repeat: Infinity, ease: 'easeInOut' as const } };
      case 'sparkle':
        return { opacity: [0.7, 1, 0.7], scale: [0.95, 1.1, 0.95], transition: { duration: 1.5, repeat: Infinity } };
      case 'gauge':
        return { rotate: [-15, 15, -15], transition: { duration: 3, repeat: Infinity, ease: 'easeInOut' as const } };
      case 'chart':
        return { y: [0, -4, 0], transition: { duration: 2, repeat: Infinity, ease: 'easeInOut' as const } };
      case 'bell':
        return { rotate: [0, 15, -15, 10, -10, 0], transition: { duration: 2, repeat: Infinity, repeatDelay: 1 } };
      default:
        return {};
    }
  };

  return (
    <div
      ref={cardRef}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
      className="feature-card"
      style={{
        transform: `perspective(1000px) rotateX(${rotX}deg) rotateY(${rotY}deg)`,
      }}
    >
      <div className="card-spotlight" />

      <div className="flex items-start justify-between">
        <motion.div className="feature-icon-wrapper" animate={getIconAnimation()}>
          {icon}
        </motion.div>

        {badge && (
          <span className="text-xs font-bold px-3 py-1 rounded-full bg-purple-950/80 text-purple-200 border border-purple-500/40 font-mono tracking-wide">
            {badge}
          </span>
        )}
      </div>

      <h3 className="feature-title text-xl font-extrabold text-white mt-2">{title}</h3>
      <p className="feature-desc text-slate-200 text-sm md:text-base leading-relaxed mb-4">{description}</p>

      {/* Optional Interactive Visual Snippet */}
      {interactiveSnippet && (
        <div className="mt-auto pt-3.5 border-t border-purple-500/20">
          {interactiveSnippet}
        </div>
      )}
    </div>
  );
}
