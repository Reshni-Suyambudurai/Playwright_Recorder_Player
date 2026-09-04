import { Component, ElementRef, effect, inject, OnDestroy, OnInit, signal, viewChild, WritableSignal } from '@angular/core';
import { Subscription } from 'rxjs';
import { WebsocketApi } from '../../services/websocket.api';
import { AssertionModeApi } from '../../services/assertion-mode.api';
import { InputDetectedData, TabInfo } from '../../types/websocket';
import { InputOverlay, InputOverlayConfirmPayload } from '../input-overlay/input-overlay';
import { TabBar } from '../tab-bar/tab-bar';
import { Spinner } from '../spinner/spinner';
import { SnapshotConfirmDialog } from '../snapshot-confirm-dialog/snapshot-confirm-dialog';

const VIEWPORT_WIDTH = 1280;
const VIEWPORT_HEIGHT = 720;

@Component({
  selector: 'app-browser-view',
  standalone: true,
  imports: [InputOverlay, TabBar, Spinner, SnapshotConfirmDialog],
  templateUrl: './browser-view.html',
  styleUrl: './browser-view.css',
})

export class BrowserView implements OnInit, OnDestroy {
  private wsApi = inject(WebsocketApi);
  readonly assertionModeApi = inject(AssertionModeApi);
  private subs: Subscription[] = [];

  readonly frameUrl: WritableSignal<string> = signal('');
  readonly overlayData: WritableSignal<InputDetectedData | null> = signal(null);
  // Exact click point — used only for the yellow marker dot
  readonly overlayX = signal(0);
  readonly overlayY = signal(0);
  // Popup position — starts at the click point, then clamped to stay fully on screen
  readonly overlayPopupX = signal(0);
  readonly overlayPopupY = signal(0);
  readonly tabs = signal<TabInfo[]>([]);
  readonly isNavigating = signal(false);

  // Assertion state (detected from backend, stored in AssertionModeApi)

  // Cursor-tracking yellow dot shown while any assertion mode is active (hidden once locked)
  readonly assertionCursorX = signal(0);
  readonly assertionCursorY = signal(0);
  readonly assertionCursorVisible = signal(false);

  // Static yellow dot pinned at the last-clicked point once an assertion is locked
  readonly assertionClickX = signal(0);
  readonly assertionClickY = signal(0);

  // Snapshot confirmation dialog state
  readonly snapshotConfirmDialogOpen = signal(false);

