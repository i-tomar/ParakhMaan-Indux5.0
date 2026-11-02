'use client';

import React, { useEffect, useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { RefreshCw } from 'lucide-react';
import { authApi } from '@/lib/api';
import { getToken, updateUser } from '@/lib/auth';

const PUBLIC_PATHS = ['/login'];

/** Client-side guard: sends signed-out users to /login and refreshes the session profile once. */
export default function AuthGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const isPublic = PUBLIC_PATHS.includes(pathname);
  const [verifiedToken, setVerifiedToken] = useState<string | null>(null);

  useEffect(() => {
    if (isPublic) return;
    const token = getToken();
    if (!token) {
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
      return;
    }
    if (token === verifiedToken) return;
    authApi
      .me()
      .then((user) => {
        updateUser(user);
        setVerifiedToken(token);
      })
      .catch(() => {
        // authFetch already clears the session and redirects on 401
      });
  }, [isPublic, pathname, router, verifiedToken]);

  if (isPublic || (verifiedToken && verifiedToken === getToken())) {
    return <>{children}</>;
  }
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center">
      <RefreshCw className="w-7 h-7 text-[#0075de] animate-spin mb-3" />
      <p className="text-sm font-semibold text-[#000000]">Checking your session…</p>
    </div>
  );
}
