'use client';

import {
  GitBranch,
  GitPullRequest,
  MessageSquare,
  RefreshCw,
  Sparkles,
  Zap,
  Github,
  BookOpen,
  ArrowRight,
  Check,
  Copy,
} from 'lucide-react';
import { useState } from 'react';
import Image from 'next/image';
import {
  AnimatedSection,
  FadeIn,
  ScaleIn,
  StaggerContainer,
  StaggerItem,
} from '@/components/lander/AnimatedSection';
import {
  StepCard,
  IconFeatureCard,
  DifferentiatorCard,
  CalloutCard,
} from '@/components/lander/FeatureCard';
import { TopoPattern } from '@/components/lander/TopoPattern';
import { Button } from '@/components/ui/Button';

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <button
      onClick={handleCopy}
      className="p-2 text-gray-400 hover:text-white transition-colors"
      aria-label="Copy to clipboard"
    >
      {copied ? <Check className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4" />}
    </button>
  );
}

export default function Home() {
  return (
    <div className="min-h-screen">
      {/* Navigation */}
      <nav className="fixed top-0 left-0 right-0 z-50 bg-white/80 backdrop-blur-md border-b border-gray-200">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3 sm:gap-4">
            <a
              href="/"
              className="text-[11px] tracking-[2px] text-gray-900 hover:text-cyan-600 transition font-mono uppercase"
            >
              CLAUDEAR
            </a>
            <div className="h-3 w-px bg-gray-300 hidden sm:block" />
            <span className="text-[9px] tracking-[1px] text-gray-400 font-mono uppercase hidden sm:block">
              AUTONOMOUS_DEV
            </span>
          </div>
          <div className="flex items-center gap-3 sm:gap-6">
            <a
              href="/docs"
              className="text-[10px] tracking-[1px] text-gray-500 hover:text-gray-900 transition font-mono uppercase flex items-center gap-1.5"
            >
              <BookOpen className="w-3.5 h-3.5 sm:hidden" />
              <span className="hidden sm:inline">DOCS</span>
            </a>
            <a
              href="https://github.com/ianborders/claudear"
              target="_blank"
              rel="noopener noreferrer"
              className="text-[10px] tracking-[1px] text-gray-500 hover:text-gray-900 transition font-mono uppercase flex items-center gap-1.5"
            >
              <Github className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">GITHUB</span>
            </a>
            <a
              href="/docs/quickstart"
              className="px-3 sm:px-4 py-1.5 text-[9px] tracking-[1px] rounded-lg border border-emerald-500 bg-emerald-500/10 text-emerald-600 hover:bg-emerald-500/20 transition font-mono uppercase"
            >
              <span className="hidden sm:inline">GET_STARTED</span>
              <span className="sm:hidden">START</span>
            </a>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="relative pt-32 pb-20 px-6 overflow-hidden">
        <TopoPattern seed={42} complexity="complex" opacity={0.08} />
        <div className="max-w-4xl mx-auto text-center relative z-10">
          <ScaleIn>
            <div className="flex items-center justify-center gap-3 mb-6">
              <div
                className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border border-emerald-500/30 bg-emerald-500/10 text-emerald-600 text-[9px] tracking-[1px] font-mono"
              >
                <Sparkles className="w-3 h-3" />
                OPEN_SOURCE
              </div>
              <a
                href="https://clotion.dev"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border border-cyan-500/30 bg-cyan-500/10 text-cyan-600 text-[9px] tracking-[1px] font-mono hover:bg-cyan-500/20 transition"
              >
                <ArrowRight className="w-3 h-3" />
                CLOTION: NOTION + CLAUDE_CODE
              </a>
            </div>
          </ScaleIn>
          <ScaleIn delay={0.1}>
            <h1
              className="text-4xl md:text-5xl text-gray-900 mb-6 leading-tight"
              style={{ fontWeight: 300 }}
            >
              Autonomous Development with
              <span className="flex items-center justify-center gap-3 mt-2">
                <Image
                  src="/Claude-Logo.svg"
                  alt="Claude"
                  width={140}
                  height={30}
                  className="h-8 md:h-10 w-auto"
                />
                <span className="text-gray-400 text-2xl md:text-3xl">+</span>
                <Image
                  src="/linear-logo.svg"
                  alt="Linear"
                  width={140}
                  height={35}
                  className="h-8 md:h-10 w-auto"
                />
              </span>
            </h1>
          </ScaleIn>
          <ScaleIn delay={0.2}>
            <p
              className="text-lg text-gray-600 mb-10 max-w-3xl mx-auto leading-relaxed"
              style={{ fontWeight: 300 }}
            >
              Hand off Linear issues to Claude Code. Claudear implements, tests, creates PRs, and manages the full
              lifecycle. Let Claude Code do the coding while you focus on what matters.
            </p>
          </ScaleIn>
          <ScaleIn delay={0.3}>
            <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
              <Button href="/docs/quickstart" size="lg" variant="primary">
                GET_STARTED
                <ArrowRight className="w-3.5 h-3.5" />
              </Button>
              <Button
                href="https://github.com/ianborders/claudear"
                size="lg"
                variant="outline"
                external
              >
                <Github className="w-3.5 h-3.5" />
                VIEW_ON_GITHUB
              </Button>
            </div>
          </ScaleIn>
        </div>
      </section>

      {/* Installation Section */}
      <AnimatedSection className="py-16 px-6">
        <div className="max-w-2xl mx-auto">
          <div className="code-block">
            <div className="flex items-center justify-between px-4 py-2 border-b border-white/10">
              <div className="flex items-center gap-1.5">
                <div className="w-2.5 h-2.5 rounded-full bg-red-500/60" />
                <div className="w-2.5 h-2.5 rounded-full bg-yellow-500/60" />
                <div className="w-2.5 h-2.5 rounded-full bg-emerald-500/60" />
              </div>
              <CopyButton text="git clone https://github.com/ianborders/claudear.git && cd claudear && pip install claudear" />
            </div>
            <div className="p-6 flex flex-col items-center gap-4">
              <Image
                src="/claudear-logo.png"
                alt="Claudear"
                width={400}
                height={100}
                className="opacity-90"
                priority
              />
              <pre className="w-full text-left">
                <code className="block">
                  <span className="text-gray-500"># 1. Clone the repository</span>
                </code>
                <code className="block">
                  <span className="text-gray-500">$</span>{' '}
                  <span className="text-emerald-400">git clone</span>{' '}
                  <span className="text-cyan-400">https://github.com/ianborders/claudear.git</span>
                </code>
                <code className="block">
                  <span className="text-gray-500">$</span>{' '}
                  <span className="text-emerald-400">cd</span>{' '}
                  <span className="text-cyan-400">claudear</span>
                </code>
                <code className="block mt-2">
                  <span className="text-gray-500"># 2. Install the claudear command</span>
                </code>
                <code className="block">
                  <span className="text-gray-500">$</span>{' '}
                  <span className="text-emerald-400">pip install</span>{' '}
                  <span className="text-cyan-400">claudear</span>
                </code>
              </pre>
            </div>
          </div>
        </div>
      </AnimatedSection>

      {/* How It Works Section */}
      <AnimatedSection className="py-20 px-6">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-12">
            <FadeIn>
              <div className="text-[9px] text-cyan-600 tracking-[2px] font-mono mb-3">
                {'// HOW_IT_WORKS'}
              </div>
            </FadeIn>
            <FadeIn delay={0.1}>
              <h2
                className="text-3xl md:text-4xl text-gray-900 mb-4"
                style={{ fontWeight: 300 }}
              >
                From Linear Issue to Merged PR
              </h2>
            </FadeIn>
            <FadeIn delay={0.2}>
              <p
                className="text-base text-gray-600 max-w-xl mx-auto"
                style={{ fontWeight: 300 }}
              >
                Claudear automates the entire development workflow, from picking up tasks to
                creating pull requests.
              </p>
            </FadeIn>
          </div>
          <StaggerContainer className="grid md:grid-cols-2 lg:grid-cols-3 gap-4" staggerDelay={0.1}>
            <StaggerItem>
              <StepCard
                number="01"
                label="Trigger"
                title="Move issue to Todo"
                description="Drag a Linear issue from Backlog to Todo. Claudear's webhook picks it up instantly."
                accentColor="cyan"
                topoSeed={1}
              />
            </StaggerItem>
            <StaggerItem>
              <StepCard
                number="02"
                label="Isolation"
                title="Create worktree"
                description="A dedicated git worktree and branch are created, isolating work from your main codebase."
                accentColor="emerald"
                topoSeed={2}
              />
            </StaggerItem>
            <StaggerItem>
              <StepCard
                number="03"
                label="Implementation"
                title="Claude implements"
                description="Claude Code analyzes the issue, explores the codebase, and implements the solution."
                accentColor="cyan"
                topoSeed={3}
              />
            </StaggerItem>
            <StaggerItem>
              <StepCard
                number="04"
                label="Blocked"
                title="Human in the loop"
                description="If Claude gets stuck, it posts a comment asking for guidance. Reply to unblock."
                accentColor="emerald"
                topoSeed={4}
              />
            </StaggerItem>
            <StaggerItem>
              <StepCard
                number="05"
                label="Review"
                title="PR created"
                description="When complete, code is pushed and a PR is created. Issue moves to In Review."
                accentColor="cyan"
                topoSeed={5}
              />
            </StaggerItem>
            <StaggerItem>
              <StepCard
                number="06"
                label="Complete"
                title="Auto-merge"
                description="Move the issue to Done and the PR auto-merges. Worktree cleaned up automatically."
                accentColor="emerald"
                topoSeed={6}
              />
            </StaggerItem>
          </StaggerContainer>
        </div>
      </AnimatedSection>

      {/* Features Grid */}
      <AnimatedSection className="py-20 px-6 bg-white/50">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-12">
            <FadeIn>
              <div className="text-[9px] text-emerald-600 tracking-[2px] font-mono mb-3">
                {'// FEATURES'}
              </div>
            </FadeIn>
            <FadeIn delay={0.1}>
              <h2
                className="text-3xl md:text-4xl text-gray-900 mb-4"
                style={{ fontWeight: 300 }}
              >
                Built for Real Workflows
              </h2>
            </FadeIn>
          </div>
          <StaggerContainer className="grid md:grid-cols-2 lg:grid-cols-3 gap-4" staggerDelay={0.08}>
            <StaggerItem>
              <IconFeatureCard
                icon={<Zap className="w-5 h-5" />}
                label="Linear Integration"
                description="Webhooks receive events in real-time. State changes trigger automation seamlessly."
                accentColor="cyan"
                topoSeed={10}
              />
            </StaggerItem>
            <StaggerItem>
              <IconFeatureCard
                icon={<GitBranch className="w-5 h-5" />}
                label="Git Worktrees"
                description="Each task gets an isolated worktree. Run multiple tasks in parallel without conflicts."
                accentColor="emerald"
                topoSeed={11}
              />
            </StaggerItem>
            <StaggerItem>
              <IconFeatureCard
                icon={<Sparkles className="w-5 h-5" />}
                label="Claude Code CLI"
                description="Uses your Claude Code subscription, not API credits. Same Claude, just automated."
                accentColor="cyan"
                topoSeed={12}
              />
            </StaggerItem>
            <StaggerItem>
              <IconFeatureCard
                icon={<GitPullRequest className="w-5 h-5" />}
                label="PR Automation"
                description="PRs created via GitHub CLI with proper titles, descriptions, and Linear issue links."
                accentColor="emerald"
                topoSeed={13}
              />
            </StaggerItem>
            <StaggerItem>
              <IconFeatureCard
                icon={<MessageSquare className="w-5 h-5" />}
                label="Human in Loop"
                description="When blocked, Claude asks for help via Linear comments. Reply to continue."
                accentColor="cyan"
                topoSeed={14}
              />
            </StaggerItem>
            <StaggerItem>
              <IconFeatureCard
                icon={<RefreshCw className="w-5 h-5" />}
                label="Crash Recovery"
                description="SQLite persistence means tasks survive restarts. Pick up where you left off."
                accentColor="emerald"
                topoSeed={15}
              />
            </StaggerItem>
          </StaggerContainer>
        </div>
      </AnimatedSection>

      {/* Why Claudear Section */}
      <AnimatedSection className="py-20 px-6">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-12">
            <FadeIn>
              <div className="text-[9px] text-cyan-600 tracking-[2px] font-mono mb-3">
                {'// WHY_CLAUDEAR'}
              </div>
            </FadeIn>
            <FadeIn delay={0.1}>
              <h2
                className="text-3xl md:text-4xl text-gray-900 mb-4"
                style={{ fontWeight: 300 }}
              >
                Open Source. Self-Hosted. Yours.
              </h2>
            </FadeIn>
          </div>
          <StaggerContainer className="grid md:grid-cols-2 gap-4" staggerDelay={0.1}>
            <StaggerItem>
              <DifferentiatorCard
                title="Open Source"
                description="MIT licensed. Fork it, modify it, contribute back. Built in public for the community."
                topoSeed={20}
              />
            </StaggerItem>
            <StaggerItem>
              <DifferentiatorCard
                title="Uses Your Subscription"
                description="Runs Claude Code CLI in headless mode. No separate API costs - uses your existing Claude Code subscription."
                topoSeed={21}
              />
            </StaggerItem>
            <StaggerItem>
              <DifferentiatorCard
                title="Self-Hosted"
                description="Runs on your machine with ngrok for webhooks. Your code never leaves your environment."
                topoSeed={22}
              />
            </StaggerItem>
            <StaggerItem>
              <DifferentiatorCard
                title="Full Control"
                description="You own the workflow. Configure states, concurrency limits, timeouts - everything is customizable."
                topoSeed={23}
              />
            </StaggerItem>
          </StaggerContainer>
        </div>
      </AnimatedSection>

      {/* CTA Section */}
      <AnimatedSection className="py-24 px-6">
        <div className="max-w-4xl mx-auto">
          <CalloutCard variant="emerald" className="text-center">
            <FadeIn>
              <div className="text-[9px] text-emerald-600 tracking-[2px] font-mono mb-4">
                {'// GET_STARTED'}
              </div>
            </FadeIn>
            <FadeIn delay={0.1}>
              <h2
                className="text-3xl md:text-4xl text-gray-900 mb-4"
                style={{ fontWeight: 300 }}
              >
                Ready to automate your development?
              </h2>
            </FadeIn>
            <FadeIn delay={0.2}>
              <p
                className="text-base text-gray-600 mb-8 max-w-2xl mx-auto"
                style={{ fontWeight: 300 }}
              >
                Get started in minutes. Install Claudear, configure your Linear webhook, and let
                Claude Code handle the implementation.
              </p>
            </FadeIn>

            {/* Workflow Steps */}
            <FadeIn delay={0.3}>
              <div className="flex flex-wrap justify-center gap-4 mb-8 text-[10px] font-mono">
                <div className="flex items-center gap-2 text-gray-500">
                  <span className="text-cyan-600">1.</span> Install
                </div>
                <span className="text-gray-300">→</span>
                <div className="flex items-center gap-2 text-gray-500">
                  <span className="text-cyan-600">2.</span> Configure
                </div>
                <span className="text-gray-300">→</span>
                <div className="flex items-center gap-2 text-gray-500">
                  <span className="text-emerald-600">3.</span> Move to Todo
                </div>
                <span className="text-gray-300">→</span>
                <div className="flex items-center gap-2 text-gray-500">
                  <span className="text-emerald-600">4.</span> Watch it work
                </div>
              </div>
            </FadeIn>

            <FadeIn delay={0.4}>
              <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
                <Button href="/docs/quickstart" size="lg" variant="primary">
                  <BookOpen className="w-3.5 h-3.5" />
                  READ_THE_DOCS
                </Button>
                <Button
                  href="https://github.com/ianborders/claudear"
                  size="lg"
                  variant="outline"
                  external
                >
                  <Github className="w-3.5 h-3.5" />
                  STAR_ON_GITHUB
                </Button>
              </div>
            </FadeIn>
            <FadeIn delay={0.5}>
              <div className="mt-6 text-[9px] text-gray-500 font-mono">
                MIT Licensed • Uses your Claude Code subscription
              </div>
            </FadeIn>
          </CalloutCard>
        </div>
      </AnimatedSection>

      {/* Footer */}
      <footer className="py-8 px-6 border-t border-gray-200 bg-white/80 backdrop-blur-sm">
        <div className="max-w-6xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="text-[9px] text-gray-500 tracking-[1px] font-mono">
            CLAUDEAR_v0.1.0
          </div>
          <div className="flex gap-6 text-[9px] tracking-[1px] font-mono">
            <a href="/docs" className="text-gray-500 hover:text-gray-900 transition">
              DOCUMENTATION
            </a>
            <a
              href="https://github.com/ianborders/claudear"
              target="_blank"
              rel="noopener noreferrer"
              className="text-gray-500 hover:text-gray-900 transition"
            >
              GITHUB
            </a>
            <a
              href="https://github.com/ianborders/claudear/blob/main/LICENSE"
              target="_blank"
              rel="noopener noreferrer"
              className="text-gray-500 hover:text-gray-900 transition"
            >
              MIT_LICENSE
            </a>
          </div>
          <a
            href="https://x.com/OpenMotus"
            target="_blank"
            rel="noopener noreferrer"
            className="text-[8px] text-gray-500 font-mono flex items-center gap-1 group transition"
          >
            BUILT_BY{' '}
            <span className="group-hover:text-emerald-600 transition">IAN_BORDERS</span>
            {' '}WITH ❤️ AND ☕
          </a>
        </div>
      </footer>
    </div>
  );
}
