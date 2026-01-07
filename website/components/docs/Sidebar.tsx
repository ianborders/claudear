'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { ChevronDown, X } from 'lucide-react';
import { useState, useEffect } from 'react';
import type { DocSection } from '@/lib/docs';

interface SidebarProps {
  sections: DocSection[];
  isOpen?: boolean;
  onClose?: () => void;
}

export function Sidebar({ sections, isOpen, onClose }: SidebarProps) {
  const pathname = usePathname();
  const [expandedSections, setExpandedSections] = useState<Set<string>>(
    new Set(sections.map((s) => s.slug))
  );

  // Close sidebar on route change (mobile)
  useEffect(() => {
    if (onClose) {
      onClose();
    }
  }, [pathname, onClose]);

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
    <>
      {/* Mobile overlay */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-40 lg:hidden"
          onClick={onClose}
        />
      )}

      {/* Sidebar */}
      <nav
        className={`
          fixed lg:sticky top-16 left-0 z-50 lg:z-auto
          w-72 lg:w-64 shrink-0
          border-r border-gray-200 bg-white lg:bg-white/50
          overflow-y-auto h-[calc(100vh-4rem)]
          transform transition-transform duration-300 ease-in-out
          ${isOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
        `}
      >
        {/* Mobile close button */}
        <button
          onClick={onClose}
          className="lg:hidden absolute top-4 right-4 p-2 text-gray-500 hover:text-gray-700"
          aria-label="Close menu"
        >
          <X className="w-5 h-5" />
        </button>

        <div className="p-6 pt-14 lg:pt-6 space-y-6">
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
    </>
  );
}
