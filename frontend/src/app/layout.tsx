import type { Metadata } from 'next';
import './globals.css';
import AppShell from '@/components/AppShell';

export const metadata: Metadata = {
  title: 'ParakhMaan | Industrial Visual Inspection',
  description: 'AI and computer-vision surface and product defect inspection for production lines',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-[#f6f5f4] text-[#000000]">
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
