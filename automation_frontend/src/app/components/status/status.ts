import { Component, inject, OnDestroy, OnInit, signal } from '@angular/core';
import { NgClass } from '@angular/common';
import { WebsocketApi } from '../../services/websocket.api';
import { NavigationApi } from '../../services/navigation.api';
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
  private sub?: Subscription;

  readonly connectionState = this.websocketApi.connectionState;
  readonly navigationState = this.navigationApi.navigationState;
  readonly recordedSteps = signal<RecordingStepSummary[]>([]);
  readonly lastRecordingName = signal<string>('');

  ngOnInit(): void {
    this.sub = this.websocketApi.recordingStopped$.subscribe(data => {
      this.recordedSteps.set(data.steps);
      this.lastRecordingName.set(data.recording_name);
    });
  }

  ngOnDestroy(): void {
    this.sub?.unsubscribe();
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
