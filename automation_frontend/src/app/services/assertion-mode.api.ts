import { Injectable, signal } from '@angular/core';

export interface AssertionCoords {
  x: number;
  y: number;
}

/**
 * Shared service for managing assertion mode state across components.
 * - Toolbar updates activeMode when user toggles assertion mode
 * - BrowserView reads activeMode to emit hover events
 * - BrowserView updates detectedAssertionMode/Data/Coords/PageUrl when backend discovers assertions
 * - Status sidebar displays detected assertions when activeMode is enabled, and forwards
 *   coords/pageUrl back to the backend when the user saves one
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
  // Where on the page the assertion was captured, and which page — needed to persist the step
  readonly detectedAssertionCoords = signal<AssertionCoords | null>(null);
  readonly detectedAssertionPageUrl = signal<string | null>(null);

  // True once the user clicks an element to pin its assertion; hover updates pause until unlocked
  readonly locked = signal(false);

  setMode(mode: 'visibility' | 'text' | 'value' | 'snapshot' | null): void {
    this.activeMode.set(mode);
    this.locked.set(false);
  }

  setDetectedAssertion(
    mode: 'visibility' | 'text' | 'value' | 'snapshot' | null,
    data: any,
    coords: AssertionCoords | null = null,
    pageUrl: string | null = null,
  ): void {
    this.detectedAssertionMode.set(mode);
    this.detectedAssertionData.set(data);
    this.detectedAssertionCoords.set(coords);
    this.detectedAssertionPageUrl.set(pageUrl);
  }

  lock(): void {
    this.locked.set(true);
  }

  clearDetectedAssertion(): void {
    this.detectedAssertionMode.set(null);
    this.detectedAssertionData.set(null);
    this.detectedAssertionCoords.set(null);
    this.detectedAssertionPageUrl.set(null);
    this.locked.set(false);
  }
}
