import { Component, ElementRef, inject, signal, OnInit, OnDestroy, viewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RecordingsApi } from '../../services/recordings.api';
import { PlaybackApi, PlayEvent } from '../../services/playback.api';
import { RecordingListItem, RecordingDetail, RecordingStep } from '../../types/websocket';
import { SvgIcon } from '../../components/svg-icon/svg-icon';
import { TooltipDirective } from '../../directives/tooltip/tooltip.directive';

export interface TabGroup {
  tabId: string;
  url: string;
  steps: RecordingStep[];
}

@Component({
  selector: 'app-runs',
  standalone: true,
  imports: [SvgIcon, FormsModule, TooltipDirective],
  templateUrl: './runs.html',
  styleUrl: './runs.css',
})
export class Runs implements OnInit, OnDestroy {
  private api = inject(RecordingsApi);
  private playbackApi = inject(PlaybackApi);

  readonly recordings = signal<RecordingListItem[]>([]);
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);
  readonly selectedId = signal<string>('');
  readonly detail = signal<RecordingDetail | null>(null);
  readonly detailLoading = signal(false);

  /** Locally edited text values keyed by step.id */
  readonly editValues = signal<Map<number, string>>(new Map());
  /** Locally toggled `shouldRun` state keyed by step.id */
  readonly shouldRunState = signal<Map<number, boolean>>(new Map());
  /** Locally toggled `pause` state keyed by step.id */
  readonly pauseState = signal<Map<number, boolean>>(new Map());

  readonly saving = signal(false);
  readonly saveError = signal<string | null>(null);
  readonly saveSuccess = signal(false);

  // ── Playback state ──────────────────────────────────────────────────────
  /** 'idle' | 'running' | 'paused' | 'done' | 'error' | 'stopped' */
  readonly playStatus    = signal<string>('idle');
  readonly currentStep   = signal<number>(0);
  readonly totalSteps    = signal<number>(0);
  readonly currentType   = signal<string>('');
  readonly currentStepId = signal<number | null>(null);
  readonly playError     = signal<string | null>(null);
  readonly failedCount   = signal<number>(0);         // steps that errored during run
  readonly hasLiveFrame  = signal<boolean>(false);

  // Direct DOM reference — we set img.src directly to bypass Angular zone
  private _frameImgRef = viewChild<ElementRef<HTMLImageElement>>('frameImg');

  private _playWs: WebSocket | null = null;
  private _clientId = `client-${Math.random().toString(36).slice(2)}`;

  // rAF throttle — only write one frame per browser paint cycle
  private _latestFrameData: string | null = null;
  private _frameRafPending = false;

  async ngOnInit(): Promise<void> {
    try {
      const list = await this.api.listRecordings();
      this.recordings.set(list);
    } catch (e: any) {
      this.error.set(e?.message ?? 'Failed to load recordings');
    } finally {
      this.loading.set(false);
    }
  }

  async onSelect(event: Event): Promise<void> {
    const id = (event.target as HTMLSelectElement).value;
    this.selectedId.set(id);
    this.detail.set(null);
    this.editValues.set(new Map());
    this.shouldRunState.set(new Map());
    this.pauseState.set(new Map());
    this.saveError.set(null);
    this.saveSuccess.set(false);
    if (!id) return;
    this.detailLoading.set(true);
    try {
      const d = await this.api.getRecording(id);
      this.detail.set(d);
    } catch {
      this.detail.set(null);
    } finally {
      this.detailLoading.set(false);
    }
  }

  selectedRecording(): RecordingListItem | undefined {
    return this.recordings().find(r => r.recordId === this.selectedId());
  }

  tabGroups(detail: RecordingDetail): TabGroup[] {
    return Object.entries(detail.steps).map(([tabId, groups]) => {
      const allSteps = (groups as RecordingStep[][]).flat();
      const nav = allSteps.find(s => s.type === 'NAVIGATE');
      const url = nav?.url ?? nav?.pageUrl ?? tabId;
      return { tabId, url, steps: allSteps };
    });
  }

  stepIcon(type: string): string {
    const icons: Record<string, string> = {
      NAVIGATE: '🌐', CLICK: '🖱️', TYPE: '⌨️',
      SCROLL: '↕️', KEY: '⌨️',
    };
    return icons[type] ?? '•';
  }

  stepLabel(step: RecordingStep): string {
    if (step.type === 'NAVIGATE') return step.url ?? step.pageUrl ?? '';
    if (step.type === 'TYPE') return step.text ? `"${step.text}"` : '';
    if (step.type === 'CLICK') return step.label ?? (step.coords ? `(${step.coords.x}, ${step.coords.y})` : '');
    if (step.type === 'SCROLL') return step.coords ? `(${step.coords.x}, ${step.coords.y})` : '';
    if (step.type === 'KEY') return step.text ?? '';
    return '';
  }

  formatDate(ts: number | null | undefined): string {
    if (!ts) return '';
    return new Date(ts).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
  }

  getEditValue(step: RecordingStep): string {
    const m = this.editValues();
    const raw = m.has(step.id) ? (m.get(step.id) ?? '') : (step.text ?? '');
    // If the stored value is a template placeholder like {{password}}, leave the input empty
    return /^\{\{.+\}\}$/.test(raw.trim()) ? '' : raw;
  }

  setEditValue(stepId: number, value: string): void {
    const m = new Map(this.editValues());
    m.set(stepId, value);
    this.editValues.set(m);
    this.saveSuccess.set(false);
  }

  getShouldRun(step: RecordingStep): boolean {
    const m = this.shouldRunState();
    return m.has(step.id) ? (m.get(step.id) ?? true) : (step.shouldRun ?? true);
  }

  toggleShouldRun(stepId: number, current: boolean): void {
    const m = new Map(this.shouldRunState());
    m.set(stepId, !current);
    this.shouldRunState.set(m);
  }

  getPause(step: RecordingStep): boolean {
    const m = this.pauseState();
    return m.has(step.id) ? (m.get(step.id) ?? false) : (step.pause ?? false);
  }

  togglePause(stepId: number, current: boolean): void {
    const m = new Map(this.pauseState());
    m.set(stepId, !current);
    this.pauseState.set(m);
  }

  hasEdits(): boolean {
    // Enable saving whenever a recording is loaded (user may have filled in values)
    if (this.detail()) return true;
    return this.editValues().size > 0;
  }

  ngOnDestroy(): void {
    this._disconnectPlay();
  }

  // ── Playback helpers ────────────────────────────────────────────────────
  private _disconnectPlay(): void {
    if (this._playWs && this._playWs.readyState < WebSocket.CLOSING) {
      this._playWs.close();
    }
    this._playWs = null;
  }

  /** Build step payload: merges shouldRun, pause, and typed values (including passwords for runtime). */
  private _buildPlayPayload(): RecordingDetail | null {
    const current = this.detail();
    if (!current) return null;

    const edits        = this.editValues();
    const shouldRunMap = this.shouldRunState();
    const pauseMap     = this.pauseState();

    const updatedSteps: Record<string, RecordingStep[][]> = {};
    for (const [tabId, groups] of Object.entries(current.steps)) {
      updatedSteps[tabId] = (groups as RecordingStep[][]).map(group =>
        group.map(step => {
          let s: RecordingStep = { ...step };
          if (shouldRunMap.has(step.id)) s = { ...s, shouldRun: shouldRunMap.get(step.id)! };
          if (pauseMap.has(step.id))     s = { ...s, pause: pauseMap.get(step.id)! };
          // For playback: use the runtime-typed value even for password fields
          if (edits.has(step.id) && edits.get(step.id)) {
            s = { ...s, text: edits.get(step.id)! };
          }
          return s;
        })
      );
    }

    return { ...current, steps: updatedSteps };
  }

  async onRunClick(): Promise<void> {
    const payload = this._buildPlayPayload();
    if (!payload) return;

    this.playStatus.set('running');
    this.playError.set(null);
    this.failedCount.set(0);
    this.hasLiveFrame.set(false);
    this.currentStep.set(0);
    this.totalSteps.set(0);
    this._disconnectPlay();

    try {
      const { play_session_id } = await this.playbackApi.startPlay(payload);

      this._playWs = this.playbackApi.connectWs(play_session_id, this._clientId, {
        onEvent: (evt: PlayEvent) => {
          if (evt.event_type !== 'FRAME') console.log('[PLAY WS event]', evt.event_type, evt.data);
          this._onPlayEvent(evt);
        },
        onClose: ()  => {
          console.warn('[PLAY WS] connection closed, status was:', this.playStatus());
          if (this.playStatus() === 'running' || this.playStatus() === 'paused') {
            this.playStatus.set('done');
          }
        },
        onError: (e) => {
          console.error('[PLAY WS] error:', e);
          this.playStatus.set('error');
        },
      });
    } catch (e: any) {
      this.playStatus.set('error');
      this.playError.set(e?.message ?? 'Failed to start playback');
    }
  }

  onResumeClick(): void {
    if (this._playWs && this._playWs.readyState === WebSocket.OPEN) {
      this._playWs.send(JSON.stringify({ event_type: 'PLAY_RESUME', data: {} }));
      this.playStatus.set('running');
    }
  }

  onStopClick(): void {
    if (this._playWs && this._playWs.readyState === WebSocket.OPEN) {
      this._playWs.send(JSON.stringify({ event_type: 'PLAY_STOP', data: {} }));
    }
    this.playStatus.set('stopped');
    this.hasLiveFrame.set(false);
    this._disconnectPlay();
  }

  private _onPlayEvent(evt: PlayEvent): void {
    switch (evt.event_type) {
      case 'PLAY_STEP_START': {
        const d = evt.data as any;
        this.currentStep.set(d.index);
        this.totalSteps.set(d.total);
        this.currentType.set(d.type);
        this.currentStepId.set(d.stepId);
        this.playError.set(null);
        this.playStatus.set('running');
        // Scroll active step into view
        setTimeout(() => {
          document.getElementById(`play-step-${d.stepId}`)?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }, 50);
        break;
      }
      case 'PLAY_PAUSED':
        this.currentStep.set((evt.data as any).index);
        this.playStatus.set('paused');
        break;
      case 'PLAY_DONE': {
        const d = evt.data as any;
        this.totalSteps.set(d.stepCount ?? this.totalSteps());
        this.failedCount.set(d.failedCount ?? 0);
        this.playStatus.set(d.failedCount > 0 ? 'done_with_errors' : 'done');
        break;
      }
      case 'PLAY_STEP_ERROR':
        // Non-fatal step error — show briefly in overlay but don't stop
        this.playError.set((evt.data as any).error ?? 'Step failed');
        break;
      case 'PLAY_ERROR':
        this.playStatus.set('error');
        this.playError.set((evt.data as any).error ?? 'Unknown error');
        break;
      case 'FRAME': {
        // Store latest frame — discard any queued intermediate frames
        this._latestFrameData = (evt.data as any).image;
        console.log('[FRAME] received, size:', this._latestFrameData?.length, 'rafPending:', this._frameRafPending);
        if (!this._frameRafPending) {
          this._frameRafPending = true;
          requestAnimationFrame(() => {
            this._frameRafPending = false;
            const data = this._latestFrameData;
            this._latestFrameData = null;
            if (!data) { console.warn('[FRAME] rAF fired but data was null'); return; }

            const imgEl = this._frameImgRef();
            const img   = imgEl?.nativeElement;
            console.log('[FRAME] rAF commit — imgEl:', !!imgEl, 'nativeElement:', !!img, 'hasLiveFrame:', this.hasLiveFrame(), 'size:', data.length);

            if (img) {
              img.src = data;
              console.log('[FRAME] img.src SET — img connected:', img.isConnected, 'offsetParent:', img.offsetParent, 'display:', getComputedStyle(img).display, 'width:', img.offsetWidth);
              if (!this.hasLiveFrame()) this.hasLiveFrame.set(true);
            } else {
              console.error('[FRAME] ❌ frameImg nativeElement is null — viewChild not resolving. hasLiveFrame:', this.hasLiveFrame());
            }
          });
        } else {
          console.log('[FRAME] dropped intermediate (rAF pending), keeping latest');
        }
        break;
      }
    }
  }

  async saveEdits(): Promise<void> {
    const current = this.detail();
    const id = this.selectedId();
    if (!current || !id || !this.hasEdits()) return;

    this.saving.set(true);
    this.saveError.set(null);
    this.saveSuccess.set(false);

    try {
      // Build updated steps with edited text values and shouldRun toggles merged in
      const updatedSteps: Record<string, RecordingStep[][]> = {};
      const edits = this.editValues();
      const shouldRunEdits = this.shouldRunState();
      const pauseEdits = this.pauseState();

      for (const [tabId, groups] of Object.entries(current.steps)) {
        updatedSteps[tabId] = (groups as RecordingStep[][]).map(group =>
          group.map(step => {
            let updated = step;
            if (shouldRunEdits.has(step.id)) {
              updated = { ...updated, shouldRun: shouldRunEdits.get(step.id)! };
            }
            if (pauseEdits.has(step.id)) {
              updated = { ...updated, pause: pauseEdits.get(step.id)! };
            }
            if (edits.has(step.id) && !step.isPassword) {
              updated = { ...updated, text: edits.get(step.id)! };
            }
            return updated;
          })
        );
      }

      const updatedRecording: RecordingDetail = {
        ...current,
        meta: { ...current.meta, updatedAt: Date.now() },
        steps: updatedSteps,
      };
      await this.api.saveRecording(id, updatedRecording);
      // Refresh local detail so saved values become canonical
      this.detail.set(updatedRecording);
      this.editValues.set(new Map());
      this.shouldRunState.set(new Map());
      this.pauseState.set(new Map());
      this.saveSuccess.set(true);
    } catch (e: any) {
      this.saveError.set(e?.message ?? 'Save failed');
    } finally {
      this.saving.set(false);
    }
  }
}
