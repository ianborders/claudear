import { getDocsSections } from '@/lib/docs';
import { DocsLayoutClient } from '@/components/docs/DocsLayoutClient';

export default function DocsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const sections = getDocsSections();

  return (
    <DocsLayoutClient sections={sections}>
      {children}
    </DocsLayoutClient>
  );
}
