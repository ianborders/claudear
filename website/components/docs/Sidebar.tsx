'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { ChevronDown } from 'lucide-react';
import { useState } from 'react';
import type { DocSection } from '@/lib/docs';

interface SidebarProps {
  sections: DocSection[];
}

export function Sidebar({ sections }: SidebarProps) {
  const pathname = usePathname();
  const [expandedSections, setExpandedSections] = useState<Set<string>>(
    new Set(sections.map((s) => s.slug))
  );

  const toggleSection = (slug: string) => {
    const newExpanded = new Set(expandedSections);
    if (newExpanded.has(slug)) {
      newExpanded.delete(slug);
    } else {
      newExpanded.add(slug);
    }
    setExpandedSections(newExpanded);
  };

  const isActive = (slug: string) => {
    return pathname === `/docs/${slug}` || pathname === `/docs/${slug}/`;
  };

  return (
    <nav className="w-64 shrink-0 border-r border-gray-200 bg-white/50 overflow-y-auto h-[calc(100vh-4rem)] sticky top-16">
      <div className="p-6 space-y-6">
        {sections.map((section) => (
          <div key={section.slug}>
            <button
              onClick={() => toggleSection(section.slug)}
              className="flex items-center justify-between w-full text-left text-[9px] font-mono text-gray-400 tracking-[1px] mb-2 hover:text-gray-600"
            >
              {section.title.toUpperCase().replace(/ /g, '_')}
              <ChevronDown
                className={`w-3.5 h-3.5 transition-transform ${
                  expandedSections.has(section.slug) ? 'rotate-0' : '-rotate-90'
                }`}
              />
            </button>
            {expandedSections.has(section.slug) && (
              <ul className="space-y-1">
                {section.docs.map((doc) => (
                  <li key={doc.slug}>
                    <Link
                      href={`/docs/${doc.slug}`}
                      className={`block px-3 py-1.5 text-sm rounded-md transition-colors ${
                        isActive(doc.slug)
                          ? 'bg-emerald-100 text-emerald-700 font-medium'
                          : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
                      }`}
                    >
                      {doc.title}
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </div>
        ))}
      </div>
    </nav>
  );
}
