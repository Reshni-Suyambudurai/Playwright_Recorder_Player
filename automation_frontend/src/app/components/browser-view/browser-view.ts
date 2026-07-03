import { Component, ElementRef, inject, OnDestroy, OnInit, signal, viewChild, WritableSignal } from '@angular/core';
import { Subscription } from 'rxjs';
import { WebsocketApi } from '../../services/websocket.api';

const VIEWPORT_WIDTH = 1280;
const VIEWPORT_HEIGHT = 720;

@Component({
  selector: 'app-browser-view',
  standalone: true,
  templateUrl: './browser-view.html',
  styleUrl: './browser-view.css',
})
export class BrowserView implements OnInit, OnDestroy {
  private wsApi = inject(WebsocketApi);
  private sub?: Subscription;

  readonly frameUrl: WritableSignal<string> = signal('');

  private imgRef = viewChild<ElementRef<HTMLImageElement>>('frameImg');

  ngOnInit(): void {
    this.sub = this.wsApi.frame$.subscribe(frame => {
      this.frameUrl.set(frame.image);
    });
  }

  ngOnDestroy(): void {
    this.sub?.unsubscribe();
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
}
