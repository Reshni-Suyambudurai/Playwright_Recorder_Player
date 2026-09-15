# Playwright Recorder & Player — Flow Reference

---

## 1. Server Startup

```
run.py → clear log → set event loop → uvicorn port 8001
  └─ app/main.py → SessionManager, BrowserService, ConnectionManager,
                   ScreenshotService, WebSocketHandler, DatabaseService
                   /recording/* | /play/* | /ws/* | /ws/play/*
```

---

## 2. Recorder Flow

### Session Start
```
POST /recording/start
  └─ launch Chromium (headless=false, 1280×720)
  └─ return session_id

WS HELLO → register client → WELCOME
WS START_RECORDING { url }
  └─ navigate(url)
  └─ CaptureManager created (per-session)
  └─ DomWatcher.attach(page) → start_worker()
  └─ NAVIGATE step recorded
  └─ cap_mgr.request(MANUAL) → FRAME #1
  └─ ← RECORDING_STARTED
```

### CLICK
```
CLICK_ACTION {x,y,button}
  └─ build_selector(x,y)
       ├─ is_input? → ← INPUT_DETECTED  (no click)
       └─ perform_click(x,y)
            └─ CLICK step recorded
            └─ ensure_future: cap_mgr.request(ACTION_CLICK)
                 └─ FIXED_DELAY 300ms → screenshot → FRAME
  └─ ← ACTION_DONE  (immediate)
```

### TYPE
```
TYPE_ACTION {text, selector}
  └─ perform_type(selector, text)
  └─ TYPE step recorded
  └─ ensure_future: cap_mgr.request(ACTION_TYPE)
       └─ FIXED_DELAY 300ms → screenshot → FRAME
  └─ ← ACTION_DONE  (immediate)
```

### SCROLL
```
SCROLL_ACTION {x,y,deltaX,deltaY}
  └─ mouse.move(x,y) → mouse.wheel(deltaX,deltaY)
  └─ SCROLL step recorded
  └─ ensure_future: cap_mgr.request(ACTION_SCROLL)
       └─ NONE 0ms → screenshot → FRAME
  └─ ← ACTION_DONE  (immediate)
```

### KEY
```
KEY_ACTION {key}
  └─ keyboard.press(key)
  └─ KEY step recorded
  └─ ensure_future: cap_mgr.request(ACTION_CLICK if Enter else ACTION_TYPE)
       └─ FIXED_DELAY 300ms → screenshot → FRAME
  └─ ← ACTION_DONE  (immediate)
```

### Stop Recording
```
STOP_RECORDING
  └─ DomWatcher.detach() → cap_mgr.stop()
  └─ Build Recording JSON
  └─ Save to disk + SQLite
  └─ ← RECORDING_STOPPED
```

---

## 3. Player Flow

### Session Start
```
POST /play/start {recording_id} → load JSON → return play_id

WS HELLO → register client → WELCOME
  └─ create_task(run_playback)
       └─ launch Chromium (headless=true, viewport from meta)
       └─ CaptureManager + DomWatcher.attach() → start_worker()
       └─ iterate steps →
```

### Step Loop
```
each step:
  shouldRun=false? → PLAY_STEP_SKIPPED → next
  └─ PLAY_STEP_START
  └─ _execute_step()
       ├─ fail → PLAY_STEP_ERROR → cap_mgr(ERROR) → FRAME → break
       └─ ok   → _settle_page()
                 └─ STEP_DONE (skip if NAVIGATE)
                      CLICK/TYPE  → FIXED_DELAY 300ms → FRAME
                      SCROLL/KEY  → NONE 0ms         → FRAME
                 └─ pause=true? → PLAY_PAUSED → wait PLAY_RESUME
  └─ (after all steps) PLAY_DONE
```

### NAVIGATE
```
page.goto(url, domcontentloaded)  ── timeout 15s ──►  fail → PLAY_STEP_ERROR
  └─ ok → STEP_DONE skipped (DomWatcher streams load frames)
```

