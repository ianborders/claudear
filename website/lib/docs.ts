import fs from 'fs';
import path from 'path';
import matter from 'gray-matter';

const docsDirectory = path.join(process.cwd(), 'content/docs');

export interface DocMeta {
  slug: string;
  title: string;
  description?: string;
  order?: number;
  section?: string;
}

export interface Doc extends DocMeta {
  content: string;
}

export interface DocSection {
  title: string;
  slug: string;
  docs: DocMeta[];
}

// Get all doc files recursively
function getDocFiles(dir: string, basePath: string = ''): string[] {
  if (!fs.existsSync(dir)) {
    return [];
  }

  const files: string[] = [];
  const entries = fs.readdirSync(dir, { withFileTypes: true });

  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    const relativePath = path.join(basePath, entry.name);

    if (entry.isDirectory()) {
      files.push(...getDocFiles(fullPath, relativePath));
    } else if (entry.name.endsWith('.mdx') || entry.name.endsWith('.md')) {
      files.push(relativePath);
    }
  }

  return files;
}

// Get a single doc by slug
export function getDocBySlug(slug: string[]): Doc | null {
  const slugPath = slug.join('/');

  // Try with .mdx extension
  let fullPath = path.join(docsDirectory, `${slugPath}.mdx`);
  if (!fs.existsSync(fullPath)) {
    // Try with .md extension
    fullPath = path.join(docsDirectory, `${slugPath}.md`);
    if (!fs.existsSync(fullPath)) {
      // Try as directory with index.mdx
      fullPath = path.join(docsDirectory, slugPath, 'index.mdx');
      if (!fs.existsSync(fullPath)) {
        fullPath = path.join(docsDirectory, slugPath, 'index.md');
        if (!fs.existsSync(fullPath)) {
          return null;
        }
      }
    }
  }

  const fileContents = fs.readFileSync(fullPath, 'utf8');
  const { data, content } = matter(fileContents);

  return {
    slug: slugPath,
    title: data.title || slugPath,
    description: data.description,
    order: data.order,
    section: data.section,
    content,
  };
}

// Get all docs metadata
export function getAllDocs(): DocMeta[] {
  const files = getDocFiles(docsDirectory);

  const docs = files.map((file) => {
    const slug = file.replace(/\.(mdx|md)$/, '').replace(/\/index$/, '');
    const fullPath = path.join(docsDirectory, file);
    const fileContents = fs.readFileSync(fullPath, 'utf8');
    const { data } = matter(fileContents);

    return {
      slug,
      title: data.title || slug,
      description: data.description,
      order: data.order ?? 999,
      section: data.section,
    };
  });

  return docs.sort((a, b) => (a.order ?? 999) - (b.order ?? 999));
}

// Get docs organized by section
export function getDocsSections(): DocSection[] {
  const docs = getAllDocs();

  // Define section order
  const sectionOrder = [
    'Getting Started',
    'How It Works',
    'Setup',
    'Usage',
    'Reference',
  ];

  const sections = new Map<string, DocMeta[]>();

  // Group docs by section
  for (const doc of docs) {
    const section = doc.section || 'Getting Started';
    if (!sections.has(section)) {
      sections.set(section, []);
    }
    sections.get(section)!.push(doc);
  }

  // Convert to array and sort
  const result: DocSection[] = [];

  for (const sectionName of sectionOrder) {
    if (sections.has(sectionName)) {
      const sectionDocs = sections.get(sectionName)!;
      sectionDocs.sort((a, b) => (a.order ?? 999) - (b.order ?? 999));
      result.push({
        title: sectionName,
        slug: sectionName.toLowerCase().replace(/\s+/g, '-'),
        docs: sectionDocs,
      });
    }
  }

  // Add any remaining sections
  for (const [sectionName, sectionDocs] of sections) {
    if (!sectionOrder.includes(sectionName)) {
      sectionDocs.sort((a, b) => (a.order ?? 999) - (b.order ?? 999));
      result.push({
        title: sectionName,
        slug: sectionName.toLowerCase().replace(/\s+/g, '-'),
        docs: sectionDocs,
      });
    }
  }

  return result;
}

// Get all doc slugs for static generation
export function getAllDocSlugs(): string[][] {
  const docs = getAllDocs();
  return docs.map((doc) => doc.slug.split('/'));
}
