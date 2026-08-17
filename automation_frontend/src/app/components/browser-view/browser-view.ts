import { Component, ElementRef, effect, inject, OnDestroy, OnInit, signal, viewChild, WritableSignal } from '@angular/core';
import { Subscription } from 'rxjs';
import { WebsocketApi } from '../../services/websocket.api';
import { AssertionModeApi } from '../../services/assertion-mode.api';
import { InputDetectedData, TabInfo } from '../../types/websocket';
import { InputOverlay, InputOverlayConfirmPayload } from '../input-overlay/input-overlay';
import { AssertionOverlay } from '../assertion-overlay/assertion-overlay';
import { TabBar } from '../tab-bar/tab-bar';
import { Spinner } from '../spinner/spinner';

const VIEWPORT_WIDTH = 1280;
const VIEWPORT_HEIGHT = 720;

@Component({
  selector: 'app-browser-view',
  standalone: true,
  imports: [InputOverlay, AssertionOverlay, TabBar, Spinner],
  templateUrl: './browser-view.html',
  styleUrl: './browser-view.css',
})
export class BrowserView implements OnInit, OnDestroy {
  private wsApi = inject(WebsocketApi);
  private assertionModeApi = inject(AssertionModeApi);
  private subs: Subscription[] = [];

  readonly frameUrl: WritableSignal<string> = signal('');
  readonly overlayData: WritableSignal<InputDetectedData | null> = signal(null);
  readonly overlayX = signal(0);
  readonly overlayY = signal(0);
  readonly tabs = signal<TabInfo[]>([]);
  readonly isNavigating = signal(false);

  // Assertion overlay state
  readonly assertionMode = signal<'visibility' | 'text' | 'value' | null>(null);
  readonly assertionData = signal<any>(null);
  readonly assertionOverlayX = signal(0);
  readonly assertionOverlayY = signal(0);

  private imgRef = viewChild<ElementRef<HTMLImageElement>>('frameImg');

  // Scroll debounce state
  private _scrollTimer: ReturnType<typeof setTimeout> | null = null;
  private _accDeltaX = 0;
  private _accDeltaY = 0;
  private _scrollX = 0;
  private _scrollY = 0;
  private readonly SCROLL_DEBOUNCE_MS = 150;

  // Hover throttle state
  private _lastHoverTime = 0;
  private readonly HOVER_THROTTLE_MS = 300;

  constructor() {
    // Monitor assertion mode changes and clear overlay when deactivated
    effect(() => {
      const mode = this.assertionModeApi.activeMode();
      if (!mode) {
        // When assertion mode is deactivated, clear the overlay
        this.assertionData.set(null);
        this.assertionMode.set(null);
      }
    });
  }

  ngOnInit(): void {
    this.subs.push(
      this.wsApi.frame$.subscribe(frame => {
        this.isNavigating.set(false);
        this.frameUrl.set(frame.image);
      }),
      this.wsApi.navigating$.subscribe(() => this.isNavigating.set(true)),
      this.wsApi.inputDetected$.subscribe(data => this._showOverlay(data)),
      this.wsApi.assertionDiscovered$.subscribe(event => {
        // event structure: {mode, assertionData: {...fields...}, coords, pageUrl}
        this.assertionMode.set(event.mode || null);
        this.assertionData.set(event.assertionData || null);
        if (event.coords) {
          this.assertionOverlayX.set(Math.round(event.coords.x + 10));
          this.assertionOverlayY.set(Math.round(event.coords.y + 10));
        }
      }),
      this.wsApi.tabOpened$.subscribe(data => this.tabs.set(data.tabs ?? [])),
      this.wsApi.tabSwitched$.subscribe(data => {
        const updated = this.tabs().map(t => ({ ...t, active: t.tab_id === data.tab_id }));
        this.tabs.set(updated);
      }),
      this.wsApi.recordingStopped$.subscribe(() => {
        this.tabs.set([]);
        this.assertionMode.set(null);
        this.assertionData.set(null);
      }),
      this.wsApi.disconnected$.subscribe(() => {
        this.frameUrl.set('');
        this.overlayData.set(null);
        this.tabs.set([]);
        this.isNavigating.set(false);
        this.assertionMode.set(null);
        this.assertionData.set(null);
        if (this._scrollTimer !== null) { clearTimeout(this._scrollTimer); this._scrollTimer = null; }
        this._accDeltaX = 0; this._accDeltaY = 0;
      }),
    );
  }

  ngOnDestroy(): void {
    this.subs.forEach(s => s.unsubscribe());
    if (this._scrollTimer !== null) clearTimeout(this._scrollTimer);
  }