### CLICK
```
resolve selector  →  #id | css:nth-match(n) | xpath=...
  └─ wait_for_selector  ── timeout 3s ──►  not found
       └─ found → element.click() ✓             └─ coords? → perform_click(x,y) ✓
                                                └─ no coords → PLAY_STEP_ERROR ✗
  └─ no selector → perform_click(x,y) ✓
after: FIXED_DELAY 300ms → FRAME
```

### TYPE
```
resolve selector
  └─ wait_for_selector  ── timeout 5s ──►  not found → PLAY_STEP_ERROR ✗
       └─ found → perform_type(selector, text) ✓
  └─ no selector → keyboard.type(text) ✓
after: FIXED_DELAY 300ms → FRAME
```

### SCROLL
```
mouse.move(x,y) → mouse.wheel(deltaX,deltaY) ✓  (never fails)
after: NONE 0ms → FRAME
```

### KEY
```
keyboard.press(key) ✓  (never fails)
after: NONE 0ms → FRAME
```

### _settle_page  (navigation detection)
```
runs only when: CLICK or KEY(Enter)  AND  step.url ≠ step.pageUrl
  └─ wait_for_function(url changed)  ── timeout 500ms ──►  no change → pass
       └─ changed → wait_for_load_state(domcontentloaded)  ── timeout 3s
all other steps → return immediately
```

---

## 4. DomWatcher  (runs in background throughout recording & playback)

```
JS MutationObserver  ─────────────────────────►  _dirty = True  (instant)
page "load" / "domcontentloaded"  ────────────►  _dirty = True

Background worker (every 300ms):
  _dirty?  YES → _dirty=False → acquire lock → screenshot → FRAME → release
           NO  → sleep again
```

---

## 5. Timeout Reference

| Step / Operation | Timeout |
|---|---|
| NAVIGATE `page.goto` | **15s** |
| CLICK `wait_for_selector` | **3s** → coords fallback |
| TYPE `wait_for_selector` | **5s** |
| `_settle_page` URL poll | **500ms** |
| `_settle_page` domcontentloaded | **3s** |
| STEP_DONE / ACTION settle | **300ms** fixed delay |
| DomWatcher worker interval | **300ms** |

---

## 6. Worst-Case Failure Time

| Step | Time before error |
|---|---|
| NAVIGATE | 15s |
| TYPE | 5s |
| CLICK (no coords) | 3s |
| SCROLL / KEY | never fails |


---

## 1. Server Startup

```
run.py
  │
  ├─ Clear debug.log (fresh log every run)
  ├─ Set WindowsProactorEventLoopPolicy (Playwright subprocess support on Windows)
  ├─ Import Uvicorn
  └─ uvicorn.run("app.main:app", host="0.0.0.0", port=8001, reload=False)
        │
        ▼
app/main.py
  │
  ├─ Create singletons: SessionManager, BrowserService, ConnectionManager,
  │                     ScreenshotService, WebSocketHandler, DatabaseService
  ├─ Mount routers:
  │     /recording/*   → api/recording.py
  │     /play/*        → api/play.py
  │     /health        → main.py
  ├─ Register WebSocket endpoints:
  │     /ws/{session_id}        → websocket_handler.py  (recording)
  │     /ws/play/{play_id}      → playback_handler.py   (playback)
  └─ DB initialise (SQLite via aiosqlite)
```

---

## 2. Recorder Flow

### 2.1 Session Start

```
POST /recording/start
  │
  ├─ SessionManager.create_session()       → RecordingSession (in-memory)
  ├─ BrowserService.launch_browser()       → Chromium (headless=false, viewport 1280×720)
  └─ return { session_id }

WebSocket /ws/{session_id}
  │
  ├─ Client sends HELLO { client_id }
  │     → ConnectionManager.register_client(session_id, client_id, ws)
  │     ← WELCOME
  │
  └─ Client sends START_RECORDING { url, recording_name }
        │
        ├─ BrowserService.navigate_to_url(page, url)          timeout: no explicit (Playwright default)
        ├─ CaptureManager(screenshot_service, session_id, client_id)   ← per-session instance
        ├─ DomWatcher(cap_mgr).attach(page)
        │     ├─ page.on("load")           → _dirty = True
        │     ├─ page.on("domcontentloaded") → _dirty = True
        │     ├─ MutationObserver injected via add_init_script
        │     └─ cap_mgr.start_worker(page)   ← background loop starts
        ├─ NAVIGATE step recorded (step id=1)
        ├─ cap_mgr.request(page, MANUAL)   → immediate screenshot → FRAME #1
        └─ ← RECORDING_STARTED
```

