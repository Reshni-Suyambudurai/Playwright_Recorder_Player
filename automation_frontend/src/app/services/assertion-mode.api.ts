import { Injectable, signal } from '@angular/core';

/**
 * Shared service for managing assertion mode state across components.
 * - Toolbar updates the mode when user toggles assertion mode
 * - BrowserView reads the mode to emit hover events
 */
@Injectable({
  providedIn: 'root',
})
export class AssertionModeApi {
  readonly activeMode = signal<'visibility' | 'text' | 'value' | null>(null);

  setMode(mode: 'visibility' | 'text' | 'value' | null): void {
    this.activeMode.set(mode);
  }
}
