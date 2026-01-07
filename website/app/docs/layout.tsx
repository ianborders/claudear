import Link from 'next/link';
import { Github } from 'lucide-react';
import { Sidebar } from '@/components/docs/Sidebar';
import { getDocsSections } from '@/lib/docs';

export default function DocsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const sections = getDocsSections();

  return (
    <div className="min-h-screen bg-[#fafafa]">
      {/* Navigation */}
      <nav className="fixed top-0 left-0 right-0 z-50 bg-white/80 backdrop-blur-md border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link
              href="/"
              className="text-[11px] tracking-[2px] text-gray-900 hover:text-cyan-600 transition font-mono uppercase"
            >
              CLAUDEAR
            </Link>
            <div className="h-3 w-px bg-gray-300" />
            <Link
              href="/docs"
              className="text-[9px] tracking-[1px] text-gray-400 font-mono uppercase"
            >
              DOCUMENTATION
            </Link>
          </div>
          <div className="flex items-center gap-4">
            <a
              href="https://github.com/ianborders/claudear"
              target="_blank"
              rel="noopener noreferrer"
              className="text-[10px] tracking-[1px] text-gray-500 hover:text-gray-900 transition font-mono uppercase flex items-center gap-1.5"
            >
              <Github className="w-3.5 h-3.5" />
              GITHUB
            </a>
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <div className="flex pt-16">
        <Sidebar sections={sections} />
        <main className="flex-1 min-w-0">{children}</main>
      </div>
    </div>
  );
}
