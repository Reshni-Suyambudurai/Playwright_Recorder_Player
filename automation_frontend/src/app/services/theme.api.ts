import { effect, inject, Injectable, signal, WritableSignal } from '@angular/core';
import { TokenStore } from './token-store.api';

@Injectable({ providedIn: 'root' })
export class ThemeApi {
  private tokenStore = inject(TokenStore);

  readonly isDark: WritableSignal<boolean> = signal(this.resolveInitialTheme());
  readonly isSidebarOpen: WritableSignal<boolean> = signal(this.resolveInitialSidebar());

  constructor() {
    /**
     * effect() is the Angular 21 way to handle reactive side effects.
     * Runs once on init and every time isDark changes — no manual DOM
     * calls needed in toggle().
     */
    effect(() => {
      const dark = this.isDark();
      document.documentElement.classList.toggle('dark', dark);
      this.tokenStore.setTheme(dark ? 'dark' : 'light');
    });

    effect(() => {
      this.tokenStore.setSidebarOpen(this.isSidebarOpen());
    });
  }

  toggle(): void {
    this.isDark.update(v => !v);
  }

  toggleSidebar(): void {
    this.isSidebarOpen.update(v => !v);
  }

  private resolveInitialTheme(): boolean {
    const saved = this.tokenStore.getTheme();
    if (saved !== null) return saved === 'dark';
    return window.matchMedia('(prefers-color-scheme: dark)').matches;
  }

  private resolveInitialSidebar(): boolean {
    const saved = this.tokenStore.getSidebarOpen();
    return saved !== null ? saved : true; // default: open
  }
}

