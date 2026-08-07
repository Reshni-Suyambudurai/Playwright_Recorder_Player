## RECORDING FLOW

### Recording Session Bootstrap

```text
User clicks Connect
        |
        v
POST /recording/start
        |
        v
SessionManager.create_session()
        |
        v
BrowserService.launch_browser()
        |
        v
Return session_id
        |
        v
Frontend opens WebSocket
        |
        v
Send HELLO (client_id)
        |
        v
WebSocketHandler.handle_hello()
        |
        v
ConnectionManager.register_client(...)
        |
        v
Send WELCOME
```


### Start Recording Flow (URL + metadata)

```text
User enters URL and recording_name
        |
        v
Send START_RECORDING
        |
        v
handle_start_recording()
        |
        v
Validate url + active session/page
        |
        v
Navigate to URL (BrowserService.navigate_to_url)
        |
        v
Create CaptureManager (per session)
        |
        v
Attach DomWatcher to page
        |
        v
Initialize recording state
(recording_id/name/description/intent, steps, tab maps)
        |
        v
Register tab-1 as active tab
        |
        v
Append first step: NAVIGATE (id=1)
        |
        v
Request MANUAL capture
        |
        v
Send FRAME
        |
        v
Send RECORDING_STARTED
```


### Continuous Recording Loop

```text
User action from UI
        |
        v
WS event received
(CLICK_ACTION / TYPE_ACTION / SCROLL_ACTION / KEY_ACTION / PAGE_REFRESH / PAGE_BACK / SWITCH_TAB)
        |
        v
Handler executes browser action
        |
        v
Append RecordingStep (id increments)
        |
        v
Send ACTION_DONE (or tab event)
        |
        v
CaptureManager.request(...)
        |
        v
ScreenshotService.capture_and_send()
        |
        v
Send FRAME
```


### CLICK + INPUT DETECTION FLOW

```text
CLICK_ACTION(x,y)
        |
        v
build_selector(page, x, y)
        |
        +-------------------------------+
        | left click on input element ? |
        +-------------------------------+
             | Yes                    | No
             v                        v
      Send INPUT_DETECTED      perform_click(x,y,button)
      (no click yet)                 |
             |                        v
             |                 Append CLICK step
             |                 (coords, selector, targetMeta)
             |                        |
             v                        v
Frontend opens overlay         CaptureManager ACTION_CLICK
and user confirms text               |
             |                        v
             +-------> TYPE_ACTION -> FRAME
```


### TYPE FLOW

```text
TYPE_ACTION(text, selector, is_password)
        |
        v
BrowserService.perform_type(...)
        |
        v
Append TYPE step
text = "{{password}}" if password else raw text
storeValue = true
        |
        v
CaptureManager ACTION_TYPE
        |
        v
Send ACTION_DONE
        |
        v
Send FRAME
```


### SCROLL FLOW

```text
SCROLL_ACTION(x,y,delta_x,delta_y)
        |
        v
BrowserService.perform_scroll(...)
        |
        v
Append SCROLL step
        |
        v
CaptureManager ACTION_SCROLL
        |
        v
Send ACTION_DONE + FRAME
```


### KEY FLOW

```text
KEY_ACTION(key)
        |
        v
Validate key in allowed set
(Enter, Tab, Escape, Backspace, ArrowUp, ArrowDown)
        |
        v
BrowserService.perform_key(key)
        |
        v
Append KEY step
        |
        v
CaptureManager request
(Enter -> ACTION_CLICK, others -> ACTION_TYPE)
        |
        v
Send ACTION_DONE + FRAME
```


### PAGE_REFRESH / PAGE_BACK FLOW

```text
PAGE_REFRESH or PAGE_BACK
        |
        v
reload()/go_back()
        |
        v
_capture_after_nav()
  - wait_for_load_state(networkidle, 5000 ms best effort)
  - update session.current_url
  - append NAVIGATE step
  - capture_and_send FRAME
        |
        v
Send ACTION_DONE
```


### TAB FLOW

```text
Browser opens new tab (context "page" event)
        |
        v
_on_new_tab()
  - wait domcontentloaded
  - allocate tab-N
  - register page + metadata
  - mark previous step isTriggerNewTab=true
  - attach DomWatcher for new tab
  - set active tab
  - append NAVIGATE step for new tab
  - send TAB_OPENED
  - send FRAME

User clicks tab in frontend
        |
        v
SWITCH_TAB
        |
        v
handle_switch_tab()
  - set active tab
  - update tab metadata
  - send FRAME
  - return TAB_SWITCHED
```


### Stop Recording Flow

```text
User clicks Stop Recording
        |
        v
Send STOP_RECORDING
        |
        v
handle_stop_recording()
        |
        v
Detach all tab watchers + legacy watcher
        |
        v
Build Recording(meta + steps)
        |
        +-----------------------------+
        | Save file + save to SQLite |
        +-----------------------------+
        |
        v
Build step summary list
        |
        v
Reset session recording state
        |
        v
Send RECORDING_STOPPED
```


### Recorder Timing / Settle References

| Operation | Timeout / Delay |
| --------- | --------------- |
| Browser navigate_to_url timeout | 30000 ms |
| Post-navigation network idle wait (best effort) | 5000 ms |
| CaptureManager poll interval (DOM worker) | 300 ms |
| ACTION_CLICK capture settle | fixed 300 ms |
| ACTION_TYPE capture settle | fixed 300 ms |
| ACTION_SCROLL capture settle | none |
| PAGE_BACK go_back timeout | 10000 ms |
| PAGE_REFRESH reload timeout | 30000 ms |




