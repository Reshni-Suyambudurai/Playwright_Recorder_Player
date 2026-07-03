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
  | 'INPUT_DETECTED'
  | 'TYPE_ACTION'
  | 'SCROLL_ACTION'
  | 'KEY_ACTION'
  | 'STOP_RECORDING'
  | 'RECORDING_STOPPED'
  | 'TAB_OPENED'
  | 'SWITCH_TAB'
  | 'TAB_SWITCHED'
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
  description?: string;
  intent?: string;
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
  x?: number;
  y?: number;
  success: boolean;
}

/* Selector info from backend */
export interface SelectorInfo {
  strategy: 'id' | 'css' | 'xpath';
  value: string;
  frameSelector?: string | null;
}

/* Input overlay */
export interface InputDetectedData {
  x: number;
  y: number;
  tag: string;
  input_type: string | null;
  label: string | null;
  placeholder: string | null;
  current_value: string;
  is_password: boolean;
  selector: SelectorInfo | null;
}

export interface TypeActionData {
  text: string;
  x: number;
  y: number;
  selector: SelectorInfo | null;
  is_password: boolean;
  label?: string | null;
  tag?: string;
}

/* Scroll */
export interface ScrollActionData {
  x: number;
  y: number;
  delta_x: number;
  delta_y: number;
}

/* Key */
export interface KeyActionData {
  key: 'Enter' | 'Tab' | 'Escape' | 'Backspace' | 'ArrowUp' | 'ArrowDown';
}

/* Recording lifecycle */
export interface RecordingStepSummary {
  id: number;
  type: string;
  label: string | null;
  pageUrl: string | null;
  tag: string | null;
  timestamp: number;
}

export interface RecordingStoppedData {
  recording_id: string;
  recording_name: string;
  step_count: number;
  steps: RecordingStepSummary[];
}

/* Tab Management */
export interface TabInfo {
  tab_id: string;
  title: string;
  url: string;
  active: boolean;
}

export interface TabOpenedData {
  tab_id: string;
  title: string;
  url: string;
  active: boolean;
  tabs: TabInfo[];
}

export interface SwitchTabData {
  tab_id: string;
}

export interface TabSwitchedData {
  tab_id: string;
  title: string;
  url: string;
  tabs: TabInfo[];
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
