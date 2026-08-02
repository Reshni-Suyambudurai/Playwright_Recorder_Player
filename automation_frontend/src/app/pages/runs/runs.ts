import { Component, ElementRef, inject, signal, computed, OnInit, OnDestroy, viewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RecordingsApi } from '../../services/recordings.api';
import { PlaybackApi, PlayEvent } from '../../services/playback.api';
import { PlaybackStateApi } from '../../services/playback-state.api';
import { RecordingListItem, RecordingDetail, RecordingStep, InputDetectedData } from '../../types/websocket';
import { SvgIcon } from '../../components/svg-icon/svg-icon';
import { StepList } from '../../components/step-list/step-list';
import { InputOverlay } from '../../components/input-overlay/input-overlay';

export interface TabGroup {
  tabId: string;
  url: string;
  steps: RecordingStep[];
}

@Component({
  selector: 'app-runs',
  standalone: true,
  imports: [SvgIcon, FormsModule, StepList, InputOverlay],
  templateUrl: './runs.html',
  styleUrl: './runs.css',
})

export class Runs implements OnInit, OnDestroy {
  private api = inject(RecordingsApi);
  private playbackApi = inject(PlaybackApi);
  readonly state = inject(PlaybackStateApi);

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

  // Direct DOM reference — we set img.src directly to bypass Angular zone
  private _frameImgRef = viewChild<ElementRef<HTMLImageElement>>('frameImg');

  // Pause-time input overlay
  readonly pauseInputData   = signal<InputDetectedData | null>(null);
  readonly pauseOverlayX    = signal(0);
  readonly pauseOverlayY    = signal(0);

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

  readonly tabGroups = computed(() => {
    const d = this.detail();
    if (!d) return [];
    return Object.entries(d.steps).map(([tabId, groups]) => {
      const allSteps = (groups as RecordingStep[][]).flat();
      const nav = allSteps.find(s => s.type === 'NAVIGATE');
      const url = nav?.url ?? nav?.pageUrl ?? tabId;
      return { tabId, url, steps: allSteps };
    });
  });

  formatDate(ts: number | null | undefined): string {
    if (!ts) return '';
    return new Date(ts).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
  }

  setEditValue(stepId: number, value: string): void {
    const m = new Map(this.editValues());
    m.set(stepId, value);
    this.editValues.set(m);
    this.saveSuccess.set(false);
  }

  toggleShouldRun(stepId: number, current: boolean): void {
    const m = new Map(this.shouldRunState());
    m.set(stepId, !current);
    this.shouldRunState.set(m);
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

    this.state.resetForNewRun();
    this._disconnectPlay();

    try {
      const { play_session_id } = await this.playbackApi.startPlay(payload);

      this._playWs = this.playbackApi.connectWs(play_session_id, this._clientId, {
        onEvent: (evt: PlayEvent) => {
          if (evt.event_type !== 'FRAME') console.log('[PLAY WS event]', evt.event_type, evt.data);
          this._onPlayEvent(evt);
        },
        onClose: () => {
          console.warn('[PLAY WS] connection closed, status was:', this.state.playStatus());
          if (this.state.playStatus() === 'running' || this.state.playStatus() === 'paused') {
            this.state.playStatus.set('done');
          }
        },
        onError: (e) => {
          console.error('[PLAY WS] error:', e);
          this.state.playStatus.set('error');
        },
      });
    } catch (e: any) {
      this.state.playStatus.set('error');
      this.state.playError.set(e?.message ?? 'Failed to start playback');
    }
  }

  onResumeClick(): void {
    if (this._playWs && this._playWs.readyState === WebSocket.OPEN) {
      this._playWs.send(JSON.stringify({ event_type: 'PLAY_RESUME', data: {} }));
      this.state.playStatus.set('running');
    }
  }

  onStopClick(): void {
    if (this._playWs && this._playWs.readyState === WebSocket.OPEN) {
      this._playWs.send(JSON.stringify({ event_type: 'PLAY_STOP', data: {} }));
    }
    this.state.playStatus.set('stopped');
    this.state.hasLiveFrame.set(false);
    this._disconnectPlay();
  }

  onFrameClick(event: MouseEvent): void {
    if (this.state.playStatus() !== 'paused') return;
    if ((event.target as HTMLElement).tagName === 'BUTTON') return;
    const img = this._frameImgRef()?.nativeElement;
    if (!img || !this._playWs || this._playWs.readyState !== WebSocket.OPEN) return;

    const coords = this._toPageCoords(event.clientX, event.clientY, img);
    if (!coords) return;
    this._playWs.send(JSON.stringify({ event_type: 'PAUSE_CLICK', data: coords }));
  }

