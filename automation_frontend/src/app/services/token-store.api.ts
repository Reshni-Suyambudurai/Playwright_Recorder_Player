import { Injectable } from '@angular/core';

/**
 * TokenStore — single source of truth for all browser storage.
 *
 * localStorage  (persists across tabs and browser restarts)
 *   - theme          'dark' | 'light'
 *   - clientId       browser installation identity — same across all tabs, survives restarts
 *
 * sessionStorage  (cleared when the tab is closed)
 *   - sessionId      backend session UUID returned by POST /recording/start
 */

const KEYS = {
  // localStorage  (browser-level persistence)
  THEME:     'theme',
  CLIENT_ID: 'clientId',

  // sessionStorage  (tab-level persistence)
  SESSION_ID: 'sessionId',
} as const;

@Injectable({ providedIn: 'root' })
export class TokenStore {

  // ── localStorage ──────────────────────────────────────────────

  getTheme(): 'dark' | 'light' | null {
    const v = localStorage.getItem(KEYS.THEME);
    return v === 'dark' || v === 'light' ? v : null;
  }

  setTheme(theme: 'dark' | 'light'): void {
    localStorage.setItem(KEYS.THEME, theme);
  }

  getClientId(): string | null {
    return localStorage.getItem(KEYS.CLIENT_ID);
  }

  setClientId(id: string): void {
    localStorage.setItem(KEYS.CLIENT_ID, id);
  }

  removeClientId(): void {
    localStorage.removeItem(KEYS.CLIENT_ID);
  }

  // ── sessionStorage ────────────────────────────────────────────

  getSessionId(): string | null {
    return sessionStorage.getItem(KEYS.SESSION_ID);
  }

  setSessionId(id: string): void {
    sessionStorage.setItem(KEYS.SESSION_ID, id);
  }

  removeSessionId(): void {
    sessionStorage.removeItem(KEYS.SESSION_ID);
  }

  // ── Helpers ───────────────────────────────────────────────────

  /**
   * Returns the stored clientId from localStorage, or generates + persists a new one.
   * Stable for the lifetime of the browser installation — same across all tabs.
   */
  resolveClientId(): string {
    const existing = this.getClientId();
    if (existing) return existing;
    const generated = `client-${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;
    this.setClientId(generated);
    return generated;
  }
}

