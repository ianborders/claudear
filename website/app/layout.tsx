import type { Metadata } from "next";
import { Inter, Space_Mono } from "next/font/google";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  display: "swap",
});

const spaceMono = Space_Mono({
  variable: "--font-space-mono",
  subsets: ["latin"],
  weight: ["400", "700"],
  display: "swap",
});

export const metadata: Metadata = {
  metadataBase: new URL("https://claudear.com"),
  title: "Claudear - Autonomous Development Automation with Claude Code + Linear + Notion",
  description:
    "Hand off Linear issues or Notion tasks to Claude Code. Claudear implements, tests, creates PRs, and manages the full lifecycle. Open source autonomous development automation.",
  keywords: [
    "Claude Code",
    "Linear",
    "Notion",
    "automation",
    "AI development",
    "autonomous coding",
    "PR automation",
    "task automation",
  ],
  authors: [{ name: "Ian Borders" }],
  creator: "Ian Borders",
  publisher: "Claudear",
  openGraph: {
    title: "Claudear - Autonomous Development Automation with Claude Code + Linear + Notion",
    description:
      "Hand off Linear issues or Notion tasks to Claude Code. Claudear implements, tests, creates PRs, and manages the full lifecycle.",
    url: "https://claudear.com",
    siteName: "Claudear",
    type: "website",
    locale: "en_US",
    images: [
      {
        url: "/og-image.png",
        width: 1200,
        height: 630,
        alt: "Claudear - Autonomous Development Automation with Claude Code + Linear + Notion",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "Claudear - Autonomous Development Automation with Claude Code + Linear + Notion",
    description:
      "Hand off Linear issues or Notion tasks to Claude Code. Claudear implements, tests, creates PRs, and manages the full lifecycle.",
    site: "https://claudear.com",
    creator: "@OpenMotus",
    images: [
      {
        url: "/twitter-image.png",
        width: 1200,
        height: 630,
        alt: "Claudear - Autonomous Development Automation with Claude Code + Linear + Notion",
      },
    ],
  },
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
    },
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${inter.variable} ${spaceMono.variable} antialiased`}>
        {children}
      </body>
    </html>
  );
}