### 2.2 CLICK Action (recording)

```
Client sends CLICK_ACTION { x, y, button }
  │
  ├─ build_selector(page, x, y)      ← JS runs in browser (elementFromPoint)
  │     returns { tag, is_input, selector, label, occurrence_index, ... }
  │
  ├─ is_input AND button=left?
  │     YES → return INPUT_DETECTED (no click — frontend opens type overlay)
  │     NO  →
  │           record pre_click_url = page.url
  │           BrowserService.perform_click(page, x, y, button)
  │           RecordingStep appended { type:CLICK, pageUrl, coords, selector }
  │           asyncio.ensure_future(cap_mgr.request(page, ACTION_CLICK))
  │                → background: FIXED_DELAY(300ms) → screenshot → FRAME
  └─ ← ACTION_DONE  (returned immediately, frame arrives ~300ms later)
```

### 2.3 TYPE Action (recording)

```
Client sends TYPE_ACTION { text, selector, x, y, is_password }
  │
  ├─ BrowserService.perform_type(page, selector, text)
  │     → page.fill(selector, text)  OR  locator.fill()
  ├─ RecordingStep appended { type:TYPE, text, selector }
  ├─ asyncio.ensure_future(cap_mgr.request(page, ACTION_TYPE))
  │     → background: FIXED_DELAY(300ms) → screenshot → FRAME
  └─ ← ACTION_DONE
```

### 2.4 SCROLL Action (recording)

```
Client sends SCROLL_ACTION { x, y, deltaX, deltaY }
  │
  ├─ BrowserService.perform_scroll(page, x, y, deltaX, deltaY)
  │     → page.mouse.move(x, y) + page.mouse.wheel(deltaX, deltaY)
  ├─ RecordingStep appended { type:SCROLL, coords, deltaX, deltaY }
  ├─ asyncio.ensure_future(cap_mgr.request(page, ACTION_SCROLL))
  │     → background: NONE settle → immediate screenshot → FRAME
  └─ ← ACTION_DONE
```

### 2.5 KEY Action (recording)

```
Client sends KEY_ACTION { key }
  │
  ├─ BrowserService.perform_key(page, key)
  │     → page.keyboard.press(key)
  ├─ RecordingStep appended { type:KEY, text:key }
  ├─ reason = ACTION_CLICK if key=="Enter" else ACTION_TYPE
  │   asyncio.ensure_future(cap_mgr.request(page, reason))
  │     → FIXED_DELAY(300ms) → screenshot → FRAME
  └─ ← ACTION_DONE
```

### 2.6 Stop Recording

```
Client sends STOP_RECORDING
  │
  ├─ DomWatcher.detach()       → cap_mgr.stop() (worker cancelled, _dirty cleared)
  ├─ Build Recording JSON from session.recording_steps
  ├─ Save to disk:  storage/recordings/<id>.json
  ├─ Save to DB:    DatabaseService.save_recording()
  └─ ← RECORDING_STOPPED { stepCount, steps[] }
```

### 2.7 DomWatcher — During Recording

```
Background worker (every 300ms):
  if _dirty AND page alive:
    _dirty = False
    acquire asyncio.Lock
    CDP screenshot → base64 → FRAME
    release lock

Any DOM mutation (JS MutationObserver):
  → __domChanged__() callback → _dirty = True   (instant, zero tasks)

page "load" / "domcontentloaded" events:
  → _dirty = True
```

---

## 3. Player Flow

### 3.1 Session Start

