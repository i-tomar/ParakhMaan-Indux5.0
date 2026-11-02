'use client';

import { useMemo, useSyncExternalStore } from 'react';
import { AuthUser } from './types';
import { onSessionChange } from './auth';

function snapshot(): string | null {
  return typeof window === 'undefined' ? null : window.localStorage.getItem('pm_user');
}

/** Current signed-in user, re-rendering on login / logout / profile refresh. */
export function useAuthUser(): AuthUser | null {
  const raw = useSyncExternalStore(onSessionChange, snapshot, () => null);
  return useMemo(() => {
    if (!raw) return null;
    try {
      return JSON.parse(raw) as AuthUser;
    } catch {
      return null;
    }
  }, [raw]);
}
