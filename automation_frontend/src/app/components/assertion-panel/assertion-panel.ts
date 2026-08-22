import { Component, computed, inject } from '@angular/core';
import { WebsocketApi } from '../../services/websocket.api';
import { AssertionModeApi } from '../../services/assertion-mode.api';

@Component({
  selector: 'app-assertion-panel',
  standalone: true,
  templateUrl: './assertion-panel.html',
  styleUrl: './assertion-panel.css',
})
export class AssertionPanel {
  private websocketApi = inject(WebsocketApi);
  private assertionModeApi = inject(AssertionModeApi);

  readonly assertionMode = this.assertionModeApi.detectedAssertionMode;
  readonly assertionData = this.assertionModeApi.detectedAssertionData;
  readonly isAsserting = computed(() => !!this.assertionMode());

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
}
