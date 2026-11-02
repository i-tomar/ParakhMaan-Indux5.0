import type { Metadata } from 'next';
import './globals.css';
import Navbar from '@/components/Navbar';
import AuthGate from '@/components/AuthGate';

export const metadata: Metadata = {
  title: 'ParakhMaan | AI Quality Inspection & Legal Metrology Compliance',
  description: 'AI & computer-vision product defect inspection with an optional Legal Metrology compliance module',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-[#f6f5f4] text-[#000000] flex flex-col">
        <Navbar />
        <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <AuthGate>{children}</AuthGate>
        </main>
        <footer className="bg-white border-t border-[#e6e6e6] py-6 text-center text-xs text-[#615d59]">
          <p>© 2026 Team Tarang • ParakhMaan • Indux 5.0 Problem Statement 12</p>
        </footer>
      </body>
    </html>
  );
}
