import { Component, inject } from '@angular/core';
import { NgClass } from '@angular/common';
import { WebsocketApi } from '../../services/websocket.api';
import { NavigationApi } from '../../services/navigation.api';

@Component({
  selector: 'app-status',
  standalone: true,
  imports: [NgClass],
  templateUrl: './status.html',
  styleUrl: './status.css',
})
export class Status {
  private websocketApi = inject(WebsocketApi);
  private navigationApi = inject(NavigationApi);

  readonly connectionState = this.websocketApi.connectionState;
  readonly navigationState = this.navigationApi.navigationState;

  /**
   * Format timestamp to readable string
   */
  formatTime(date: Date | null): string {
    if (!date) return '-';
    return new Date(date).toLocaleTimeString();
  }
}