  onFrameWheel(event: WheelEvent): void {
    if (this.state.playStatus() !== 'paused') return;
    event.preventDefault();
    const img = this._frameImgRef()?.nativeElement;
    if (!img || !this._playWs || this._playWs.readyState !== WebSocket.OPEN) return;

    const coords = this._toPageCoords(event.clientX, event.clientY, img);
    if (!coords) return;
    this._playWs.send(JSON.stringify({
      event_type: 'PAUSE_SCROLL',
      data: { ...coords, delta_y: event.deltaY }
    }));
  }

  /**
   * Maps a viewport click position to page coordinates (1280×720).
   * Accounts for object-fit: contain — the screenshot is letterboxed inside
   * the <img> element, so raw element-relative coords would be wrong.
   * Returns null if the click landed outside the rendered image area.
   */
  private _showPauseInputOverlay(data: InputDetectedData): void {
    const img = this._frameImgRef()?.nativeElement;
    if (!img) { this.pauseInputData.set(data); return; }

    const rect = img.getBoundingClientRect();
    const PAGE_W = 1280, PAGE_H = 720;
    const contentAspect = PAGE_W / PAGE_H;
    const boxAspect     = rect.width / rect.height;
    let renderedW: number, renderedH: number, offsetX: number, offsetY: number;
    if (boxAspect > contentAspect) {
      renderedH = rect.height; renderedW = renderedH * contentAspect;
      offsetX = (rect.width - renderedW) / 2; offsetY = 0;
    } else {
      renderedW = rect.width; renderedH = renderedW / contentAspect;
      offsetX = 0; offsetY = (rect.height - renderedH) / 2;
    }
    const scaleX = renderedW / PAGE_W;
    const scaleY = renderedH / PAGE_H;
    // Position relative to .player-screen container
    const containerRect = (img.closest('.player-screen') as HTMLElement)?.getBoundingClientRect() ?? rect;
    this.pauseOverlayX.set(Math.round(data.x * scaleX + (rect.left - containerRect.left) + offsetX));
    this.pauseOverlayY.set(Math.round(data.y * scaleY + (rect.top  - containerRect.top)  + offsetY));
    this.pauseInputData.set(data);
  }

  onPauseTypeConfirm(text: string): void {
    const data = this.pauseInputData();
    this.pauseInputData.set(null);
    if (!data?.selector || !this._playWs || this._playWs.readyState !== WebSocket.OPEN) return;
    this._playWs.send(JSON.stringify({
      event_type: 'PAUSE_TYPE',
      data: { selector: data.selector, text },
    }));
  }

  onPauseTypeCancel(): void {
    this.pauseInputData.set(null);
  }

  private _toPageCoords(
    clientX: number,
    clientY: number,
    img: HTMLImageElement,
  ): { x: number; y: number } | null {
    const rect = img.getBoundingClientRect();
    const PAGE_W = 1280, PAGE_H = 720;
    const contentAspect = PAGE_W / PAGE_H;
    const boxAspect     = rect.width / rect.height;

    let renderedW: number, renderedH: number, offsetX: number, offsetY: number;
    if (boxAspect > contentAspect) {
      // Box is wider than content — horizontal pillarboxing
      renderedH = rect.height;
      renderedW = renderedH * contentAspect;
      offsetX   = (rect.width - renderedW) / 2;
      offsetY   = 0;
    } else {
      // Box is taller than content — vertical letterboxing
      renderedW = rect.width;
      renderedH = renderedW / contentAspect;
      offsetX   = 0;
      offsetY   = (rect.height - renderedH) / 2;
    }

    const relX = clientX - rect.left - offsetX;
    const relY = clientY - rect.top  - offsetY;

    // Click was in the padding area, not on the actual screenshot
    if (relX < 0 || relY < 0 || relX > renderedW || relY > renderedH) return null;

    return {
      x: Math.round((relX / renderedW) * PAGE_W),
      y: Math.round((relY / renderedH) * PAGE_H),
    };
  }

  private _onPlayEvent(evt: PlayEvent): void {
    // Handle pause-type overlay events before the state machine
    if (evt.event_type === 'PAUSE_INPUT_DETECTED') {
      this._showPauseInputOverlay(evt.data as InputDetectedData);
      return;
    }

    const isFrame = this.state.handleEvent(evt);
    if (!isFrame) return;

    // ── FRAME: rAF-throttled render to bypass Angular zone ─────────────
    this._latestFrameData = (evt.data as { image: string }).image;
    if (!this._frameRafPending) {
      this._frameRafPending = true;
      requestAnimationFrame(() => {
        this._frameRafPending = false;
        const data = this._latestFrameData;
        this._latestFrameData = null;
        if (!data) return;

        const img = this._frameImgRef()?.nativeElement;
        if (img) {
          img.src = data;
          if (!this.state.hasLiveFrame()) this.state.hasLiveFrame.set(true);
        }
      });
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
