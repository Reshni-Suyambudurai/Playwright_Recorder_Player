import { Injectable, signal } from '@angular/core';
import { PlayEvent, FailedStep } from './playback.api';

/**
 * Owns all reactive playback state and handles incoming WebSocket events.
 * The component keeps only the WS connection + rAF/frame rendering.
 */
@Injectable({ providedIn: 'root' })
export class PlaybackStateApi {
  /** 'idle' | 'running' | 'paused' | 'done' | 'done_with_errors' | 'error' | 'stopped' */
  readonly playStatus    = signal<string>('idle');
  readonly currentStep   = signal<number>(0);
  readonly totalSteps    = signal<number>(0);
  readonly currentType   = signal<string>('');
  readonly currentStepId = signal<number | null>(null);
  readonly playError     = signal<string | null>(null);
  readonly failedCount   = signal<number>(0);
  readonly failedSteps   = signal<FailedStep[]>([]);
  readonly hasLiveFrame  = signal<boolean>(false);

  /** Reset all state before a new run starts. */
  resetForNewRun(): void {
    this.playStatus.set('running');
    this.playError.set(null);
    this.failedCount.set(0);
    this.failedSteps.set([]);
    this.hasLiveFrame.set(false);
    this.currentStep.set(0);
    this.totalSteps.set(0);
    this.currentStepId.set(null);
    this.currentType.set('');
  }

  /**
   * Process a WebSocket event and update signals accordingly.
   * Returns `true` when the event is a FRAME — caller must handle rendering.
   */
  handleEvent(evt: PlayEvent): boolean {
    switch (evt.event_type) {
      case 'PLAY_STEP_START': {
        const d = evt.data as { stepId: number; index: number; total: number; type: string };
        this.currentStep.set(d.index);
        this.totalSteps.set(d.total);
        this.currentType.set(d.type);
        this.currentStepId.set(d.stepId);
        this.playError.set(null);
        this.playStatus.set('running');
        setTimeout(() => {
          document.getElementById(`play-step-${d.stepId}`)?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }, 50);
        break;
      }
      case 'PLAY_PAUSED': {
        const d = evt.data as { stepId: number; index: number; error?: string };
        this.currentStep.set(d.index);
        if (d.error) this.playError.set(d.error);
        this.playStatus.set('paused');
        break;
      }
      case 'PLAY_DONE': {
        const d = evt.data as { stepCount: number; failedCount: number; failedSteps: FailedStep[]; message: string };
        this.totalSteps.set(d.stepCount ?? this.totalSteps());
        this.failedCount.set(d.failedCount ?? 0);
        this.failedSteps.set(d.failedSteps ?? []);
        this.playStatus.set(d.failedCount > 0 ? 'done_with_errors' : 'done');
        break;
      }
      case 'PLAY_STEP_ERROR': {
        const d = evt.data as { error: string };
        this.playError.set(d.error ?? 'Step failed');
        break;
      }
      case 'PLAY_ERROR': {
        const d = evt.data as { error: string };
        this.playStatus.set('error');
        this.playError.set(d.error ?? 'Unknown error');
        break;
      }
      case 'FRAME':
        return true; // caller handles rendering
    }
    return false;
  }
}