```
POST /play/start { recording_id }
  │
  ├─ Load recording JSON from DB
  └─ return { play_id }

WebSocket /ws/play/{play_id}
  │
  ├─ Client sends HELLO { client_id }
  │     → ConnectionManager.register_client(play_id, client_id, ws)
  │     ← WELCOME
  │     → asyncio.create_task(playback_service.run_playback())
  │
  └─ run_playback():
        ├─ BrowserService.launch_browser(headless=True, viewport from meta)
        ├─ CaptureManager(screenshot_service, play_id, client_id)
        ├─ DomWatcher(cap_mgr).attach(page)   ← same as recorder
        └─ iterate steps → _execute_step()
```

### 3.2 Step Execution Loop

```
For each step:
  │
  ├─ shouldRun=false?  → PLAY_STEP_SKIPPED → next step
  │
  ├─ send PLAY_STEP_START { stepId, index, total, type }
  │
  ├─ _execute_step(step, page)     ← see per-step detail below
  │
  ├─ exception?
  │     YES → PLAY_STEP_ERROR { stepId, error }
  │           cap_mgr.request(ERROR) → immediate screenshot → FRAME
  │           break (all remaining steps skipped)
  │
  ├─ _settle_page()                ← navigation detection only
  │
  ├─ step_type != NAVIGATE?
  │     YES → cap_mgr.request(STEP_DONE, settle=per_type)
  │               CLICK/TYPE : FIXED_DELAY(300ms) → screenshot → FRAME
  │               SCROLL/KEY : NONE(0ms)          → screenshot → FRAME
  │     NO (NAVIGATE) → skip STEP_DONE (DomWatcher streams page load frames)
  │
  └─ pause=true?
        → PLAY_PAUSED sent → block on asyncio.Event
        → wait for PLAY_RESUME (client sends PLAY_RESUME)
        → continue
```

### 3.3 NAVIGATE Step

```
page.goto(url, wait_until="domcontentloaded", timeout=15s)
  ↓ success → continue
  ↓ timeout / fail → exception → PLAY_STEP_ERROR → break

Timeouts:  goto = 15s
Fallback:  none
```

### 3.4 CLICK Step

```
_resolve_pw_selector(step.selector)
  ├─ strategy=id    → "#value"
  ├─ strategy=css   → "value"  OR  "value:nth-match(n+1)"  if occurrence_index > 0
  └─ strategy=xpath → "xpath=value"

selector exists?
  │
  ├─ YES
  │    wait_for_selector(pw_selector, timeout=3s)
  │      ↓ found → element.click(button) → done ✓
  │      ↓ not found / timeout after 3s
  │           coords available?
  │             YES → WARNING logged → perform_click(x, y) → done ✓
  │             NO  → raise → PLAY_STEP_ERROR → break ✗
  │
  └─ NO selector
       coords → perform_click(x, y) → done ✓
       no coords → silently skipped

Timeouts:  wait_for_selector = 3s
Fallback:  coords (instant, no extra wait)
```

### 3.5 TYPE Step

```
selector exists?
  │
  ├─ YES
  │    _resolve_pw_selector()
  │    wait_for_selector(pw_selector, timeout=5s)
  │      ↓ found → BrowserService.perform_type(page, selector, text)
  │                  → page.fill() or locator.fill()
  │      ↓ not found after 5s → raise → PLAY_STEP_ERROR → break ✗
  │    (no coords fallback — TYPE requires the actual element)
  │
  └─ NO selector
       page.keyboard.type(text) → done ✓

Timeouts:  wait_for_selector = 5s
Fallback:  keyboard.type if no selector
```

### 3.6 SCROLL Step

```
perform_scroll(page, x, y, deltaX, deltaY)
  → page.mouse.move(x, y)
  → page.mouse.wheel(deltaX, deltaY)
  → done ✓

Timeouts:  none
Fallback:  none — never fails
```

### 3.7 KEY Step

```
perform_key(page, key_text)
  → page.keyboard.press(key)
  → done ✓

Timeouts:  none
Fallback:  none — never fails
```

### 3.8 _settle_page (navigation detection)

