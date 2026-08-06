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
  | 'PAGE_REFRESH'
  | 'PAGE_BACK'
  | 'STOP_RECORDING'
  | 'RECORDING_STOPPED'
  | 'TAB_OPENED'
  | 'SWITCH_TAB'
  | 'TAB_SWITCHED'
  | 'SESSION_CLOSED'
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
  occurrence_index?: number;
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
  inputValidation?: InputValidation | null;
}

export type InputValidationMode =
  | 'alphabet'
  | 'numeric'
  | 'alphanumeric'
  | 'date'
  | 'email'
  | 'mobile'
  | 'strongPassword'
  | 'custom';

export interface InputValidation {
  required?: boolean;
  description?: string | null;
  mode?: InputValidationMode | null;
  minLength?: number | null;
  maxLength?: number | null;
  customRegex?: string | null;
  allowNegativeNumber?: boolean;
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

/* Recording List / Detail */
export interface RecordingListItem {
  recordId: string;
  userId: string;
  flowName: string;
  description: string;
  stepCount: number;
  createdAt: number | null;
  updatedAt: number | null;
}

export interface RecordingStep {
  id: number;
  type: string;
  url?: string;
  pageUrl?: string;
  pageTitle?: string;
  text?: string;
  label?: string;
  coords?: { x: number; y: number } | null;
  selector?: { strategy: string; value: string } | null;
  isTriggerNewTab?: boolean | null;
  frameIndex?: number;
  tab_id?: string;
  isPassword?: boolean;
  shouldRun?: boolean;
  pause?: boolean;
  storeValue?: boolean;
  inputValidation?: InputValidation | null;
}

export interface RecordingDetail {
  version: string;
  meta: {
    id: string;
    title: string;
    description: string;
    intent: string;
    createdAt: number;
    updatedAt?: number;
    viewport: { width: number; height: number; deviceScaleFactor: number };
  };
  steps: Record<string, RecordingStep[][]>;
}

export interface ConnectionState {
  isConnected: boolean;
  sessionId: string | null;
  clientId: string | null;
  lastUpdate: Date | null;
  error: string | null;
  sessionClosed?: boolean;
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
