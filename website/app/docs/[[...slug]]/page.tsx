import { notFound } from 'next/navigation';
import { MDXRemote } from 'next-mdx-remote/rsc';
import Link from 'next/link';
import { ArrowLeft, ArrowRight } from 'lucide-react';
import remarkGfm from 'remark-gfm';
import { getDocBySlug, getAllDocs, getAllDocSlugs } from '@/lib/docs';

interface DocPageProps {
  params: Promise<{ slug?: string[] }>;
}

// Custom components for MDX
const components = {
  h1: (props: React.HTMLAttributes<HTMLHeadingElement>) => (
    <h1 className="text-2xl sm:text-3xl font-semibold text-gray-900 mb-4 sm:mb-6 mt-6 sm:mt-8 first:mt-0" {...props} />
  ),
  h2: (props: React.HTMLAttributes<HTMLHeadingElement>) => (
    <h2 className="text-xl sm:text-2xl font-semibold text-gray-900 mb-3 sm:mb-4 mt-6 sm:mt-8" {...props} />
  ),
  h3: (props: React.HTMLAttributes<HTMLHeadingElement>) => (
    <h3 className="text-lg sm:text-xl font-semibold text-gray-900 mb-2 sm:mb-3 mt-4 sm:mt-6" {...props} />
  ),
  p: (props: React.HTMLAttributes<HTMLParagraphElement>) => (
    <p className="text-gray-600 leading-relaxed mb-4" {...props} />
  ),
  ul: (props: React.HTMLAttributes<HTMLUListElement>) => (
    <ul className="list-disc list-inside text-gray-600 mb-4 space-y-1" {...props} />
  ),
  ol: (props: React.HTMLAttributes<HTMLOListElement>) => (
    <ol className="list-decimal list-inside text-gray-600 mb-4 space-y-1" {...props} />
  ),
  li: (props: React.HTMLAttributes<HTMLLIElement>) => (
    <li className="leading-relaxed" {...props} />
  ),
  a: (props: React.AnchorHTMLAttributes<HTMLAnchorElement>) => (
    <a className="text-emerald-600 hover:text-emerald-700 underline" {...props} />
  ),
  code: (props: React.HTMLAttributes<HTMLElement>) => {
    const isInline = typeof props.children === 'string' && !props.children.includes('\n');
    if (isInline) {
      return (
        <code
          className="bg-gray-100 text-gray-800 px-1.5 py-0.5 rounded text-sm font-mono"
          {...props}
        />
      );
    }
    return <code className="font-mono" {...props} />;
  },
  pre: (props: React.HTMLAttributes<HTMLPreElement>) => (
    <pre
      className="bg-gray-900 text-gray-100 rounded-lg p-4 overflow-x-auto mb-4 text-sm"
      {...props}
    />
  ),
  blockquote: (props: React.HTMLAttributes<HTMLQuoteElement>) => (
    <blockquote
      className="border-l-4 border-emerald-500 pl-4 italic text-gray-600 my-4"
      {...props}
    />
  ),
  table: (props: React.HTMLAttributes<HTMLTableElement>) => (
    <div className="overflow-x-auto mb-6 rounded-lg border border-gray-200">
      <table className="min-w-full divide-y divide-gray-200" {...props} />
    </div>
  ),
  thead: (props: React.HTMLAttributes<HTMLTableSectionElement>) => (
    <thead className="bg-gray-50" {...props} />
  ),
  tbody: (props: React.HTMLAttributes<HTMLTableSectionElement>) => (
    <tbody className="bg-white divide-y divide-gray-100" {...props} />
  ),
  tr: (props: React.HTMLAttributes<HTMLTableRowElement>) => (
    <tr {...props} />
  ),
  th: (props: React.HTMLAttributes<HTMLTableCellElement>) => (
    <th
      className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider"
      {...props}
    />
  ),
  td: (props: React.HTMLAttributes<HTMLTableCellElement>) => (
    <td className="px-4 py-3 text-sm text-gray-600" {...props} />
  ),
};

export async function generateStaticParams() {
  const slugs = getAllDocSlugs();
  // Include empty slug for /docs route
  return [{ slug: undefined }, ...slugs.map((slug) => ({ slug }))];
}

export async function generateMetadata({ params }: DocPageProps) {
  const resolvedParams = await params;
  const slug = resolvedParams.slug || ['introduction'];
  const doc = getDocBySlug(slug);

  if (!doc) {
    return { title: 'Not Found' };
  }

  return {
    title: `${doc.title} | Claudear Docs`,
    description: doc.description,
  };
}

export default async function DocPage({ params }: DocPageProps) {
  const resolvedParams = await params;
  const slug = resolvedParams.slug || ['introduction'];
  const doc = getDocBySlug(slug);

  if (!doc) {
    notFound();
  }

  // Get all docs for prev/next navigation
  const allDocs = getAllDocs();
  const currentIndex = allDocs.findIndex((d) => d.slug === doc.slug);
  const prevDoc = currentIndex > 0 ? allDocs[currentIndex - 1] : null;
  const nextDoc = currentIndex < allDocs.length - 1 ? allDocs[currentIndex + 1] : null;

  return (
    <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-8 sm:py-12">
      {/* Breadcrumb */}
      <div className="text-sm text-gray-500 mb-6">
        <Link href="/docs" className="hover:text-gray-700">
          Docs
        </Link>
        <span className="mx-2">/</span>
        <span className="text-gray-900">{doc.title}</span>
      </div>

      {/* Content */}
      <article className="prose prose-gray max-w-none">
        <h1>{doc.title}</h1>
        {doc.description && (
          <p className="text-xl text-gray-500 mb-8 -mt-2">{doc.description}</p>
        )}
        <MDXRemote
          source={doc.content}
          components={components}
          options={{ mdxOptions: { remarkPlugins: [remarkGfm] } }}
        />
      </article>

      {/* Prev/Next Navigation */}
      <div className="flex items-center justify-between mt-12 pt-8 border-t border-gray-200">
        {prevDoc ? (
          <Link
            href={`/docs/${prevDoc.slug}`}
            className="flex items-center gap-2 text-gray-600 hover:text-gray-900 transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            <div>
              <div className="text-xs text-gray-400 uppercase tracking-wider">Previous</div>
              <div className="text-sm font-medium">{prevDoc.title}</div>
            </div>
          </Link>
        ) : (
          <div />
        )}
        {nextDoc ? (
          <Link
            href={`/docs/${nextDoc.slug}`}
            className="flex items-center gap-2 text-gray-600 hover:text-gray-900 transition-colors text-right"
          >
            <div>
              <div className="text-xs text-gray-400 uppercase tracking-wider">Next</div>
              <div className="text-sm font-medium">{nextDoc.title}</div>
            </div>
            <ArrowRight className="w-4 h-4" />
          </Link>
        ) : (
          <div />
        )}
      </div>
    </div>
  );
}