```
Called after every step. Runs only when:
  step_type == CLICK  OR  (step_type == KEY AND key_text == "Enter")
  AND  step.url is not None  AND  step.url != step.pageUrl

wait_for_function("location.href !== before", timeout=500ms)
  ↓ url changed → wait_for_load_state("domcontentloaded", timeout=3s)
  ↓ no change   → pass (500ms elapsed, harmless)

All other steps (TYPE, SCROLL, KEY non-Enter, SPA CLICKs):
  → return immediately (0ms)
```

### 3.9 DomWatcher — During Playback

Same as recording. Runs in background throughout entire playback:

```
Background worker (every 300ms):
  if _dirty:
    _dirty = False
    acquire lock (waits if STEP_DONE in progress)
    CDP screenshot → base64 → FRAME
    release lock

DOM mutation → _dirty = True  (zero tasks, zero awaits)
page load/domcontentloaded → _dirty = True
```

---

## 4. CaptureManager — Settle Strategy Reference

| CaptureReason | Settle | Delay | Used by |
|---|---|---|---|
| `ACTION_CLICK` | FIXED_DELAY | 300ms | Recorder CLICK/KEY(Enter) |
| `ACTION_TYPE` | FIXED_DELAY | 300ms | Recorder TYPE |
| `ACTION_SCROLL` | NONE | 0ms | Recorder SCROLL |
| `STEP_DONE` (CLICK/TYPE) | FIXED_DELAY | 300ms | Player CLICK/TYPE |
| `STEP_DONE` (SCROLL/KEY) | NONE | 0ms | Player SCROLL/KEY |
| `DOM_MUTATION` | NONE | 0ms | DomWatcher worker |
| `MANUAL` | NONE | 0ms | First frame on connect |
| `ERROR` | NONE | 0ms | Step failure screenshot |
| `PAUSE_CLICK` | FIXED_DELAY | 300ms | Pause-mode click |
| `PAUSE_SCROLL` | NONE | 0ms | Pause-mode scroll |
| `PAUSE_TYPE` | FIXED_DELAY | 300ms | Pause-mode type |

---

## 5. Timeout Summary

| Operation | Timeout | Location |
|---|---|---|
| NAVIGATE `page.goto` | **15s** | `_step_navigate` |
| CLICK `wait_for_selector` | **3s** (then coords fallback) | `_step_click` |
| TYPE `wait_for_selector` | **5s** | `_step_type` |
| `_settle_page` URL poll | **500ms** | `_settle_page` |
| `_settle_page` domcontentloaded | **3s** | `_settle_page` |
| ACTION_CLICK / STEP_DONE settle | **300ms** | `CaptureManager` |
| DomWatcher worker poll | **300ms interval** | `CaptureManager._dom_capture_worker` |

---

## 6. Worst-Case Step Failure Time

| Step | Max wait before PLAY_STEP_ERROR |
|---|---|
| NAVIGATE | 15s |
| TYPE (selector missing) | 5s |
| CLICK (selector missing, no coords) | 3s |
| SCROLL | never fails |
| KEY | never fails |

      │
      ▼
app/main.py           (Creates the FastAPI application)
      │
      ├── Database
      ├── Services
      ├── Routers
      ├── WebSockets
      └── Health endpoint

run.py

This file does not contain your application logic.

Its only job is:


Python Starts
      │
      ▼
Clear debug.log
      │
      ▼
Configure Windows Event Loop
      │
      ▼
Import Uvicorn
      │
      ▼
Start Server
      │
      ▼
Load app.main


app/main.py
Main entry point for the Playwright Recorder backend application.

