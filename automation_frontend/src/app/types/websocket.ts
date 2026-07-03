/* WebSocket Event Types */
export type EventType =
  | 'HELLO'
  | 'WELCOME'
  | 'PING'
  | 'PONG'
  | 'NAVIGATE'
  | 'NAVIGATION_SUCCESS'
  | 'NAVIGATION_ERROR'
  | 'START_RECORDING'
  | 'RECORDING_STARTED'
  | 'FRAME'
  | 'CLICK_ACTION'
  | 'ACTION_DONE'
  | 'ERROR';

/* WebSocket Event Structure */
export interface WebSocketEvent<T = any> {
  event_type: EventType;
  client_id?: string;   // present on all outgoing events; echoed back on some responses
  data: T;
}

/* Event Data Models */
export interface HelloData {
  client_id: string;
  timestamp: number;
}

export interface WelcomeData {
  session_id: string;
  client_id: string;
  timestamp: number;
}

export interface PingData {
  timestamp: number;
}

export interface PongData {
  timestamp: number;
}

export interface NavigateData {
  url: string;
}

export interface NavigationSuccessData {
  url: string;
  title?: string;
  status_code?: number;
}

export interface NavigationErrorData {
  url: string;
  error: string;
  message: string;
}

export interface ErrorData {
  message: string;
  code?: string;
}

/* Screenshot Streaming */
export interface StartRecordingData {
  url: string;
  recording_name: string;
}

export interface RecordingStartedData {
  recording_name: string;
  url: string;
  title?: string;
  timestamp: string;
}

export interface FrameData {
  image: string;    // data:image/jpeg;base64,...
  width: number;
  height: number;
  timestamp: string;
}

export interface ClickActionData {
  x: number;
  y: number;
  button?: 'left' | 'right' | 'middle';
}

export interface ActionDoneData {
  type: string;
  x: number;
  y: number;
  success: boolean;
}

/* Connection State */
export interface ConnectionState {
  isConnected: boolean;
  sessionId: string | null;
  clientId: string | null;
  lastUpdate: Date | null;
  error: string | null;
}

/* Navigation State */
export interface NavigationState {
  isLoading: boolean;
  currentUrl: string | null;
  lastNavigation: {
    url: string;
    timestamp: Date;
    title?: string;
    statusCode?: number;
  } | null;
  error: string | null;
}
