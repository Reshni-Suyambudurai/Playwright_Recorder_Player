import { Component, inject, OnDestroy, OnInit, output, signal } from '@angular/core';
import { NgClass } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { WebsocketApi } from '../../services/websocket.api';
import { NavigationApi } from '../../services/navigation.api';
import { TokenStore } from '../../services/token-store.api';
import { environment } from '../../../environments/environment';
import { Subscription } from 'rxjs';
import { Spinner } from '../spinner/spinner';
import { TooltipDirective } from '../../directives/tooltip/tooltip.directive';
import { SvgIcon } from '../svg-icon/svg-icon';

@Component({
  selector: 'app-toolbar',
  standalone: true,
  imports: [FormsModule, Spinner, TooltipDirective, SvgIcon],
  templateUrl: './toolbar.html',
  styleUrl: './toolbar.css',
})
export class Toolbar implements OnInit, OnDestroy {
  private websocketApi = inject(WebsocketApi);
  private navigationApi = inject(NavigationApi);
  private tokenStore = inject(TokenStore);
  private sub?: Subscription;

  urlInput: string = '';
  readonly connectionState = this.websocketApi.connectionState;
  readonly navigationState = this.navigationApi.navigationState;
  readonly isRecording = signal(false);
  readonly isConnecting = signal(false);

  /** Emits when the user wants to open the recording modal */
  readonly openRecordingModal = output<string>();

  ngOnInit(): void {
    this.sub = this.websocketApi.recordingStarted$.subscribe(() => this.isRecording.set(true));
    this.websocketApi.recordingStopped$.subscribe(() => this.isRecording.set(false));
    this.websocketApi.disconnected$.subscribe(() => {
      this.isRecording.set(false);
      this.urlInput = '';
    });
  }

  ngOnDestroy(): void {
    this.sub?.unsubscribe();
  }

  async onConnect(): Promise<void> {
    this.isConnecting.set(true);
    try {
      const response = await fetch(`${environment.apiBaseUrl}/recording/start`, {
        method: 'POST',
      });
      const data = await response.json();
      const sessionId = data.session_id;

      this.tokenStore.setSessionId(sessionId);

      // Connect to WebSocket
      await this.websocketApi.connect(sessionId);
    } catch (error) {
      console.error('Failed to connect:', error);
    } finally {
      this.isConnecting.set(false);
    }
  }

  async onDisconnect(): Promise<void> {
    try {
      const sessionId = this.tokenStore.getSessionId();
      if (sessionId) {
        await fetch(`${environment.apiBaseUrl}/recording/stop`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_id: sessionId }),
        });
        this.tokenStore.removeSessionId();
      }
      this.websocketApi.disconnect();
    } catch (error) {
      console.error('Failed to disconnect:', error);
    }
  }

  /**
   * Navigate to URL on Enter key
   */
  onKeyPress(event: KeyboardEvent): void {
    if (event.key === 'Enter') {
      this.onNavigate();
    }
  }

  /**
   * Trigger recording modal instead of navigating directly
   */
  onNavigate(): void {
    if (this.urlInput.trim()) {
      this.openRecordingModal.emit(this.urlInput.trim());
    }
  }

  onRefresh(): void {
    this.websocketApi.sendPageRefresh();
  }

  onBack(): void {
    this.websocketApi.sendPageBack();
  }

  onStopRecording(): void {
    this.websocketApi.sendStopRecording();
  }
}
