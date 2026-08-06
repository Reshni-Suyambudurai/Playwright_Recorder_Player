import { Component, ElementRef, inject, OnDestroy, OnInit, signal, viewChild, WritableSignal } from '@angular/core';
import { Subscription } from 'rxjs';
import { WebsocketApi } from '../../services/websocket.api';
import { InputDetectedData, TabInfo } from '../../types/websocket';
import { InputOverlay, InputOverlayConfirmPayload } from '../input-overlay/input-overlay';
import { TabBar } from '../tab-bar/tab-bar';
import { Spinner } from '../spinner/spinner';

const VIEWPORT_WIDTH = 1280;
const VIEWPORT_HEIGHT = 720;

@Component({
  selector: 'app-browser-view',
  standalone: true,
  imports: [InputOverlay, TabBar, Spinner],
  templateUrl: './browser-view.html',
  styleUrl: './browser-view.css',
})
export class BrowserView implements OnInit, OnDestroy {
  private wsApi = inject(WebsocketApi);
  private subs: Subscription[] = [];

  readonly frameUrl: WritableSignal<string> = signal('');
  readonly overlayData: WritableSignal<InputDetectedData | null> = signal(null);
  readonly overlayX = signal(0);
  readonly overlayY = signal(0);
  readonly tabs = signal<TabInfo[]>([]);
  readonly isNavigating = signal(false);

  private imgRef = viewChild<ElementRef<HTMLImageElement>>('frameImg');

  // Scroll debounce state
  private _scrollTimer: ReturnType<typeof setTimeout> | null = null;
  private _accDeltaX = 0;
  private _accDeltaY = 0;
  private _scrollX = 0;
  private _scrollY = 0;
  private readonly SCROLL_DEBOUNCE_MS = 150;

  ngOnInit(): void {
    this.subs.push(
      this.wsApi.frame$.subscribe(frame => {
        this.isNavigating.set(false);
        this.frameUrl.set(frame.image);
      }),
      this.wsApi.navigating$.subscribe(() => this.isNavigating.set(true)),
      this.wsApi.inputDetected$.subscribe(data => this._showOverlay(data)),
      this.wsApi.tabOpened$.subscribe(data => this.tabs.set(data.tabs ?? [])),
      this.wsApi.tabSwitched$.subscribe(data => {
        const updated = this.tabs().map(t => ({ ...t, active: t.tab_id === data.tab_id }));
        this.tabs.set(updated);
      }),
      this.wsApi.recordingStopped$.subscribe(() => this.tabs.set([])),
      this.wsApi.disconnected$.subscribe(() => {
        this.frameUrl.set('');
        this.overlayData.set(null);
        this.tabs.set([]);
        this.isNavigating.set(false);
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