  private imgRef = viewChild<ElementRef<HTMLImageElement>>('frameImg');
  // These template refs point at component tags, so `read: ElementRef` is required —
  // otherwise viewChild resolves to the component instance and .nativeElement is undefined.
  private inputOverlayRef = viewChild('inputOverlayEl', { read: ElementRef<HTMLElement> });

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
        // When assertion mode is deactivated, close dialog and clear state
        this.snapshotConfirmDialogOpen.set(false);
        this.assertionModeApi.clearDetectedAssertion();
        this.assertionCursorVisible.set(false);
      } else if (mode === 'snapshot') {
        // When snapshot mode is activated, immediately show confirmation dialog
        this.snapshotConfirmDialogOpen.set(true);
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
        // Store in AssertionModeApi for status sidebar to display and for Save to persist
        this.assertionModeApi.setDetectedAssertion(
          event.mode || null,
          event.assertionData || null,
          event.coords || null,
          event.pageUrl || null,
        );
      }),
      this.wsApi.snapshotPreview$.subscribe(event => {
        // event structure: {label, ariaSnapshot, elementCount, region, pageUrl}
        // Store in AssertionModeApi for status sidebar to display and for Save to persist
        this.assertionModeApi.setDetectedAssertion(
          'snapshot',
          {
            label: event.label,
            ariaSnapshot: event.ariaSnapshot,
            elementCount: event.elementCount,
            region: event.region,
          },
          null,
          event.pageUrl || null,
        );
      }),
      this.wsApi.tabOpened$.subscribe(data => this.tabs.set(data.tabs ?? [])),
      this.wsApi.tabSwitched$.subscribe(data => {
        const updated = this.tabs().map(t => ({ ...t, active: t.tab_id === data.tab_id }));
        this.tabs.set(updated);
      }),
      this.wsApi.recordingStopped$.subscribe(() => {
        this.tabs.set([]);
        this.assertionModeApi.clearDetectedAssertion();
      }),
      this.wsApi.disconnected$.subscribe(() => {
        this.frameUrl.set('');
        this.overlayData.set(null);
        this.tabs.set([]);
        this.isNavigating.set(false);
        this.assertionModeApi.clearDetectedAssertion();
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
    const x = Math.round(data.x * scaleX + (rect.left - containerRect.left));
    const y = Math.round(data.y * scaleY + (rect.top - containerRect.top));
    // Marker sits at the exact click point
    this.overlayX.set(x);
    this.overlayY.set(y);
    // Popup starts at the click point too; it gets clamped on-screen after it renders
    this.overlayPopupX.set(x);
    this.overlayPopupY.set(y);
    this.overlayData.set(data);
    // Wait a frame so the popup has its real dimensions, then clamp it into view
    requestAnimationFrame(() => this._repositionInputOverlay());
  }

  private _repositionInputOverlay(): void {
    const popup = this.inputOverlayRef()?.nativeElement;
    const img = this.imgRef()?.nativeElement;
    if (!popup || !img) return;

    const containerRect = (img.parentElement as HTMLElement).getBoundingClientRect();
    const popupWidth = popup.offsetWidth;
    const popupHeight = popup.offsetHeight;
    const padding = 4;

    let x = this.overlayX();
    let y = this.overlayY();

    // Pull the popup back inside the right/bottom edges of the screenshot
    if (x + popupWidth > containerRect.width - padding) {
      x = Math.max(padding, containerRect.width - popupWidth - padding);
    }
    if (y + popupHeight > containerRect.height - padding) {
      y = Math.max(padding, containerRect.height - popupHeight - padding);
    }

    this.overlayPopupX.set(x);
    this.overlayPopupY.set(y);
  }

  onImageClick(event: MouseEvent): void {
    const mode = this.assertionModeApi.activeMode();

    // Ignore all clicks when in assertion mode (snapshot shows dialog on activation, others lock on click)
    if (mode) {
      // For non-snapshot modes: Pin the assertion at this exact point
      if (mode !== 'snapshot') {
        const img = this.imgRef()?.nativeElement;
        if (!img) return;
        const rect = img.getBoundingClientRect();
        const scaleX = VIEWPORT_WIDTH / rect.width;
        const scaleY = VIEWPORT_HEIGHT / rect.height;
        const x = Math.round((event.clientX - rect.left) * scaleX);
        const y = Math.round((event.clientY - rect.top) * scaleY);

        this.assertionClickX.set(Math.round(event.clientX - rect.left));
        this.assertionClickY.set(Math.round(event.clientY - rect.top));
        this.assertionCursorVisible.set(false);
        this.assertionModeApi.lock();
        this.wsApi.sendAssertionHover(x, y);
      }
      return;
    }

    // Normal click action when no assertion mode is active
    const img = this.imgRef()?.nativeElement;
    if (!img) return;
    const rect = img.getBoundingClientRect();
    const scaleX = VIEWPORT_WIDTH / rect.width;
    const scaleY = VIEWPORT_HEIGHT / rect.height;
    const x = Math.round((event.clientX - rect.left) * scaleX);
    const y = Math.round((event.clientY - rect.top) * scaleY);

    this.wsApi.sendClickAction(x, y);
  }

  onSnapshotConfirmDialogConfirm(): void {
    // Capture full-page snapshot (zero coordinates = full page)
    this.wsApi.sendSnapshotCaptureRequest({
      x: 0,
      y: 0,
      width: 0,
      height: 0,
    });
    this.snapshotConfirmDialogOpen.set(false);
  }

  onSnapshotConfirmDialogCancel(): void {
    // Close dialog and deactivate snapshot mode
    this.snapshotConfirmDialogOpen.set(false);
    this.assertionModeApi.setMode(null);
  }

  onImageHover(event: MouseEvent): void {
    const mode = this.assertionModeApi.activeMode();
    const img = this.imgRef()?.nativeElement;
    if (!img) return;
    const rect = img.getBoundingClientRect();

    // Once an assertion is locked (user clicked an element), freeze the display —
    // ignore further mouse movement until it's Saved or Dismissed from the sidebar.
    if (this.assertionModeApi.locked()) return;

    // Track the yellow cursor dot for any active assertion mode (visibility/text/value/snapshot)
    if (mode) {
      this.assertionCursorX.set(Math.round(event.clientX - rect.left));
      this.assertionCursorY.set(Math.round(event.clientY - rect.top));
      this.assertionCursorVisible.set(true);
    } else {
      this.assertionCursorVisible.set(false);
    }

    // Hover-based discovery only applies to non-snapshot modes (snapshot uses drag-select instead)
    if (!mode || mode === 'snapshot') return;

    // Throttle hover events (300ms for smooth updates without flickering)
    const now = Date.now();
    if (now - this._lastHoverTime < this.HOVER_THROTTLE_MS) return;
    this._lastHoverTime = now;

    const scaleX = VIEWPORT_WIDTH / rect.width;
    const scaleY = VIEWPORT_HEIGHT / rect.height;
    const x = Math.round((event.clientX - rect.left) * scaleX);
    const y = Math.round((event.clientY - rect.top) * scaleY);

    this.wsApi.sendAssertionHover(x, y);
  }



  onImageWheel(event: WheelEvent): void {
    event.preventDefault();
    // While any assertion mode is active, don't record scroll actions
    if (this.assertionModeApi.activeMode()) return;
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
