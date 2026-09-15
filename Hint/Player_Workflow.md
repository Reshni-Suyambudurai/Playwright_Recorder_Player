# Player Workflow

> How the playback engine works — from clicking Run to seeing the final result.

---

## 1. High-Level Flow

```
User clicks Run
      │
      ▼
[Frontend] POST /play/start  ──►  [api/play.py] creates PlaySession  ──►  returns play_id
      │
      ▼
[Frontend] opens WebSocket /ws/play/{play_id}
      │
      ▼
[Frontend] sends HELLO { clientId }
      │
      ▼
[playback_handler.py] registers client, launches asyncio Task: run_playback()
      │
      ├──── For each step ────────────────────────────────────────────────────
      │        │
      │        ├─► send PLAY_STEP_START  →  frontend highlights step in list
      │        │
      │        ├─► _execute_step() dispatch table
      │        │        ├─ NAVIGATE → page.goto(url, domcontentloaded)
      │        │        ├─ CLICK    → wait_for_selector(15s) → element.click()
      │        │        ├─ TYPE     → wait_for_selector(15s) → perform_type()
      │        │        ├─ SCROLL   → perform_scroll(x, y, deltaY)
      │        │        └─ KEY      → keyboard.press(key)
      │        │
      │        ├─► on failure → PLAY_STEP_ERROR → cap_mgr.request(ERROR) → break
      │        │
      │        ├─► _settle_page() — only for CLICK / KEY(Enter):
      │        │        └─ 500ms URL poll → if navigated → domcontentloaded(3s)
      │        │
      │        ├─► waitAfterMs sleep (from recording, 100–300ms)
      │        │
      │        ├─► cap_mgr.request(STEP_DONE) → 300ms FIXED_DELAY → FRAME
      │        │        └─ frontend: img.src = base64 JPEG
      │        │
      │        └─► if step.pause:
      │                 send PLAY_PAUSED → block on pause_event
      │                 frontend can click/scroll/type on the paused frame
      │                 PLAY_RESUME → pause_event.set() → continue
      │
      └──── After last step ────────────────────────────────────────────────
               │
               ▼
         send PLAY_DONE { stepCount, failedCount, failedSteps }
               │
               ▼
         DomWatcher.detach() → cap_mgr.stop() → browser.close()
```

---

## 2. File Map

### Backend

| File | Role |
|---|---|
| `api/play.py` | REST `POST /play/start` — loads recording JSON, creates `PlaySession`, returns `play_id`. Also `DELETE /play/{id}` to cancel. |
| `models/playback.py` | `PlaySession` dataclass — holds browser/page/task/capture_manager/dom_watcher references, status, pause_event. `PlayStatus` enum (PENDING / RUNNING / PAUSED / DONE / STOPPED / ERROR). |
| `websocket/playback_handler.py` | WebSocket event router for `/ws/play/{id}`. Handles HELLO → start task; PLAY_RESUME → unblock pause; PLAY_STOP → cancel task; PAUSE_CLICK / PAUSE_SCROLL / PAUSE_TYPE → interact during pause; PING → PONG. |
| `services/playback_service.py` | **Core engine.** `run_playback()` — the asyncio task that iterates steps, dispatches via `_STEP_HANDLERS`, calls `_settle_page()`, sends FRAME via `cap_mgr.request(STEP_DONE)`. |
| `services/capture_manager.py` | Per-session screenshot coordinator. Owns `asyncio.Lock`, settle strategies, dirty-flag DOM worker. HIGH priority = immediate capture with fixed delay. LOW = dirty flag only (worker fires at 300ms intervals). |
| `services/dom_watcher.py` | Attached to the playback page. On mutation → sets `capture_manager._dirty = True`. Background worker in CaptureManager fires a screenshot every 300ms if dirty. Detached in `run_playback` `finally` block. |
| `services/browser_service.py` | Playwright wrapper: `launch_browser(headless=True, viewport)`, `perform_click()`, `perform_type()`, `perform_scroll()`, `perform_key()`, `take_screenshot()`. |
| `services/screenshot_service.py` | `capture_and_send()` — takes JPEG screenshot (quality 60, 1280×720), base64-encodes, sends `FRAME` event. Logs CDP time, encode time, WS send time. |
| `websocket/connection_manager.py` | Maps `play_id:client_id` → WebSocket. `send_to_client()` delivers all events. |

