import { Component, ElementRef, inject, OnDestroy, OnInit, signal, viewChild, WritableSignal } from '@angular/core';
import { Subscription } from 'rxjs';
import { WebsocketApi } from '../../services/websocket.api';
import { InputDetectedData, TabInfo } from '../../types/websocket';
import { InputOverlay } from '../input-overlay/input-overlay';
import { TabBar } from '../tab-bar/tab-bar';

const VIEWPORT_WIDTH = 1280;
const VIEWPORT_HEIGHT = 720;

@Component({
  selector: 'app-browser-view',
  standalone: true,
  imports: [InputOverlay, TabBar],
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

  private imgRef = viewChild<ElementRef<HTMLImageElement>>('frameImg');

  ngOnInit(): void {
    this.subs.push(
      this.wsApi.frame$.subscribe(frame => this.frameUrl.set(frame.image)),
      this.wsApi.inputDetected$.subscribe(data => this._showOverlay(data)),
      this.wsApi.tabOpened$.subscribe(data => this.tabs.set(data.tabs ?? [])),
      this.wsApi.tabSwitched$.subscribe(data => {
        const updated = this.tabs().map(t => ({ ...t, active: t.tab_id === data.tab_id }));
        this.tabs.set(updated);
      }),
      this.wsApi.recordingStopped$.subscribe(() => this.tabs.set([])),
    );
  }

  ngOnDestroy(): void {
    this.subs.forEach(s => s.unsubscribe());
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
    this.wsApi.sendScrollAction(x, y, event.deltaX, event.deltaY);
  }

  onOverlayConfirm(text: string): void {
    const data = this.overlayData();
    if (!data) return;
    this.overlayData.set(null);
    this.wsApi.sendTypeAction(text, data.x, data.y, data.selector, data.is_password, data.label, data.tag);
  }

  onOverlayCancel(): void {
    this.overlayData.set(null);
  }
}
