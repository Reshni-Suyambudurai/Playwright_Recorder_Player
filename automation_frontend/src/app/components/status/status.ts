import { Component, computed, inject, OnDestroy, OnInit, signal } from '@angular/core';
import { NgClass } from '@angular/common';
import { WebsocketApi } from '../../services/websocket.api';
import { NavigationApi } from '../../services/navigation.api';
import { AssertionModeApi } from '../../services/assertion-mode.api';
import { RecordingStepSummary } from '../../types/websocket';
import { Subscription } from 'rxjs';

@Component({
  selector: 'app-status',
  standalone: true,
  imports: [NgClass],
  templateUrl: './status.html',
  styleUrl: './status.css',
})
export class Status implements OnInit, OnDestroy {
  private websocketApi = inject(WebsocketApi);
  private navigationApi = inject(NavigationApi);
  private assertionModeApi = inject(AssertionModeApi);
  private sub?: Subscription;

  readonly connectionState = this.websocketApi.connectionState;
  readonly navigationState = this.navigationApi.navigationState;
  readonly recordedSteps = signal<RecordingStepSummary[]>([]);
  readonly lastRecordingName = signal<string>('');

  // Assertion display signals
  readonly assertionMode = this.assertionModeApi.detectedAssertionMode;
  readonly assertionData = this.assertionModeApi.detectedAssertionData;
  readonly isAsserting = computed(() => !!this.assertionMode());

  ngOnInit(): void {
    this.sub = this.websocketApi.recordingStopped$.subscribe(data => {
      this.recordedSteps.set(data.steps);
      this.lastRecordingName.set(data.recording_name);
    });
    this.websocketApi.disconnected$.subscribe(() => {
      this.recordedSteps.set([]);
      this.lastRecordingName.set('');
    });
  }

  ngOnDestroy(): void {
    this.sub?.unsubscribe();
  }

  saveAssertion(): void {
    // Send assertion save event to backend via WebSocket
    const mode = this.assertionMode();
    const data = this.assertionData();
    if (mode && data) {
      if (mode === 'snapshot') {
        // Snapshot assertions use the specific snapshot save method
        this.websocketApi.sendSnapshotSaveAssertion(data);
      } else {
        // Other assertion types (visibility, text, value)
        this.websocketApi.sendAssertionSave(
          mode as 'visibility' | 'text' | 'value',
          data
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

  formatTime(date: Date | null): string {
    if (!date) return '-';
    return new Date(date).toLocaleTimeString();
  }

  stepIcon(type: string): string {
    const icons: Record<string, string> = {
      NAVIGATE: '🌐', CLICK: '🖱️', TYPE: '⌨️',
      SCROLL: '↕️', KEY: '⌥',
    };
    return icons[type] ?? '▸';
  }
}