### Frontend

| File | Role |
|---|---|
| `pages/runs/runs.ts` | Page component. Signals: `playStatus`, `currentStep`, `totalSteps`, `currentStepId`, `failedCount`, `hasLiveFrame`, `pauseInputData`. Calls `playbackApi.startPlay()` then opens WebSocket. Handles FRAME, PAUSE_CLICK, PAUSE_TYPE, PAUSE_SCROLL. |
| `pages/runs/runs.html` | Template. `<img #frameImg>` always in DOM (hidden via CSS until first frame). Step list with active highlight. Overlays: running / paused / done / done_with_errors / error / stopped. `app-input-overlay` for PAUSE_TYPE. |
| `pages/runs/runs.css` | Player layout. `.player-screen` uses `--bg-tertiary`. `.player-live-frame` uses `object-fit: contain`. `.player-screen--interactive` cursor crosshair in paused state. |
| `services/playback.api.ts` | `startPlay(recordingJson)` → POST. WebSocket connection management. Dispatches events to `handleEvent()` → `PlaybackStateApi`. |

---

## 3. WebSocket Event Reference

```
Frontend → Backend
──────────────────────────────────────────────────────────
HELLO          { clientId }                starts playback task
PLAY_RESUME    {}                          unblocks a paused step
PLAY_STOP      {}                          cancels the asyncio task
PAUSE_CLICK    { x, y }                   click on frame during pause
PAUSE_SCROLL   { x, y, delta_y }          scroll on frame during pause
PAUSE_TYPE     { selector, text }          type into input during pause
PING           {}                          keep-alive

Backend → Frontend
──────────────────────────────────────────────────────────
WELCOME              { play_session_id }               HELLO acknowledged
PLAY_STEP_START      { stepId, index, total, type }    step about to execute
PLAY_STEP_SKIPPED    { stepId }                        shouldRun=false
PLAY_STEP_ERROR      { stepId, type, error }           step failed → stops
PLAY_PAUSED          { stepId, index }                 step has pause=true
PAUSE_INPUT_DETECTED { x, y, selector, tag, ... }     PAUSE_CLICK on input field
FRAME                { image, width, height, source }  JPEG base64 screenshot
PLAY_DONE            { stepCount, failedCount,         all steps finished
                       failedSteps[] }
PLAY_ERROR           { error }                         fatal engine error
PONG                 { timestamp }                     ping response
```

---

## 4. Step Execution Detail (`playback_service.py`)

```
_execute_step(step, page)
      │
      ├─ dispatch via _STEP_HANDLERS dict
      │
      ├─ NAVIGATE  ──►  page.goto(url, wait_until="domcontentloaded", timeout=30s)
      │
      ├─ CLICK
      │      ├─ _resolve_pw_selector(step.selector)
      │      ├─ selector exists?
      │      │     └─► wait_for_selector(timeout=15s)  (SPAs need time to render)
      │      │           └─ None → raise "CLICK target not found" → PLAY_STEP_ERROR
      │      │           └─ found → element.click(button)
      │      └─ no selector → coords fallback → mouse.click(x, y)
      │
      ├─ TYPE
      │      ├─ _resolve_pw_selector(step.selector)
      │      ├─ wait_for_selector(timeout=15s)
      │      │     └─ None → raise "element not found" → PLAY_STEP_ERROR
      │      └─ perform_type(page, selector, text)
      │            └─ isPassword → keyboard.press("Enter") after fill
      │
      ├─ SCROLL  ──►  mouse.move(x,y) + mouse.wheel(deltaX, deltaY)
      │
      └─ KEY     ──►  keyboard.press(key)
```

