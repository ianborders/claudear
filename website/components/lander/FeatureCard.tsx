'use client';

import { motion } from 'framer-motion';
import { type ReactNode } from 'react';
import { TopoPattern } from './TopoPattern';

interface FeatureCardProps {
  children: ReactNode;
  className?: string;
  variant?: 'default' | 'accent' | 'dark';
  hover?: boolean;
}

export function FeatureCard({
  children,
  className = '',
  variant = 'default',
  hover = true,
}: FeatureCardProps) {
  const baseStyles = 'rounded-xl p-6 transition-all duration-300 relative overflow-hidden';

  const variantStyles = {
    default: 'bg-white border border-gray-200 shadow-sm',
    accent: 'bg-gradient-to-br from-emerald-50 to-cyan-50 border border-emerald-200/50',
    dark: 'bg-[#0a0a0a] border border-white/15',
  };

  const hoverStyles = hover
    ? 'hover:shadow-lg hover:-translate-y-1'
    : '';

  return (
    <motion.div
      className={`${baseStyles} ${variantStyles[variant]} ${hoverStyles} ${className}`}
      whileHover={hover ? { scale: 1.02 } : undefined}
      transition={{ duration: 0.2 }}
    >
      <div className="relative z-10">{children}</div>
    </motion.div>
  );
}

// Step card for "How It Works" section
interface StepCardProps {
  number: string;
  label: string;
  title: string;
  description: string;
  accentColor?: 'cyan' | 'emerald';
  className?: string;
  topoSeed?: number;
}

export function StepCard({
  number,
  label,
  title,
  description,
  accentColor = 'cyan',
  className = '',
  topoSeed = 1,
}: StepCardProps) {
  const colors = {
    cyan: {
      border: 'border-cyan-500/30',
      bg: 'bg-cyan-500/10',
      text: 'text-cyan-600',
      numberBorder: 'border-cyan-500/50',
      numberBg: 'bg-cyan-500/10',
      topo: '#9ca3af',
    },
    emerald: {
      border: 'border-emerald-500/30',
      bg: 'bg-emerald-500/10',
      text: 'text-emerald-600',
      numberBorder: 'border-emerald-500/50',
      numberBg: 'bg-emerald-500/10',
      topo: '#9ca3af',
    },
  };

  const c = colors[accentColor];

  // Vary complexity based on seed for variety
  const complexities: ('simple' | 'medium' | 'complex')[] = ['simple', 'medium', 'complex'];
  const complexity = complexities[topoSeed % complexities.length];

  return (
    <motion.div
      className={`bg-white rounded-xl p-6 border border-gray-200 shadow-sm hover:shadow-lg transition-all duration-300 relative overflow-hidden h-full flex flex-col ${className}`}
      whileHover={{ y: -4, scale: 1.01 }}
      transition={{ duration: 0.2 }}
    >
      <TopoPattern
        seed={topoSeed * 17}
        complexity={complexity}
        color={c.topo}
        opacity={0.15}
      />
      <div className="relative z-10 flex flex-col flex-1">
        <div className="flex items-center gap-3 mb-4">
          <div
            className={`w-8 h-8 rounded-full ${c.numberBorder} ${c.numberBg} flex items-center justify-center ${c.text} text-xs font-bold font-mono`}
          >
            {number}
          </div>
          <div className={`text-[10px] ${c.text} tracking-[2px] font-mono uppercase`}>
            {label}
          </div>
        </div>
        <h3
          className="text-lg text-gray-900 mb-2"
          style={{ fontWeight: 500 }}
        >
          {title}
        </h3>
        <p
          className="text-sm text-gray-600 leading-relaxed flex-1"
          style={{ fontWeight: 300 }}
        >
          {description}
        </p>
      </div>
    </motion.div>
  );
}

// Icon feature card for grid layouts
interface IconFeatureCardProps {
  icon: ReactNode;
  label: string;
  description: string;
  accentColor?: 'cyan' | 'emerald';
  className?: string;
  topoSeed?: number;
}

export function IconFeatureCard({
  icon,
  label,
  description,
  accentColor = 'emerald',
  className = '',
  topoSeed = 1,
}: IconFeatureCardProps) {
  const colors = {
    cyan: { text: 'text-cyan-600 group-hover:text-cyan-500' },
    emerald: { text: 'text-emerald-600 group-hover:text-emerald-500' },
  };

  // Vary complexity based on seed for variety
  const complexities: ('simple' | 'medium' | 'complex')[] = ['simple', 'medium', 'complex'];
  const complexity = complexities[topoSeed % complexities.length];

  return (
    <motion.div
      className={`group bg-white rounded-xl p-6 border border-gray-200 shadow-sm hover:shadow-md transition-all duration-300 relative overflow-hidden h-full flex flex-col ${className}`}
      whileHover={{ y: -2 }}
      transition={{ duration: 0.2 }}
    >
      <TopoPattern
        seed={topoSeed * 23}
        complexity={complexity}
        color="#9ca3af"
        opacity={0.15}
      />
      <div className="relative z-10 flex flex-col flex-1">
        <div className="flex items-start justify-between mb-4">
          <div className={`text-[9px] ${colors[accentColor].text} tracking-[2px] font-mono uppercase`}>
            {label}
          </div>
          <div className="text-gray-400 group-hover:text-gray-600 transition-colors">
            {icon}
          </div>
        </div>
        <p
          className="text-sm text-gray-600 leading-relaxed flex-1"
          style={{ fontWeight: 300 }}
        >
          {description}
        </p>
      </div>
    </motion.div>
  );
}

// Large callout card
interface CalloutCardProps {
  children: ReactNode;
  variant?: 'cyan' | 'emerald';
  className?: string;
}

export function CalloutCard({
  children,
  variant = 'cyan',
  className = '',
}: CalloutCardProps) {
  const variants = {
    cyan: { bg: 'bg-gradient-to-br from-cyan-50 to-blue-50 border-cyan-200/50' },
    emerald: { bg: 'bg-gradient-to-br from-emerald-50 to-teal-50 border-emerald-200/50' },
  };

  return (
    <div className={`rounded-2xl p-8 border ${variants[variant].bg} ${className}`}>
      {children}
    </div>
  );
}

// Differentiator card for "Why" section
interface DifferentiatorCardProps {
  title: string;
  description: string;
  className?: string;
  topoSeed?: number;
}

export function DifferentiatorCard({
  title,
  description,
  className = '',
  topoSeed = 1,
}: DifferentiatorCardProps) {
  // Vary complexity based on seed for variety
  const complexities: ('simple' | 'medium' | 'complex')[] = ['simple', 'medium', 'complex'];
  const complexity = complexities[topoSeed % complexities.length];

  return (
    <motion.div
      className={`bg-white rounded-xl p-6 border border-gray-200 shadow-sm relative overflow-hidden h-full flex flex-col ${className}`}
      whileHover={{ y: -4, boxShadow: '0 10px 40px -10px rgba(0,0,0,0.1)' }}
      transition={{ duration: 0.3 }}
    >
      <TopoPattern
        seed={topoSeed * 31}
        complexity={complexity}
        color="#9ca3af"
        opacity={0.15}
      />
      <div className="relative z-10 flex flex-col flex-1">
        <h3
          className="text-lg text-gray-900 mb-2"
          style={{ fontWeight: 500 }}
        >
          {title}
        </h3>
        <p
          className="text-sm text-gray-600 leading-relaxed flex-1"
          style={{ fontWeight: 300 }}
        >
          {description}
        </p>
      </div>
    </motion.div>
  );
}
