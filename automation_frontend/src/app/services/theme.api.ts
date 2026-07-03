import { effect, inject, Injectable, signal, WritableSignal } from '@angular/core';
import { TokenStore } from './token-store.api';

@Injectable({ providedIn: 'root' })
export class ThemeApi {
  private tokenStore = inject(TokenStore);

  readonly isDark: WritableSignal<boolean> = signal(this.resolveInitialTheme());

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
  }

  toggle(): void {
    this.isDark.update(v => !v);
    // DOM + localStorage update is handled entirely by the effect above.
  }

  private resolveInitialTheme(): boolean {
    const saved = this.tokenStore.getTheme();
    if (saved !== null) return saved === 'dark';
    return window.matchMedia('(prefers-color-scheme: dark)').matches;
  }
}