---

## 5. Screenshot Pipeline (per step)

```
_execute_step() completes
      │
      ├─ _settle_page()
      │     └─ CLICK/KEY(Enter) only:
      │           wait_for_function("location.href !== before", timeout=500ms)
      │           if navigated → wait_for_load_state("domcontentloaded", timeout=3s)
      │           else → pass  (CaptureManager owns the wait)
      │
      ├─ await asyncio.sleep(waitAfterMs / 1000)  ← from recording (100–300ms)
      │
      ├─ cap_mgr.request(page, STEP_DONE)
      │     ├─ reason = HIGH priority → _dirty = False
      │     ├─ acquire asyncio.Lock
      │     ├─ FIXED_DELAY 300ms
      │     ├─ screenshot_service.capture_and_send()
      │     │     ├─ CDP screenshot (JPEG quality=60, 1280×720)  ~30–50 KB
      │     │     ├─ base64 encode  → ~40–67 KB
      │     │     └─ WebSocket send → FRAME event → frontend img.src
      │     └─ release lock
      │
      └─ DomWatcher worker (background, 300ms interval)
            if _dirty → capture_and_send() → FRAME (DOM updates after the step)
```

---

## 6. Pause Mode — Interactive on Frame

When `step.pause = true`, playback blocks and the frontend becomes interactive:

```
PLAY_PAUSED received
      │
      ├─ Overlay shows "Paused at Step N"
      ├─ player-screen gets cursor: crosshair
      │
      ├─ User clicks frame
      │     → onFrameClick() → _toPageCoords() (letterbox math)
      │     → sends PAUSE_CLICK { x, y }
      │     → backend: build_selector(x, y)
      │           is_input? → PAUSE_INPUT_DETECTED → InputOverlay shown
      │           else      → page.mouse.click(x, y) → cap_mgr.request(PAUSE_CLICK) → FRAME
      │
      ├─ User types in InputOverlay
      │     → onPauseTypeConfirm(text)
      │     → sends PAUSE_TYPE { selector, text }
      │     → backend: perform_type(page, selector, text) → cap_mgr.request(PAUSE_TYPE) → FRAME
      │
      ├─ User scrolls frame
      │     → onFrameWheel() → _toPageCoords()
      │     → sends PAUSE_SCROLL { x, y, delta_y }
      │     → backend: page.mouse.wheel(delta_y) → cap_mgr.request(PAUSE_SCROLL) → FRAME
      │
      └─ User clicks Resume
            → sends PLAY_RESUME
            → backend: pause_event.set() → run_playback continues
```

---

## 7. Failure Handling

```
Step throws exception
      │
      ├─► PLAY_STEP_ERROR { stepId, type, error }
      ├─► cap_mgr.request(ERROR) → FRAME (shows page at moment of failure)
      ├─► break — remaining steps are not run
      └─► PLAY_DONE { failedCount: 1, failedSteps: [...] }
                │
                ▼
          Frontend overlay: ⚠ Done — N steps — 1 failed
```

---

## 8. Status Flow

```
PENDING ──► RUNNING ──► DONE
               │
               ├──► PAUSED ──► RUNNING  (on PLAY_RESUME)
               │
               ├──► STOPPED              (on PLAY_STOP)
               │
               └──► ERROR               (fatal engine exception)
```

---

## 9. Coordinate Mapping — PAUSE_CLICK / PAUSE_SCROLL

The `<img>` element uses `object-fit: contain`, which adds letterboxing/pillarboxing. Raw `clientX/Y` cannot be used directly — they must be remapped to the actual rendered image area.

