import { Component, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { WebsocketApi } from '../../services/websocket.api';
import { AssertionModeApi } from '../../services/assertion-mode.api';

@Component({
  selector: 'app-assertion-panel',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './assertion-panel.html',
  styleUrl: './assertion-panel.css',
})
export class AssertionPanel {
  private websocketApi = inject(WebsocketApi);
  private assertionModeApi = inject(AssertionModeApi);

  readonly assertionMode = this.assertionModeApi.detectedAssertionMode;
  readonly assertionData = this.assertionModeApi.detectedAssertionData;
  readonly isAsserting = computed(() => !!this.assertionMode());

  // New state for enhanced UX
  readonly isDiscovering = signal(false);
  readonly discoveryError = signal<string | null>(null);
  readonly stepCounter = signal({ current: 0, total: 0 });
  readonly showDropdownOptions = signal(false);
  readonly showAriaTree = signal(false);
  readonly copyFeedback = signal(false);

  // Mode labels
  readonly modeLabels: { [key: string]: string } = {
    visibility: 'Visibility',
    text: 'Text Content',
    value: 'Element Value',
    snapshot: 'Snapshot (ARIA)',
  };

  constructor() {
    // Track discovery state via WebSocket events
    this.websocketApi.assertionDiscovered$.subscribe(() => {
      this.isDiscovering.set(false);
      this.discoveryError.set(null);
    });
  }

  saveAssertion(): void {
    // Send assertion save event to backend via WebSocket
    const mode = this.assertionMode();
    const data = this.assertionData();
    const pageUrl = this.assertionModeApi.detectedAssertionPageUrl();
    if (mode && data) {
      if (mode === 'snapshot') {
        // Snapshot assertions use the specific snapshot save method
        this.websocketApi.sendSnapshotSaveAssertion({ ...data, pageUrl });
      } else {
        // Other assertion types (visibility, text, value)
        this.websocketApi.sendAssertionSave(
          mode as 'visibility' | 'text' | 'value',
          data,
          this.assertionModeApi.detectedAssertionCoords(),
          pageUrl,
        );
      }
    }
    // Clear the assertion display
    this.assertionModeApi.clearDetectedAssertion();
  }

  cancelAssertion(): void {
    // Clear the assertion display without saving
    this.assertionModeApi.clearDetectedAssertion();
  }

  formatRegion(region: { x: number; y: number; width: number; height: number } | undefined): string {
    if (!region) return '—';
    return `${region.width}×${region.height} @ (${region.x}, ${region.y})`;
  }

  getModeLabel(mode: string | null): string {
    return mode ? this.modeLabels[mode] || mode : '';
  }

  toggleDropdownOptions(): void {
    this.showDropdownOptions.update(val => !val);
  }

  toggleAriaTree(): void {
    this.showAriaTree.update(val => !val);
  }

  copyAriaTree(): void {
    const ariaText = this.assertionData()?.ariaSnapshot || '';
    if (ariaText) {
      navigator.clipboard.writeText(ariaText).then(() => {
        this.copyFeedback.set(true);
        setTimeout(() => {
          this.copyFeedback.set(false);
        }, 2000);
      });
    }
  }
}