  private _showOverlay(data: InputDetectedData): void {
    const img = this.imgRef()?.nativeElement;
    if (!img) { this.overlayData.set(data); return; }
    const rect = img.getBoundingClientRect();
    const scaleX = rect.width / VIEWPORT_WIDTH;
    const scaleY = rect.height / VIEWPORT_HEIGHT;
    // Position relative to the container (container is position:relative)
    const containerRect = (img.parentElement as HTMLElement).getBoundingClientRect();
    this.overlayX.set(Math.round(data.x * scaleX + (rect.left - containerRect.left)));
    this.overlayY.set(Math.round(data.y * scaleY + (rect.top - containerRect.top)));
    this.overlayData.set(data);
  }

  onImageClick(event: MouseEvent): void {
    const img = this.imgRef()?.nativeElement;
    if (!img) return;
    const rect = img.getBoundingClientRect();
    const scaleX = VIEWPORT_WIDTH / rect.width;
    const scaleY = VIEWPORT_HEIGHT / rect.height;
    const x = Math.round((event.clientX - rect.left) * scaleX);
    const y = Math.round((event.clientY - rect.top) * scaleY);
    this.wsApi.sendClickAction(x, y);
  }

  onImageHover(event: MouseEvent): void {
    // Only emit if assertion mode is active
    if (!this.assertionModeApi.activeMode()) return;

    // Throttle hover events (300ms for smooth updates without flickering)
    const now = Date.now();
    if (now - this._lastHoverTime < this.HOVER_THROTTLE_MS) return;
    this._lastHoverTime = now;

    const img = this.imgRef()?.nativeElement;
    if (!img) return;
    const rect = img.getBoundingClientRect();
    const scaleX = VIEWPORT_WIDTH / rect.width;
    const scaleY = VIEWPORT_HEIGHT / rect.height;
    const x = Math.round((event.clientX - rect.left) * scaleX);
    const y = Math.round((event.clientY - rect.top) * scaleY);

    // Tooltip dimensions
    const tooltipWidth = 500;
    const tooltipHeight = 300;
    const padding = 2;

    // Position at cursor, but keep within bounds
    let overlayX = Math.round(event.clientX - rect.left);
    let overlayY = Math.round(event.clientY - rect.top);

    // Constrain to left boundary
    overlayX = Math.max(padding, overlayX);

    // Constrain to right boundary (ensure tooltip doesn't extend beyond screenshot width)
    if (overlayX + tooltipWidth > rect.width) {
      overlayX = rect.width - tooltipWidth - padding;
    }

    // Constrain to top boundary
    overlayY = Math.max(padding, overlayY);

    // Constrain to bottom boundary (ensure tooltip doesn't extend beyond screenshot height)
    if (overlayY + tooltipHeight > rect.height) {
      overlayY = rect.height - tooltipHeight - padding;
    }

    this.assertionOverlayX.set(overlayX);
    this.assertionOverlayY.set(overlayY);

    this.wsApi.sendAssertionHover(x, y);
  }

  onImageWheel(event: WheelEvent): void {
    event.preventDefault();
    const img = this.imgRef()?.nativeElement;
    if (!img) return;
    const rect = img.getBoundingClientRect();
    const scaleX = VIEWPORT_WIDTH / rect.width;
    const scaleY = VIEWPORT_HEIGHT / rect.height;
    const x = Math.round((event.clientX - rect.left) * scaleX);
    const y = Math.round((event.clientY - rect.top) * scaleY);

    // Accumulate deltas; capture origin coords on first tick of this gesture
    if (this._scrollTimer === null) {
      this._scrollX = x;
      this._scrollY = y;
    }
    this._accDeltaX += event.deltaX;
    this._accDeltaY += event.deltaY;

    // Reset debounce window
    if (this._scrollTimer !== null) clearTimeout(this._scrollTimer);
    this._scrollTimer = setTimeout(() => {
      this._scrollTimer = null;
      this.wsApi.sendScrollAction(this._scrollX, this._scrollY, this._accDeltaX, this._accDeltaY);
      this._accDeltaX = 0;
      this._accDeltaY = 0;
    }, this.SCROLL_DEBOUNCE_MS);
  }

  onOverlayConfirm(payload: InputOverlayConfirmPayload): void {
    const data = this.overlayData();
    if (!data) return;
    this.overlayData.set(null);
    this.wsApi.sendTypeAction(
      payload.text,
      data.x,
      data.y,
      data.selector,
      data.is_password,
      data.label,
      data.tag,
      payload.inputValidation,
    );
  }

  onOverlayCancel(): void {
    this.overlayData.set(null);
  }
}