```
_toPageCoords(clientX, clientY, imgElement)
      │
      ├─ rect = imgElement.getBoundingClientRect()
      ├─ naturalW=1280, naturalH=720
      ├─ scale = min(rect.width/1280, rect.height/720)
      ├─ renderedW = 1280 * scale, renderedH = 720 * scale
      ├─ offsetX = (rect.width - renderedW) / 2     ← letterbox horizontal
      ├─ offsetY = (rect.height - renderedH) / 2    ← letterbox vertical
      ├─ relX = clientX - rect.left - offsetX
      ├─ relY = clientY - rect.top - offsetY
      └─ if relX/relY outside rendered area → return null (ignore click)
         else → { x: relX / scale, y: relY / scale }  ← 1280×720 coords
```


```
User clicks Run
      │
      ▼
[Frontend] POST /play/start  ──►  [Backend] creates PlaySession  ──►  returns play_session_id
      │
      ▼
[Frontend] opens WebSocket /ws/play/{play_session_id}
      │
      ▼
[Frontend] sends HELLO {clientId, ...}
      │
      ▼
[Backend] registers client, spawns asyncio Task: run_playback()
      │
      ├──── For each step ────────────────────────────────────────────────────
      │        │
      │        ├─► send PLAY_STEP_START  →  frontend highlights step in list
      │        │
      │        ├─► execute step (NAVIGATE / CLICK / TYPE / SCROLL / KEY)
      │        │        │
      │        │        ├─ CLICK: check selector → click element (or coords fallback)
      │        │        ├─ TYPE:  check selector → fill field  → press Enter if password
      │        │        └─ NAVIGATE: page.goto(url)
      │        │
      │        ├─► on failure → send PLAY_STEP_ERROR  →  break (stop all steps)
      │        │
      │        ├─► settle page (wait for URL change / networkidle)
      │        │
      │        ├─► take screenshot → send FRAME event
      │        │        └─ frontend: img.src = base64 JPEG  (direct DOM, no Angular zone)
      │        │
      │        └─► if step.pause → send PLAY_PAUSED → wait for PLAY_RESUME
      │
      └──── After last step ───────────────────────────────────────────────────
               │
               ▼
         send PLAY_DONE { stepCount, failedCount, failedSteps }
               │
               ▼
         close browser, detach DomWatcher
```

---

## 2. File Map

### Backend

| File | Role |
|---|---|
| `api/play.py` | REST endpoint `POST /play/start` — creates `PlaySession`, returns `play_session_id`. Also `DELETE /play/{id}` to cancel. |
| `models/playback.py` | `PlaySession` dataclass — holds browser/page/task references, status, pause_event. `PlayStatus` enum (PENDING / RUNNING / PAUSED / DONE / STOPPED / ERROR). |
| `websocket/playback_handler.py` | WebSocket event router for `/ws/play/{id}`. Handles `HELLO` → start task, `PLAY_RESUME` → unblock pause, `PLAY_STOP` → cancel task, `PING` → PONG. |
| `services/playback_service.py` | **Core engine.** `run_playback()` — the asyncio task that iterates steps, sends events, manages settle/screenshot cycle. `_execute_step()` dispatches each step type. |
| `services/browser_service.py` | Playwright wrapper. `launch_browser(headless, viewport)`, `perform_click()`, `perform_type()` (with selector pre-check), `perform_scroll()`, `navigate_to_url()`. |
| `services/screenshot_service.py` | `capture_and_send()` — takes JPEG screenshot (quality 60), base64-encodes it, sends as `FRAME` event via ConnectionManager. |
| `services/dom_watcher.py` | Attached to the page during playback. Fires screenshots automatically on DOM mutations (debounced). Suppressed during active step execution. |
| `websocket/connection_manager.py` | Maps `session_id:client_id` → WebSocket. `send_to_client()` delivers all events. |

### Frontend

