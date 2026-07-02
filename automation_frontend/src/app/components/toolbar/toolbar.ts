import { Component, inject } from '@angular/core';
import { NgClass } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { WebsocketApi } from '../../services/websocket.api';
import { NavigationApi } from '../../services/navigation.api';
import { environment } from '../../../environments/environment';

@Component({
  selector: 'app-toolbar',
  standalone: true,
  imports: [NgClass, FormsModule],
  templateUrl: './toolbar.html',
  styleUrl: './toolbar.css',
})
export class Toolbar {
  private websocketApi = inject(WebsocketApi);
  private navigationApi = inject(NavigationApi);

  urlInput: string = '';
  readonly connectionState = this.websocketApi.connectionState;
  readonly navigationState = this.navigationApi.navigationState;

  async onConnect(): Promise<void> {
    try {
      const response = await fetch(`${environment.apiBaseUrl}/recording/start`, {
        method: 'POST',
      });
      const data = await response.json();
      const sessionId = data.session_id;

      sessionStorage.setItem('sessionId', sessionId);
      await this.websocketApi.connect(sessionId);
    } catch (error) {
      console.error('Failed to connect:', error);
    }
  }

  async onDisconnect(): Promise<void> {
    try {
      const sessionId = sessionStorage.getItem('sessionId');
      if (sessionId) {
        await fetch(`${environment.apiBaseUrl}/recording/stop`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_id: sessionId }),
        });
        sessionStorage.removeItem('sessionId');
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
   * Navigate to entered URL
   */
  onNavigate(): void {
    if (this.urlInput.trim()) {
      this.navigationApi.navigateToUrl(this.urlInput);
    }
  }
}
