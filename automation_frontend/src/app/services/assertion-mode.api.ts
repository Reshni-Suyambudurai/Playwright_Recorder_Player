import { Injectable, signal } from '@angular/core';

/**
 * Shared service for managing assertion mode state across components.
 * - Toolbar updates activeMode when user toggles assertion mode
 * - BrowserView reads activeMode to emit hover events
 * - BrowserView updates detectedAssertionMode/Data when backend discovers assertions
 * - Status sidebar displays detected assertions when activeMode is enabled
 * - `locked` freezes further hover-driven updates once the user clicks an element,
 *   until they Save or Dismiss it from the status sidebar
 */
@Injectable({
  providedIn: 'root',
})
export class AssertionModeApi {
  // User-selected assertion mode from toolbar
  readonly activeMode = signal<'visibility' | 'text' | 'value' | 'snapshot' | null>(null);

  // Detected assertion from backend (updated by browser-view)
  readonly detectedAssertionMode = signal<'visibility' | 'text' | 'value' | 'snapshot' | null>(null);
  readonly detectedAssertionData = signal<any>(null);

  // True once the user clicks an element to pin its assertion; hover updates pause until unlocked
  readonly locked = signal(false);

  setMode(mode: 'visibility' | 'text' | 'value' | 'snapshot' | null): void {
    this.activeMode.set(mode);
    this.locked.set(false);
  }

  setDetectedAssertion(
    mode: 'visibility' | 'text' | 'value' | 'snapshot' | null,
    data: any
  ): void {
    this.detectedAssertionMode.set(mode);
    this.detectedAssertionData.set(data);
  }

  lock(): void {
    this.locked.set(true);
  }

  clearDetectedAssertion(): void {
    this.detectedAssertionMode.set(null);
    this.detectedAssertionData.set(null);
    this.locked.set(false);
  }
}