| File | Role |
|---|---|
| `pages/runs/runs.ts` | Page component. Signals: `playStatus`, `currentStep`, `totalSteps`, `currentStepId`, `failedCount`, `hasLiveFrame`. Calls `playbackApi.startPlay()` then `connectWs()`. |
| `pages/runs/runs.html` | Template. `<img #frameImg>` always in DOM (hidden via CSS until first frame). Step list with active highlight. Overlays: running / paused / done / done_with_errors / error / stopped. |
| `pages/runs/runs.css` | Player layout styles. `.player-screen` uses `--bg-tertiary` (theme-aware). `.player-live-frame` uses `object-fit: contain`. |
| `services/playback.api.ts` | `startPlay(recordingJson)` → POST. `connectWs(playId, clientId, handlers)` → opens WebSocket, dispatches events to `onMessage(evt)`. |

---

## 3. WebSocket Event Reference

```
Frontend → Backend
──────────────────
HELLO          { clientId }                    starts playback task
PLAY_RESUME    {}                               unblocks a paused step
PLAY_STOP      {}                              cancels the task
PING           {}                               keep-alive

Backend → Frontend
──────────────────
WELCOME        { playId }                       HELLO acknowledged
PLAY_STEP_START  { stepId, index, total, type } step about to execute
PLAY_STEP_SKIPPED { stepId }                    shouldRun=false
PLAY_STEP_ERROR  { stepId, type, error }        step failed → playback stops
PLAY_PAUSED    { stepId, index }                step has pause=true
FRAME          { image, width, height }         JPEG base64 screenshot
PLAY_DONE      { stepCount, failedCount,        all steps finished
                 failedSteps[] }
PLAY_ERROR     { error }                        fatal engine error
```

---

## 4. Step Execution Detail

```
_execute_step(step, page)
      │
      ├─ NAVIGATE  ──►  page.goto(url, domcontentloaded)
      │
      ├─ CLICK
      │      ├─ selector exists?  ──►  element.click()  (accurate)
      │      └─ selector missing  ──►  mouse.click(x, y)  (coords fallback)
      │            └─ coords also fail  ──►  raise → PLAY_STEP_ERROR
      │
      ├─ TYPE
      │      ├─ selector pre-check: query_selector()
      │      │      └─ None  ──►  raise "element not found" → PLAY_STEP_ERROR
      │      ├─ page.fill(selector, text)
      │      └─ isPassword=true  ──►  keyboard.press("Enter")
      │
      ├─ SCROLL  ──►  mouse.move(x,y) + mouse.wheel(dx, dy)
      │
      └─ KEY     ──►  keyboard.press(key)
```

---

## 5. Screenshot Pipeline

```
Playwright headless page
      │
      │  page.screenshot(type=jpeg, quality=60, timeout=5s)
      ▼
raw JPEG bytes  (~30–50 KB)
      │
      │  base64.b64encode()
      ▼
base64 string  (~40–67 KB)
      │
      │  wrapped in { event_type: "FRAME", data: { image: "data:image/jpeg;base64,..." } }
      ▼
WebSocket text frame  →  Browser
      │
      │  requestAnimationFrame callback (throttled, no Angular zone)
      ▼
 img.src = data  (direct DOM write, no change detection)
```

> DomWatcher fires additional FRAME events on DOM mutations (e.g. after navigation),  
> so the preview updates even between explicit step screenshots.

---

## 6. Failure Handling

```
Step throws exception
      │
      ├─► PLAY_STEP_ERROR sent { stepId, type, error }
      ├─► screenshot of failure state sent (FRAME)
      ├─► break — no more steps run
      │
      └─► PLAY_DONE { failedCount: 1, failedSteps: [...] }
                │
                ▼
          Frontend overlay: ⚠ Done — N steps — 1 failed
```

**TYPE selector pre-check** is the primary failure detector for application-level errors  
(e.g. wrong password → login page stays → next TYPE target not found → immediate fail).

---

## 7. Status Flow

```
PENDING  ──► RUNNING ──► DONE
                │
                ├──► PAUSED ──► RUNNING (on PLAY_RESUME)
                │
                ├──► STOPPED  (on PLAY_STOP)
                │
                └──► ERROR    (fatal engine exception)
```