## Playback Entire Flow

```text
User clicks Play
        │
        ▼
POST /play/start
        │
        ▼
Create PlaySession
        │
        ▼
Return play_session_id
        │
        ▼
Open WebSocket
        │
        ▼
HELLO
        │
        ▼
PlaybackHandler starts run_playback() 
        │
        ▼
Launch Browser + Page
        │
        ├────────► Start CaptureManager
        │
        ├────────► Start DOMWatcher
        │
        ▼
Flatten recording steps
        │
        ▼
For each step:
    ├─ Send PLAY_STEP_START
    ├─ Execute action (click/type/navigate/...)
    ├─ Wait for page to settle if needed
    ├─ Capture screenshot
    └─ Send FRAME
        │
        ▼
Repeat until all steps complete
        │
        ▼
Send PLAY_DONE
        │
        ▼
Close browser and clean up
```


- play.py: the receptionist that creates a playback session.
- playback_handler.py: the traffic controller that receives WebSocket commands like HELLO, RESUME, and STOP.
- playback_service.py: the robot that actually performs the recorded actions.
- browser_service.py: the hands that control the browser.
- dom_watcher.py: the eyes that notice page changes.
- capture_manager.py: the photographer that decides when a screenshot should be taken.
- screenshot_service.py: the camera that captures the image and sends it to the frontend.
- connection_manager.py: the mail carrier that delivers events to the correct client.
- playback.py: the notebook that stores the current playback state.


### TYPE FLOW
```text
                      PLAY_STEP_START
                              │
                              ▼
                  Is Step Type = TYPE?
                              │
                              ▼
              wait_for_selector()
            visible timeout = 5000 ms
                              │
                ┌─────────────┴─────────────┐
                │                           │
          Element Found                Timeout
                │                           │
                ▼                           ▼
         Type Recorded Text          PLAY_STEP_ERROR
                │                     Stop Playback
                ▼
        Request Screenshot
          (STEP_DONE)
                │
                ▼
      CaptureManager waits
         FIXED_DELAY = 300 ms
                │
                ▼
      Screenshot Captured
                │
                ▼
        Execute Next Step
```

### CLICK FLOW

```text
                           PLAY_STEP_START
                                  │
                                  ▼
                      Is Step Type = CLICK?
                                  │
                                  ▼
                  Recorded Selector Available?
                                  │
                                  ▼
                    Retry Loop (Maximum 3 Attempts)
                                  │
             ┌────────────────────┴───────────────────┐
             │                                        │
     wait_for_selector()                      Selector Missing
    visible timeout = 3000 ms                        │
             │                                       │
             ▼                                       ▼
      Element Found?                     sleep(0.2 sec)
             │                                       │
     ┌───────┴────────┐                              │
     │                │                              │
    Yes              No────────────Retry < 3 ?──────┘
     │                               │
     ▼                               ▼
Click Element                  Retry Again
     │
     ▼
Check if URL Changed
wait_for_function()
timeout = 500 ms
     │
     ┌───────────────┴────────────────┐
     │                                │
 URL Changed                     URL Same
     │                                │
     ▼                                ▼
wait for                      Continue
domcontentloaded
timeout = 3000 ms
     │
     ▼
Request Screenshot
(STEP_DONE)
     │
     ▼
CaptureManager
FIXED_DELAY = 300 ms
     │
     ▼
Next Step
```

### CLICK FLOW: Selector Failed

```text
          Selector Not Found After 3 Retries
                         │
                         ▼
      sleep(0.35 sec)  (Stabilization Delay)
                         │
                         ▼
      Wait for requestAnimationFrame()
                    (2 browser frames)
                         │
                         ▼
      Dropdown Recovery Enabled?
                         │
          ┌──────────────┴───────────────┐
          │                              │
         Yes                             No(fallback)
          │                              │
          ▼                              ▼
 Search option by              Coordinate/TargetMeta
 recorded value                     validation
 (Example: "Meeting")                  │
          │                            │
      ┌───┴────┐                  ┌────┴────┐
      │        │                  │         │
    Found     Not Found        Match     No Match
      │        │                  │         │
      ▼        ▼                  ▼         ▼
 Click     Continue          Click      PLAY_STEP_ERROR
Recovered   Fallback         Element      Stop Playback
 Option
```


 | Operation             | Timeout / Delay |
| --------------------- | --------------- |
| wait_for_selector     | **3000 ms**     |
| Retry attempts        | **3**           |
| Delay between retries | **0.2 sec**     |
| Stabilization delay   | **0.35 sec**    |
| requestAnimationFrame | **2 frames**    |
| URL change detection  | **500 ms**      |
| DOMContentLoaded wait | **3000 ms**     |
| CaptureManager delay  | **300 ms**      |


### Navigation FLOW

```text
                            PLAY_STEP_START
                                   │
                                   ▼
                     Is Step Type = NAVIGATE?
                                   │
                                   ▼
                    page.goto(recordedUrl)
                 wait_until = "domcontentloaded"
                     timeout = 15000 ms
                                   │
                     ┌─────────────┴─────────────┐
                     │                           │
                 Success                     Timeout/Error
                     │                           │
                     ▼                           ▼
         Navigation Completed           PLAY_STEP_ERROR
                     │                           │
                     ▼                           ▼
          Request Screenshot             Stop Playback
           (STEP_DONE Capture)
                     │
                     ▼
         CaptureManager waits
              FIXED_DELAY = 300 ms
                     │
                     ▼
            Screenshot Captured
                     │
                     ▼
              Execute Next Step
```

