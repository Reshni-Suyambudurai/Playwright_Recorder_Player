import { Injectable, inject, signal, WritableSignal } from '@angular/core';
import { NavigationState } from '../types/websocket';
import { WebsocketApi } from './websocket.api';

@Injectable({
  providedIn: 'root',
})
export class NavigationApi {
  private websocketApi = inject(WebsocketApi);

  readonly navigationState: WritableSignal<NavigationState> = signal({
    isLoading: false,
    currentUrl: null,
    lastNavigation: null,
    error: null,
  });

  constructor() {
    this.setupEventListeners();
  }

  /**
   * Setup listeners for navigation events
   */
  private setupEventListeners(): void {
    this.websocketApi.navigationSuccess$.subscribe((data) => {
      this.updateNavigationState({
        isLoading: false,
        currentUrl: data.url,
        lastNavigation: {
          url: data.url,
          timestamp: new Date(),
          title: data.title,
          statusCode: data.status_code,
        },
        error: null,
      });
    });

    this.websocketApi.navigationError$.subscribe((data) => {
      this.updateNavigationState({
        isLoading: false,
        error: `${data.error}: ${data.message}`,
      });
    });

    this.websocketApi.disconnected$.subscribe(() => {
      this.navigationState.set({
        isLoading: false,
        currentUrl: null,
        lastNavigation: null,
        error: null,
      });
    });
  }

  /**
   * Navigate to a URL
   */
  public navigateToUrl(url: string): void {
    if (!this.isValidUrl(url)) {
      this.updateNavigationState({
        error: 'Invalid URL format',
      });
      return;
    }

    if (!this.websocketApi.isConnected()) {
      this.updateNavigationState({
        error: 'WebSocket not connected',
      });
      return;
    }

    this.updateNavigationState({
      isLoading: true,
      error: null,
    });

    this.websocketApi.navigate(url);
  }

  /**
   * Validate URL format
   */
  private isValidUrl(url: string): boolean {
    if (!url || url.trim().length === 0) {
      return false;
    }
    // Allow URLs with http/https protocol or plain domain/path
    try {
      new URL(url.startsWith('http') ? url : `http://${url}`);
      return true;
    } catch {
      return false;
    }
  }

  /**
   * Clear error message
   */
  public clearError(): void {
    this.updateNavigationState({
      error: null,
    });
  }

  /**
   * Update navigation state
   */
  private updateNavigationState(partial: Partial<NavigationState>): void {
    const current = this.navigationState();
    this.navigationState.set({
      ...current,
      ...partial,
    });
  }

  /**
   * Get current navigation state
   */
  public getNavigationState(): NavigationState {
    return this.navigationState();
  }
}
