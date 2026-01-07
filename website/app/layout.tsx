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
  title: "Claudear - Autonomous Development with Claude Code",
  description:
    "Move Linear issues to Todo. Claudear implements, creates PRs, and manages the full lifecycle. Open source autonomous development automation.",
  keywords: [
    "Claude Code",
    "Linear",
    "automation",
    "AI development",
    "autonomous coding",
    "PR automation",
  ],
  authors: [{ name: "Claudear" }],
  openGraph: {
    title: "Claudear - Autonomous Development with Claude Code",
    description:
      "Move Linear issues to Todo. Claudear implements, creates PRs, and manages the full lifecycle.",
    url: "https://claudear.com",
    siteName: "Claudear",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "Claudear - Autonomous Development with Claude Code",
    description:
      "Move Linear issues to Todo. Claudear implements, creates PRs, and manages the full lifecycle.",
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
