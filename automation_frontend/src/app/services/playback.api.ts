import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';

export interface FailedStep {
  stepId: number;
  index: number;
  type: string;
  error: string;
}

export type PlayEvent =
  | { event_type: 'WELCOME';           data: { play_session_id: string; message: string } }
  | { event_type: 'PLAY_STEP_START';   data: { stepId: number; index: number; total: number; type: string } }
  | { event_type: 'PLAY_STEP_SKIPPED'; data: { stepId: number; index: number; total: number } }
  | { event_type: 'PLAY_STEP_ERROR';   data: { stepId: number; index: number; type: string; error: string } }
  | { event_type: 'PLAY_PAUSED';       data: { stepId: number; index: number } }
  | { event_type: 'PLAY_DONE';         data: { stepCount: number; failedCount: number; failedSteps: FailedStep[]; message: string } }
  | { event_type: 'PLAY_ERROR';        data: { error: string } }
  | { event_type: 'PLAY_STOPPED';      data: Record<string, never> }
  | { event_type: 'FRAME';             data: { image: string } }
  | { event_type: 'PONG';              data: unknown }
  | { event_type: string;              data: unknown };

export interface PlayHandlers {
  onEvent: (evt: PlayEvent) => void;
  onClose?: () => void;
  onError?: (err: Event) => void;
}

const API_BASE = 'http://localhost:8001';
const WS_BASE  = 'ws://localhost:8001';

@Injectable({ providedIn: 'root' })
export class PlaybackApi {
  private _ws: WebSocket | null = null;

  constructor(private http: HttpClient) {}

  /** POST /play/start — returns the play_session_id */
  async startPlay(recordingJson: object): Promise<{ play_session_id: string }> {
    return firstValueFrom(
      this.http.post<{ play_session_id: string }>(`${API_BASE}/play/start`, recordingJson)
    );
  }

  /**
   * Open a WebSocket to /ws/play/{playId}, send HELLO, and wire up handlers.
   * Returns the raw WebSocket so the caller can send PLAY_RESUME / PLAY_STOP.
   */
  connectWs(playId: string, clientId: string, handlers: PlayHandlers): WebSocket {
    this.disconnect();

    const ws = new WebSocket(`${WS_BASE}/ws/play/${playId}`);
    this._ws = ws;

    ws.onopen = () => {
      ws.send(JSON.stringify({ event_type: 'HELLO', data: { client_id: clientId } }));
    };

    ws.onmessage = (ev) => {
      try {
        const evt = JSON.parse(ev.data) as PlayEvent;
        handlers.onEvent(evt);
      } catch {
        /* ignore unparseable frames */
      }
    };

    ws.onclose  = () => handlers.onClose?.();
    ws.onerror  = (e) => handlers.onError?.(e);

    return ws;
  }

  /** Disconnect any open playback WebSocket. */
  disconnect(): void {
    if (this._ws && this._ws.readyState < WebSocket.CLOSING) {
      this._ws.close();
    }
    this._ws = null;
  }
}
