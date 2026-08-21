import { Injectable, inject, signal, WritableSignal } from '@angular/core';
import {
  ActionDoneData,
  ClickActionData,
  ConnectionState,
  ErrorData,
  EventType,
  FrameData,
  HelloData,
  InputDetectedData,
  InputValidation,
  KeyActionData,
  NavigateData,
  NavigationErrorData,
  NavigationSuccessData,
  PingData,
  PongData,
  RecordingStartedData,
  RecordingStoppedData,
  ScrollActionData,
  SelectorInfo,
  StartRecordingData,
  TabOpenedData,
  TabSwitchedData,
  SwitchTabData,
  TypeActionData,
  WebSocketEvent,
  WelcomeData,
} from '../types/websocket';
import { Observable, Subject } from 'rxjs';
import { environment } from '../../environments/environment';
import { TokenStore } from './token-store.api';
import { ValidationStateApi } from './validation-state.api';

@Injectable({
  providedIn: 'root',
})
export class WebsocketApi {
  private tokenStore = new TokenStore();
  private validationState = inject(ValidationStateApi);
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
  private navigatingSubject = new Subject<void>();
  private disconnectedSubject = new Subject<void>();

  readonly navigating$: Observable<void> = this.navigatingSubject.asObservable();
  readonly disconnected$: Observable<void> = this.disconnectedSubject.asObservable();
  private actionDoneSubject = new Subject<ActionDoneData>();

  readonly frame$: Observable<FrameData> = this.frameSubject.asObservable();
  readonly recordingStarted$: Observable<RecordingStartedData> = this.recordingStartedSubject.asObservable();
  readonly actionDone$: Observable<ActionDoneData> = this.actionDoneSubject.asObservable();

  // Input overlay + recording lifecycle
  private inputDetectedSubject = new Subject<InputDetectedData>();
  private recordingStoppedSubject = new Subject<RecordingStoppedData>();
  private tabOpenedSubject = new Subject<TabOpenedData>();
  private tabSwitchedSubject = new Subject<TabSwitchedData>();
  private assertionDiscoveredSubject = new Subject<any>();
  private snapshotPreviewSubject = new Subject<any>();

  readonly inputDetected$: Observable<InputDetectedData> = this.inputDetectedSubject.asObservable();
  readonly recordingStopped$: Observable<RecordingStoppedData> = this.recordingStoppedSubject.asObservable();
  readonly tabOpened$: Observable<TabOpenedData> = this.tabOpenedSubject.asObservable();
  readonly tabSwitched$: Observable<TabSwitchedData> = this.tabSwitchedSubject.asObservable();
  readonly assertionDiscovered$: Observable<any> = this.assertionDiscoveredSubject.asObservable();
  readonly snapshotPreview$: Observable<any> = this.snapshotPreviewSubject.asObservable();

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
    this.validationState.clear();
    this.updateConnectionState({
      isConnected: false,
      sessionId: null,
      error: null,
      sessionClosed: false,
    });
    this.disconnectedSubject.next();
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
          this.handleActionDone(event.data as ActionDoneData);
          break;
        case 'INPUT_DETECTED':
          this.handleInputDetected(event.data as InputDetectedData);
          break;
        case 'VALIDATION_DISCOVERED':
          this.handleValidationDiscovered(event.data);
          break;
        case 'ASSERTION_DISCOVERED':
          this.assertionDiscoveredSubject.next(event.data);
          break;
        case 'SNAPSHOT_PREVIEW':
          this.snapshotPreviewSubject.next(event.data);
          break;
        case 'RECORDING_STOPPED':
          this.validationState.clear();
          this.recordingStoppedSubject.next(event.data as RecordingStoppedData);
          break;
        case 'TAB_OPENED':
          this.tabOpenedSubject.next(event.data as TabOpenedData);
          break;
        case 'TAB_SWITCHED':
          this.tabSwitchedSubject.next(event.data as TabSwitchedData);
          break;
        case 'SESSION_CLOSED':
          this.validationState.clear();
          this.updateConnectionState({ isConnected: false, sessionId: null, error: null, sessionClosed: true });
          this.disconnectedSubject.next();
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
    this.navigatingSubject.next();
    this.send('START_RECORDING', data);
  }

  public sendClickAction(x: number, y: number, button: 'left' | 'right' | 'middle' = 'left'): void {
    const data: ClickActionData = { x, y, button };
    this.navigatingSubject.next();
    this.send('CLICK_ACTION', data);
  }

  public sendTypeAction(
    text: string,
    x: number,
    y: number,
    selector: SelectorInfo | null,
    isPassword: boolean,
    label?: string | null,
    tag?: string,
    inputValidation?: InputValidation | null,
  ): void {
    const data: TypeActionData = { text, x, y, selector, is_password: isPassword, label, tag, inputValidation };
    this.navigatingSubject.next();
    this.send('TYPE_ACTION', data);
  }

  public sendScrollAction(x: number, y: number, deltaX: number, deltaY: number): void {
    const data: ScrollActionData = { x, y, delta_x: deltaX, delta_y: deltaY };
    this.navigatingSubject.next();
    this.send('SCROLL_ACTION', data);
  }

  public sendKeyAction(key: KeyActionData['key']): void {
    this.navigatingSubject.next();
    this.send('KEY_ACTION', { key });
  }

  public sendPageRefresh(): void {
    this.navigatingSubject.next();
    this.send('PAGE_REFRESH', {});
  }

  public sendPageBack(): void {
    this.navigatingSubject.next();
    this.send('PAGE_BACK', {});
  }

  public sendStopRecording(): void {
    this.send('STOP_RECORDING', {});
  }

  private handleActionDone(data: ActionDoneData): void {
    if (data.validation) {
      this.validationState.upsertContext(data.validation);
    }
    this.actionDoneSubject.next(data);
  }

  private handleInputDetected(data: InputDetectedData): void {
    if (data.validation) {
      this.validationState.upsertContext(data.validation);
    }
    this.inputDetectedSubject.next(data);
  }

  private handleValidationDiscovered(data: any): void {
    this.validationState.upsertContext(data);
  }

  public sendSwitchTab(tabId: string): void {
    this.send('SWITCH_TAB', { tab_id: tabId } satisfies SwitchTabData);
  }

  public sendAssertionModeToggled(mode: 'visibility' | 'text' | 'value' | 'snapshot' | null): void {
    this.send('ASSERTION_MODE_TOGGLED', { mode });
  }

  public sendAssertionHover(x: number, y: number): void {
    this.send('ASSERTION_HOVER', { x, y });
  }

  public sendSnapshotCaptureRequest(coords: { x: number; y: number; width: number; height: number }): void {
    this.send('SNAPSHOT_CAPTURE_REQUEST', coords);
  }

  public sendSnapshotSaveAssertion(data: any): void {
    this.send('SNAPSHOT_SAVE_ASSERTION', data);
  }

  public sendAssertionSave(
    mode: 'visibility' | 'text' | 'value',
    data: any,
    coords: { x: number; y: number } | null = null,
    pageUrl: string | null = null,
  ): void {
    // Send assertion step recorded event
    this.send('ASSERTION_STEP_RECORDED', { mode, data, coords, pageUrl });
  }

  public isConnected(): boolean {
    return this.ws !== null && this.ws.readyState === WebSocket.OPEN;
  }

  public getConnectionState(): ConnectionState {
    return this.connectionState();
  }
}
