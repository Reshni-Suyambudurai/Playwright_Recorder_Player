import { Component, ElementRef, inject, signal, computed, OnInit, OnDestroy, viewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import dayjs from 'dayjs';
import customParseFormat from 'dayjs/plugin/customParseFormat';
import { RecordingsApi } from '../../services/recordings.api';
import { PlaybackApi, PlayEvent, RuntimePatchAck, RuntimeStepPatch } from '../../services/playback.api';
import { PlaybackStateApi } from '../../services/playback-state.api';
import { RecordingListItem, RecordingDetail, RecordingStep, InputDetectedData, InputValidation } from '../../types/websocket';
import { SvgIcon } from '../../components/svg-icon/svg-icon';
import { StepList } from '../../components/step-list/step-list';
import { InputOverlay } from '../../components/input-overlay/input-overlay';
import { InputOverlayConfirmPayload } from '../../components/input-overlay/input-overlay';
import { RunResultPopup } from '../../components/run-result-popup/run-result-popup';

dayjs.extend(customParseFormat);

const ACCEPTED_DATE_FORMATS = [
  'YYYY-MM-DD',
  'DD-MM-YYYY',
  'MM-DD-YYYY',
  'YYYY/MM/DD',
  'DD/MM/YYYY',
  'MM/DD/YYYY',
  'YYYY.MM.DD',
  'DD.MM.YYYY',
  'MM.DD.YYYY',
  'D MMM YYYY',
  'DD MMM YYYY',
  'MMM D, YYYY',
  'MMMM D, YYYY',
  'D MMMM YYYY',
  'YYYYMMDD',
];

export interface TabGroup {
  tabId: string;
  url: string;
  steps: RecordingStep[];
}

@Component({
  selector: 'app-runs',
  standalone: true,
  imports: [SvgIcon, FormsModule, StepList, InputOverlay, RunResultPopup],
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
  /** Live validation errors for TYPE steps keyed by step.id */
  readonly validationErrors = signal<Map<number, string>>(new Map());

  readonly saving = signal(false);
  readonly saveError = signal<string | null>(null);
  readonly saveSuccess = signal(false);
  readonly runtimeTrackingActive = signal(false);
  readonly runtimeAppliedShouldRunBaseline = signal<Map<number, boolean>>(new Map());
  readonly runtimeAppliedPauseBaseline = signal<Map<number, boolean>>(new Map());
  readonly runtimeRunStartShouldRunBaseline = signal<Map<number, boolean>>(new Map());
  readonly runtimeRunStartPauseBaseline = signal<Map<number, boolean>>(new Map());
  readonly runPopupVisible = signal(false);
  readonly runPopupTitle = signal('');
  readonly runPopupMessage = signal('');
  readonly runPopupVariant = signal<'success' | 'error'>('success');
  readonly runPopupAutoCloseMs = signal(2000);

  // Direct DOM reference — we set img.src directly to bypass Angular zone
  private _frameImgRef = viewChild<ElementRef<HTMLImageElement>>('frameImg');

  // Pause-time input overlay
  readonly pauseInputData   = signal<InputDetectedData | null>(null);
  readonly pauseOverlayX    = signal(0);
  readonly pauseOverlayY    = signal(0);

  private _playWs: WebSocket | null = null;
  private _clientId = `client-${Math.random().toString(36).slice(2)}`;
  private _successRefreshTimer: ReturnType<typeof setTimeout> | null = null;
  private _runtimePatchAckResolver: ((ack: RuntimePatchAck) => void) | null = null;
  private _lastErrorPopupKey = '';
  private _runtimeAutoPatchTimer: ReturnType<typeof setTimeout> | null = null;
  private _runtimePatchInFlight = false;
  private _runtimeAutoPatchQueued = false;

  // rAF throttle — only write one frame per browser paint cycle
  private _latestFrameData: string | null = null;
  private _frameRafPending = false;

  readonly isPlaybackActive = computed(() => {
    const status = this.state.playStatus();
    return status === 'running' || status === 'paused';
  });

  readonly shouldTrackRuntimeChanges = computed(
    () => this.runtimeTrackingActive() && this.isPlaybackActive()
  );

  private _showErrorPopupOnce(key: string, title: string, message: string): void {
    const normalized = message?.trim();
    if (!normalized) return;
    if (this._lastErrorPopupKey === key) return;
    this._lastErrorPopupKey = key;
    this._showRunPopup('error', title, normalized, 0);
  }

  private _captureRuntimeRunStartBaselines(): void {
    const current = this.detail();
    if (!current) {
      this.runtimeRunStartShouldRunBaseline.set(new Map());
      this.runtimeRunStartPauseBaseline.set(new Map());
      return;
    }

    const shouldRunBaseline = new Map<number, boolean>();
    const pauseBaseline = new Map<number, boolean>();

    for (const groups of Object.values(current.steps)) {
      for (const group of groups as RecordingStep[][]) {
        for (const step of group) {
          const effectiveShouldRun = this.shouldRunState().has(step.id)
            ? (this.shouldRunState().get(step.id) ?? (step.shouldRun ?? true))
            : (step.shouldRun ?? true);
          const effectivePause = this.pauseState().has(step.id)
            ? (this.pauseState().get(step.id) ?? (step.pause ?? false))
            : (step.pause ?? false);

          shouldRunBaseline.set(step.id, effectiveShouldRun);
          pauseBaseline.set(step.id, effectivePause);
        }
      }
    }

    this.runtimeRunStartShouldRunBaseline.set(shouldRunBaseline);
    this.runtimeRunStartPauseBaseline.set(pauseBaseline);
  }

  private _resetRuntimeTrackingState(): void {
    this.runtimeTrackingActive.set(false);
    this.runtimeAppliedShouldRunBaseline.set(new Map());
    this.runtimeAppliedPauseBaseline.set(new Map());
    this.runtimeRunStartShouldRunBaseline.set(new Map());
    this.runtimeRunStartPauseBaseline.set(new Map());
  }

  private _resetRuntimeState(): void {
    this._resetRuntimeTrackingState();
    this._runtimePatchInFlight = false;
    this._runtimeAutoPatchQueued = false;
    if (this._runtimeAutoPatchTimer) {
      clearTimeout(this._runtimeAutoPatchTimer);
      this._runtimeAutoPatchTimer = null;
    }
  }

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
    this.validationErrors.set(new Map());
    this.saveError.set(null);
    this.saveSuccess.set(false);
    this._resetRuntimeState();
    if (!id) return;
    this.detailLoading.set(true);
    try {
      const d = await this.api.getRecording(id);
      this.detail.set(d);
      this._recomputeValidationErrors();
    } catch {
      this.detail.set(null);
      this.validationErrors.set(new Map());
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
    this._recomputeValidationErrors();
    this.saveSuccess.set(false);
  }

  toggleShouldRun(stepId: number, current: boolean): void {
    const m = new Map(this.shouldRunState());
    m.set(stepId, !current);
    this.shouldRunState.set(m);
    this._recomputeValidationErrors();
    this._scheduleRuntimeAutoPatch();
  }

  togglePause(stepId: number, current: boolean): void {
    const m = new Map(this.pauseState());
    m.set(stepId, !current);
    this.pauseState.set(m);
    this._scheduleRuntimeAutoPatch();
  }

  hasEdits(): boolean {
    // Enable saving whenever a recording is loaded (user may have filled in values)
    if (this.detail()) return true;
    return this.editValues().size > 0;
  }

  ngOnDestroy(): void {
    this._clearSuccessRefreshTimer();
    this._disconnectPlay();
  }

  // ── Playback helpers ────────────────────────────────────────────────────
  private _disconnectPlay(): void {
    if (this._playWs && this._playWs.readyState < WebSocket.CLOSING) {
      this._playWs.close();
    }
    this._playWs = null;
    this._runtimePatchAckResolver = null;
    this._resetRuntimeTrackingState();
    if (this._runtimeAutoPatchTimer) {
      clearTimeout(this._runtimeAutoPatchTimer);
      this._runtimeAutoPatchTimer = null;
    }
    this._runtimePatchInFlight = false;
    this._runtimeAutoPatchQueued = false;
  }

  private _scheduleRuntimeAutoPatch(): void {
    if (!this.shouldTrackRuntimeChanges()) return;
    if (!this._playWs || this._playWs.readyState !== WebSocket.OPEN) return;

    if (this._runtimeAutoPatchTimer) {
      clearTimeout(this._runtimeAutoPatchTimer);
    }

    this._runtimeAutoPatchTimer = setTimeout(() => {
      this._runtimeAutoPatchTimer = null;
      void this._flushRuntimeAutoPatch();
    }, 150);
  }

  private async _flushRuntimeAutoPatch(): Promise<void> {
    if (!this.shouldTrackRuntimeChanges()) return;

    if (this._runtimePatchInFlight) {
      this._runtimeAutoPatchQueued = true;
      return;
    }

    const patches = this._buildRuntimeStepPatches();
    if (patches.length === 0) return;

    this._runtimePatchInFlight = true;
    try {
      const sent = this.playbackApi.sendPatchSteps(patches);
      if (!sent) {
        this._showErrorPopupOnce('runtime-apply-connection', 'Runtime Sync Failed', 'Playback connection is not available.');
        return;
      }

      const ack = await this._waitForRuntimePatchAck();
      if (!ack) {
        this._showErrorPopupOnce('runtime-apply-timeout', 'Runtime Sync Failed', 'Runtime update timed out. Try again.');
        return;
      }

      if (ack.unresolvedStepIds?.length) {
        const message = `Applied ${ack.appliedCount}/${ack.receivedCount}. Missing step IDs: ${ack.unresolvedStepIds.join(', ')}`;
        this._showErrorPopupOnce(`runtime-apply-unresolved-${ack.unresolvedStepIds.join('-')}`, 'Runtime Sync Failed', message);
      }

      const unresolved = new Set<number>(ack.unresolvedStepIds ?? []);
      const shouldRunBaseline = new Map(this.runtimeAppliedShouldRunBaseline());
      const pauseBaseline = new Map(this.runtimeAppliedPauseBaseline());
      for (const patch of patches) {
        if (unresolved.has(patch.stepId)) continue;
        if (typeof patch.shouldRun === 'boolean') {
          shouldRunBaseline.set(patch.stepId, patch.shouldRun);
        }
        if (typeof patch.pause === 'boolean') {
          pauseBaseline.set(patch.stepId, patch.pause);
        }
      }
      this.runtimeAppliedShouldRunBaseline.set(shouldRunBaseline);
      this.runtimeAppliedPauseBaseline.set(pauseBaseline);
    } finally {
      this._runtimePatchInFlight = false;
      if (this._runtimeAutoPatchQueued) {
        this._runtimeAutoPatchQueued = false;
        void this._flushRuntimeAutoPatch();
      }
    }
  }

  private _buildRuntimeStepPatches(): RuntimeStepPatch[] {
    const current = this.detail();
    if (!current) return [];
    if (!this.shouldTrackRuntimeChanges()) return [];

    const runStartShouldRunBaseline = this.runtimeRunStartShouldRunBaseline();
    const runStartPauseBaseline = this.runtimeRunStartPauseBaseline();
    const runtimeShouldRunBaseline = this.runtimeAppliedShouldRunBaseline();
    const runtimePauseBaseline = this.runtimeAppliedPauseBaseline();
    const baseFlags = new Map<number, { shouldRun: boolean; pause: boolean }>();
    for (const groups of Object.values(current.steps)) {
      for (const group of groups as RecordingStep[][]) {
        for (const step of group) {
          const runStartShouldRun = runStartShouldRunBaseline.has(step.id)
            ? (runStartShouldRunBaseline.get(step.id) ?? (step.shouldRun ?? true))
            : (step.shouldRun ?? true);
          const runStartPause = runStartPauseBaseline.has(step.id)
            ? (runStartPauseBaseline.get(step.id) ?? (step.pause ?? false))
            : (step.pause ?? false);
          const baseShouldRun = runtimeShouldRunBaseline.has(step.id)
            ? (runtimeShouldRunBaseline.get(step.id) ?? runStartShouldRun)
            : runStartShouldRun;
          const basePause = runtimePauseBaseline.has(step.id)
            ? (runtimePauseBaseline.get(step.id) ?? runStartPause)
            : runStartPause;
          baseFlags.set(step.id, {
            shouldRun: baseShouldRun,
            pause: basePause,
          });
        }
      }
    }

    const merged = new Map<number, RuntimeStepPatch>();
    for (const [stepId, shouldRun] of this.shouldRunState().entries()) {
      const base = baseFlags.get(stepId);
      if (!base || base.shouldRun === shouldRun) continue;
      merged.set(stepId, { ...(merged.get(stepId) ?? { stepId }), shouldRun });
    }

    for (const [stepId, pause] of this.pauseState().entries()) {
      const base = baseFlags.get(stepId);
      if (!base || base.pause === pause) continue;
      merged.set(stepId, { ...(merged.get(stepId) ?? { stepId }), pause });
    }

    return Array.from(merged.values());
  }

  private _waitForRuntimePatchAck(timeoutMs = 5000): Promise<RuntimePatchAck | null> {
    return new Promise((resolve) => {
      const timeout = setTimeout(() => {
        if (this._runtimePatchAckResolver) {
          this._runtimePatchAckResolver = null;
        }
        resolve(null);
      }, timeoutMs);

      this._runtimePatchAckResolver = (ack: RuntimePatchAck) => {
        clearTimeout(timeout);
        this._runtimePatchAckResolver = null;
        resolve(ack);
      };
    });
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
    const validationFailure = this._getFirstValidationFailure();
    if (validationFailure) {
      this._showRunPopup('error', 'Dynamic Input Validation Error', validationFailure, 0);
      return;
    }

    const payload = this._buildPlayPayload();
    if (!payload) return;

    this._clearSuccessRefreshTimer();
    this.closeRunPopup();
    this.state.resetForNewRun();
    this._disconnectPlay();
    this._lastErrorPopupKey = '';
    this._resetRuntimeState();

    try {
      const { play_session_id } = await this.playbackApi.startPlay(payload);

      this._playWs = this.playbackApi.connectWs(play_session_id, this._clientId, {
        onEvent: (evt: PlayEvent) => {
          if (evt.event_type !== 'FRAME') console.log('[PLAY WS event]', evt.event_type, evt.data);
          this._onPlayEvent(evt);
        },
        onClose: () => {
          console.warn('[PLAY WS] connection closed, status was:', this.state.playStatus());
          this._resetRuntimeTrackingState();
          if (this.state.playStatus() === 'running' || this.state.playStatus() === 'paused') {
            this.state.playStatus.set('done');
          }
        },
        onError: (e) => {
          console.error('[PLAY WS] error:', e);
          this.state.playStatus.set('error');
          this._showErrorPopupOnce('play-ws-error', 'Playback Error', 'Playback WebSocket connection error.');
        },
      });

      this._captureRuntimeRunStartBaselines();
      this.runtimeTrackingActive.set(true);
    } catch (e: any) {
      this.state.playStatus.set('error');
      const message = e?.message ?? 'Failed to start playback';
      this.state.playError.set(message);
      this._showErrorPopupOnce(`play-start-error-${message}`, 'Playback Error', message);
    }
  }

  onResumeClick(): void {
    if (this._playWs && this._playWs.readyState === WebSocket.OPEN) {
      this._playWs.send(JSON.stringify({ event_type: 'PLAY_RESUME', data: {} }));
      this.state.playStatus.set('running');
    }
  }

  onStopClick(): void {
    // UX decision: Stop acts as Pause for now.
    // Keep the WS session alive so Resume can continue from current step.
    this.state.playStatus.set('paused');
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

  onPauseTypeConfirm(payload: InputOverlayConfirmPayload): void {
    const data = this.pauseInputData();
    this.pauseInputData.set(null);
    if (!data?.selector || !this._playWs || this._playWs.readyState !== WebSocket.OPEN) return;
    this._playWs.send(JSON.stringify({
      event_type: 'PAUSE_TYPE',
      data: { selector: data.selector, text: payload.text },
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
    if (evt.event_type === 'PLAY_STEP_ERROR') {
      const data = evt.data as { stepId?: number; error?: string };
      const stepId = data.stepId ?? 0;
      const message = data.error ?? 'Step failed';
      this._showErrorPopupOnce(`play-step-error-${stepId}-${message}`, 'Playback Step Error', `Step ID ${stepId}: ${message}`);
    }

    if (evt.event_type === 'PLAY_PAUSED') {
      const data = evt.data as { stepId?: number; reason?: string; error?: string };
      if (data.reason === 'error' && data.error) {
        const stepId = data.stepId ?? 0;
        this._showErrorPopupOnce(`play-paused-error-${stepId}-${data.error}`, 'Playback Paused On Error', `Step ID ${stepId}: ${data.error}`);
      }
    }

    if (evt.event_type === 'PLAY_PATCH_STEPS_ACK') {
      const ack = evt.data as RuntimePatchAck;
      if (this._runtimePatchAckResolver) {
        this._runtimePatchAckResolver(ack);
      }
      return;
    }

    if (evt.event_type === 'PLAY_DONE') {
      const data = evt.data as { stepCount: number };
      this._resetRuntimeTrackingState();
      this._showRunPopup('success', 'Playback Successful', `${data.stepCount} steps executed successfully. Refreshing in 10 seconds.`, 10000);
      this._scheduleSuccessRefresh();
    }

    if (evt.event_type === 'PLAY_ERROR') {
      this._clearSuccessRefreshTimer();
      const data = evt.data as { error?: string };
      this._resetRuntimeTrackingState();
      this._showErrorPopupOnce(`play-error-${data.error ?? 'Playback failed.'}`, 'Playback Error', data.error ?? 'Playback failed.');
    }

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

  closeRunPopup(): void {
    this.runPopupVisible.set(false);
  }

  private _showRunPopup(variant: 'success' | 'error', title: string, message: string, autoCloseMs = 2000): void {
    this.runPopupVariant.set(variant);
    this.runPopupTitle.set(title);
    this.runPopupMessage.set(message);
    this.runPopupAutoCloseMs.set(autoCloseMs);
    this.runPopupVisible.set(true);
  }

  private _scheduleSuccessRefresh(): void {
    this._clearSuccessRefreshTimer();
    this._successRefreshTimer = setTimeout(() => {
      window.location.reload();
    }, 10000);
  }

  private _clearSuccessRefreshTimer(): void {
    if (this._successRefreshTimer) {
      clearTimeout(this._successRefreshTimer);
      this._successRefreshTimer = null;
    }
  }

  private _findValidationFailure(): string | null {
    return this._getFirstValidationFailure();
  }

  private _recomputeValidationErrors(): void {
    const result = this._collectValidationState();
    this.validationErrors.set(result.errors);
  }

  private _getFirstValidationFailure(): string | null {
    const result = this._collectValidationState();
    this.validationErrors.set(result.errors);
    return result.firstPopupError;
  }

  private _collectValidationState(): { errors: Map<number, string>; firstPopupError: string | null } {
    const current = this.detail();
    const errors = new Map<number, string>();
    let firstPopupError: string | null = null;
    if (!current) return { errors, firstPopupError };

    const edits = this.editValues();
    const shouldRunMap = this.shouldRunState();

    for (const groups of Object.values(current.steps)) {
      for (const group of groups as RecordingStep[][]) {
        for (const step of group) {
          if (step.type !== 'TYPE') continue;

          const shouldRun = shouldRunMap.has(step.id) ? shouldRunMap.get(step.id)! : (step.shouldRun ?? true);
          if (!shouldRun) continue;

          const rules = step.inputValidation;
          if (!rules) continue;

          const value = this._resolveEditableStepValue(step, edits);
          const error = this._validateValueAgainstRules(value, rules);
          if (error) {
            const label = step.label?.trim() || 'TYPE';
            const inlineError = `${label}: ${error}`;
            errors.set(step.id, inlineError);
            if (!firstPopupError) {
              firstPopupError = `Step ID ${step.id}: ${inlineError}`;
            }
          }
        }
      }
    }

    return { errors, firstPopupError };
  }

  private _resolveEditableStepValue(step: RecordingStep, edits: Map<number, string>): string {
    const raw = edits.has(step.id) ? (edits.get(step.id) ?? '') : (step.text ?? '');
    return /^\{\{.+\}\}$/.test(raw.trim()) ? '' : raw;
  }

  private _isValidDate(value: string): boolean {
    const trimmed = value.trim();
    if (!trimmed) return false;

    if (dayjs(trimmed, ACCEPTED_DATE_FORMATS, true).isValid()) {
      return true;
    }

    // Fallback for common browser-parseable formats (e.g. ISO datetime strings).
    return dayjs(trimmed).isValid();
  }

  private _validateValueAgainstRules(value: string, rules: InputValidation): string | null {
    const raw = value ?? '';

    if (rules.required && raw.trim().length === 0) {
      return 'Value is required.';
    }

    if (raw.length === 0) {
      return null;
    }

    if (typeof rules.minLength === 'number' && raw.length < rules.minLength) {
      return `Minimum length is ${rules.minLength}.`;
    }

    if (typeof rules.maxLength === 'number' && raw.length > rules.maxLength) {
      return `Maximum length is ${rules.maxLength}.`;
    }

    switch (rules.mode) {
      case 'alphabet':
        if (!/^[A-Za-z]+$/.test(raw)) return 'Only alphabetic characters are allowed.';
        break;
      case 'numeric': {
        const numberRegex = rules.allowNegativeNumber ? /^-?\d+(\.\d+)?$/ : /^\d+(\.\d+)?$/;
        if (!numberRegex.test(raw)) {
          return rules.allowNegativeNumber
            ? 'Enter a valid number.'
            : 'Only non-negative numbers are allowed.';
        }
        break;
      }
      case 'alphanumeric':
        if (!/^[A-Za-z0-9]+$/.test(raw)) return 'Only alphanumeric characters are allowed.';
        break;
      case 'date':
        if (!this._isValidDate(raw)) return 'Enter a valid date.';
        break;
      case 'email':
        if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(raw)) return 'Enter a valid email address.';
        break;
      case 'mobile':
        if (!/^\+?[0-9]{10,15}$/.test(raw)) return 'Enter a valid mobile number.';
        break;
      case 'strongPassword':
        if (!/^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z0-9]).{8,}$/.test(raw)) {
          return 'Password must be at least 8 characters and include upper, lower, number, and symbol.';
        }
        break;
      case 'custom':
        if (rules.customRegex) {
          try {
            const regex = new RegExp(rules.customRegex);
            if (!regex.test(raw)) return 'Value does not match custom regex.';
          } catch {
            return 'Custom regex is invalid.';
          }
        }
        break;
      default:
        break;
    }

    return null;
  }

  async saveEdits(): Promise<void> {
    const current = this.detail();
    const id = this.selectedId();
    if (!current || !id || !this.hasEdits()) return;

    const validationFailure = this._getFirstValidationFailure();
    if (validationFailure) {
      this._showRunPopup('error', 'Dynamic Input Validation Error', validationFailure, 0);
      return;
    }

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
      this._resetRuntimeState();
      this._recomputeValidationErrors();
      this.saveSuccess.set(true);
    } catch (e: any) {
      const message = e?.message ?? 'Save failed';
      this.saveError.set(message);
      this._showErrorPopupOnce(`save-error-${message}`, 'Save Error', message);
    } finally {
      this.saving.set(false);
    }
  }
}
