import { Injectable, signal, WritableSignal } from '@angular/core';
import {
  ActionDoneData,
  ClickActionData,
  ConnectionState,
  ErrorData,
  EventType,
  FrameData,
  HelloData,
  NavigateData,
  NavigationErrorData,
  NavigationSuccessData,
  PingData,
  PongData,
  RecordingStartedData,
  StartRecordingData,
  WebSocketEvent,
  WelcomeData,
} from '../types/websocket';
import { Observable, Subject } from 'rxjs';
import { environment } from '../../environments/environment';
import { TokenStore } from './token-store.api';

@Injectable({
  providedIn: 'root',
})
export class WebsocketApi {
  private tokenStore = new TokenStore();
  private ws: WebSocket | null = null;
  private clientId: string = this.tokenStore.resolveClientId();

  readonly connectionState: WritableSignal<ConnectionState> = signal({
    isConnected: false,
    sessionId: null,
    clientId: null,
    lastUpdate: null,
    error: null,
  });

  // Navigation observables
  private navigationSuccessSubject = new Subject<NavigationSuccessData>();
  private navigationErrorSubject = new Subject<NavigationErrorData>();
  private errorSubject = new Subject<string>();

  readonly navigationSuccess$: Observable<NavigationSuccessData> = this.navigationSuccessSubject.asObservable();
  readonly navigationError$: Observable<NavigationErrorData> = this.navigationErrorSubject.asObservable();
  readonly error$: Observable<string> = this.errorSubject.asObservable();

  // Screenshot streaming observables
  private frameSubject = new Subject<FrameData>();
  private recordingStartedSubject = new Subject<RecordingStartedData>();
  private actionDoneSubject = new Subject<ActionDoneData>();

  readonly frame$: Observable<FrameData> = this.frameSubject.asObservable();
  readonly recordingStarted$: Observable<RecordingStartedData> = this.recordingStartedSubject.asObservable();
  readonly actionDone$: Observable<ActionDoneData> = this.actionDoneSubject.asObservable();

  /**
   * Connect to WebSocket server
   */
  public async connect(sessionId: string, serverUrl: string = environment.wsBaseUrl): Promise<void> {
    return new Promise((resolve, reject) => {
      try {
        const wsUrl = `${serverUrl}/ws/${sessionId}`;
        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = () => {
          this.sendHello();
          resolve();
        };

        this.ws.onmessage = (event) => {
          this.handleMessage(event.data);
        };

        this.ws.onerror = (event) => {
          console.error('WebSocket error:', event);
          const errorMsg = 'WebSocket connection error';
          this.errorSubject.next(errorMsg);
          this.updateConnectionState({
            isConnected: false,
            error: errorMsg,
          });
          reject(new Error(errorMsg));
        };

        this.ws.onclose = () => {
          this.updateConnectionState({
            isConnected: false,
            error: 'Connection closed',
          });
        };
      } catch (error) {
        const errorMsg = error instanceof Error ? error.message : 'Connection failed';
        reject(new Error(errorMsg));
      }
    });
  }

  /**
   * Disconnect from WebSocket server
   */
  public disconnect(): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.close();
    }
    this.updateConnectionState({
      isConnected: false,
      sessionId: null,
      error: null,
    });
  }

  /**
   * Send NAVIGATE event
   */
  public navigate(url: string): void {
    const data: NavigateData = { url };
    this.send('NAVIGATE', data);
  }

  /**
   * Send PING event
   */
  public sendPing(): void {
    const data: PingData = { timestamp: Date.now() };
    this.send('PING', data);
  }

  /**
   * Generic send method — always includes client_id so backend can target responses.
   */
  private send(eventType: EventType, data: any): void {
    if (!this.isConnected()) {
      console.warn('WebSocket not connected');
      return;
    }

    const event: WebSocketEvent = {
      event_type: eventType,
      client_id: this.clientId,
      data,
    };

    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(event));
    }
  }

  /**
   * Send HELLO event (internal)
   */
  private sendHello(): void {
    const data: HelloData = {
      client_id: this.clientId,
      timestamp: Date.now(),
    };
    this.send('HELLO', data);
  }

  /**
   * Handle incoming WebSocket messages
   */
  private handleMessage(data: string): void {
    try {
      const event: WebSocketEvent = JSON.parse(data);

      switch (event.event_type) {
        case 'WELCOME':
          this.handleWelcome(event.data as WelcomeData);
          break;
        case 'PONG':
          this.handlePong(event.data as PongData);
          break;
        case 'NAVIGATION_SUCCESS':
          this.navigationSuccessSubject.next(event.data as NavigationSuccessData);
          this.updateConnectionState({ error: null });
          break;
        case 'NAVIGATION_ERROR':
          this.navigationErrorSubject.next(event.data as NavigationErrorData);
          this.updateConnectionState({ error: event.data.message });
          break;
        case 'FRAME':
          this.frameSubject.next(event.data as FrameData);
          break;
        case 'RECORDING_STARTED':
          this.recordingStartedSubject.next(event.data as RecordingStartedData);
          break;
        case 'ACTION_DONE':
          this.actionDoneSubject.next(event.data as ActionDoneData);
          break;
        case 'ERROR':
          this.handleError(event.data as ErrorData);
          break;
        default:
          console.log('Unknown event type:', event.event_type);
      }
    } catch (error) {
      console.error('Failed to parse WebSocket message:', error);
    }
  }

  /**
   * Handle WELCOME event
   */
  private handleWelcome(data: WelcomeData): void {
    this.updateConnectionState({
      isConnected: true,
      sessionId: data.session_id,
      clientId: data.client_id,
      lastUpdate: new Date(),
      error: null,
    });
  }

  /**
   * Handle PONG event
   */
  private handlePong(data: PongData): void {
    this.updateConnectionState({
      lastUpdate: new Date(),
    });
  }

  /**
   * Handle ERROR event
   */
  private handleError(data: ErrorData): void {
    this.errorSubject.next(data.message);
    this.updateConnectionState({
      error: data.message,
    });
  }

  /**
   * Update connection state
   */
  private updateConnectionState(partial: Partial<ConnectionState>): void {
    const current = this.connectionState();
    this.connectionState.set({ ...current, ...partial });
  }

  /**
   * Check if WebSocket is connected
   */
  public sendStartRecording(data: StartRecordingData): void {
    this.send('START_RECORDING', data);
  }

  public sendClickAction(x: number, y: number, button: 'left' | 'right' | 'middle' = 'left'): void {
    const data: ClickActionData = { x, y, button };
    this.send('CLICK_ACTION', data);
  }

  public isConnected(): boolean {
    return this.ws !== null && this.ws.readyState === WebSocket.OPEN;
  }

  public getConnectionState(): ConnectionState {
    return this.connectionState();
  }
}
