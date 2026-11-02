import { AuthUser } from './types';

const TOKEN_KEY = 'pm_token';
const USER_KEY = 'pm_user';
const listeners = new Set<() => void>();

export function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function getUser(): AuthUser | null {
  if (typeof window === 'undefined') return null;
  const raw = window.localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as AuthUser;
  } catch {
    return null;
  }
}

export function setSession(token: string, user: AuthUser): void {
  window.localStorage.setItem(TOKEN_KEY, token);
  window.localStorage.setItem(USER_KEY, JSON.stringify(user));
  listeners.forEach((fn) => fn());
}

export function updateUser(user: AuthUser): void {
  window.localStorage.setItem(USER_KEY, JSON.stringify(user));
  listeners.forEach((fn) => fn());
}

export function clearSession(): void {
  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(USER_KEY);
  listeners.forEach((fn) => fn());
}

export function onSessionChange(fn: () => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

/** Mirrors the backend permission model for navigation only; the API enforces it. */
export function can(user: AuthUser | null, permission: string): boolean {
  return !!user?.permissions?.includes(permission);
}

export const ROLE_LABELS: Record<string, string> = {
  OPERATOR: 'Operator',
  QUALITY_MANAGER: 'Quality Manager',
  ADMIN: 'Administrator',
  AUDITOR: 'Auditor',
};