Application
│
├── /recording/*   → recording.py
│
├── /play/*        → play.py
│
├── /health        → main.py
│
├── /ws/*          → main.py
│
└── /ws/play/*     → main.py


Player Flow:

## Complete Playback Execution Flow

---

### NAVIGATE step
```
page.goto(url, wait_until="domcontentloaded", timeout=30s)
  ↓ success → continue
  ↓ timeout/fail → exception → PLAY_STEP_ERROR → break
```
No fallback. No coords. Must succeed.

---

### CLICK step
```
resolve selector (strategy + value + occurrence_index)
  │
  ├─ id       →  "#value"
  ├─ css      →  "value"  OR  "value:nth-match(n+1)"  if occurrence_index > 0
  └─ xpath    →  "xpath=value"
  │
  ▼
selector exists?
  │
  ├─ YES
  │    wait_for_selector(pw_selector, timeout=3s)
  │      ↓ found within 3s → element.click(button) → done ✓
  │      ↓ not found / timeout (3s wasted)
  │          coords available?
  │            ├─ YES → [WARNING logged] → perform_click(x, y) → done ✓
  │            └─ NO  → raise Exception → PLAY_STEP_ERROR → break ✗
  │
  └─ NO selector
       coords available → perform_click(x, y) → done ✓
       no coords        → step silently skipped (no action, no error)
```
**Timeouts**: `wait_for_selector = 3s`. Coords fallback is instant.

---

### TYPE step
```
selector exists?
  │
  ├─ YES
  │    resolve pw_selector
  │    wait_for_selector(pw_selector, timeout=15s)
  │      ↓ found → perform_type(page, selector, text)
  │                  → page.fill(selector, text)  OR  page.type()
  │      ↓ not found / timeout (15s wasted) → raise Exception → PLAY_STEP_ERROR → break ✗
  │    NO coords fallback for TYPE
  │
  └─ NO selector
       page.keyboard.type(text) → done ✓
```
**Timeouts**: `wait_for_selector = 15s`. No fallback — TYPE needs the element.

---

### SCROLL step
```
coords = step.coords  (defaults to {x:0, y:0} if missing)
perform_scroll(page, x, y, deltaX, deltaY)
  → page.mouse.move(x, y)
  → page.mouse.wheel(deltaX, deltaY)
  → done ✓
```
**No timeout. No selector. Never fails.**

---

### KEY step
```
perform_key(page, key_text)
  → page.keyboard.press(key)
  → done ✓
```
**No timeout. No selector. Never fails.**

---

### After every step (success or not)

```
step_failed?
  │
  ├─ YES → PLAY_STEP_ERROR sent
  │         cap_mgr.request(ERROR) → immediate screenshot → FRAME
  │         break — all remaining steps skipped
  │
  └─ NO  → _settle_page()
  │            is CLICK or KEY(Enter)?  AND  step.url != step.pageUrl?
  │              YES → wait_for_function("url changed", timeout=500ms)
  │                      url changed → wait_for_load_state("domcontentloaded", timeout=3s)
  │                      no change   → pass (500ms wasted, harmless)
  │              NO  → return immediately (TYPE/SCROLL/KEY skip entirely)
  │
  │         asyncio.sleep(waitAfterMs)   ← 100ms or 300ms from recording
  │
  │         cap_mgr.request(STEP_DONE)
  │              acquire lock
  │              FIXED_DELAY 300ms
  │              CDP screenshot → base64 → FRAME sent
  │              release lock
  │
  └─ pause=true? → PLAY_PAUSED sent → block on pause_event → wait for PLAY_RESUME
```

---

### DomWatcher (runs in parallel the entire time)

```
Background worker loop (started on DomWatcher.attach):

  every 300ms:
    if _dirty:
      _dirty = False
      acquire lock (waits if STEP_DONE capture is in progress)
      CDP screenshot → base64 → FRAME sent
      release lock

MutationObserver (JS in browser):
  any DOM change → __domChanged__() → _dirty = True   (instant, no await, no task)

page.on("load"):
  → _dirty = True

page.on("domcontentloaded"):
  → _dirty = True
```

**DomWatcher never blocks playback.** It runs entirely in the background. Its frames interleave with STEP_DONE frames via the shared lock.

---

### Full timing per step (SPA click, no navigation)

```
_execute_step() CLICK
  wait_for_selector: 0–3s        ← best case ~50ms if element exists
  element.click(): ~5ms
  ─────────────────────────────
  _settle_page(): 0ms             ← skipped (url == pageUrl)
  waitAfterMs: 300ms
  STEP_DONE fixed delay: 300ms
  CDP + encode + WS: ~250ms
  ─────────────────────────────
  Total per step: ~900ms best case, ~3.9s worst case (3s selector wait)

DomWatcher fires:
  after step lock releases → next 300ms worker tick → FRAME #2
```