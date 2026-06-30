# 🎬 Playwright Recorder Player

A web automation tool built with **FastAPI** and **Playwright**. Capture screenshots, analyze DOM, find elements by coordinates, and generate CSS selectors and XPath expressions.

---

## 📋 Overview

**What it does:**
- ✅ Launch headless Chromium browser
- ✅ Navigate to any website
- ✅ Capture full-page screenshots
- ✅ Extract page DOM/HTML
- ✅ Find elements by clicking coordinates (X, Y)
- ✅ Generate CSS selectors and XPath expressions
- ✅ Display element properties (tag, ID, class, attributes)

**Architecture:**
- **Backend:** FastAPI (async/sync) + Playwright (synchronous)
- **Frontend:** Interactive HTML/CSS/JavaScript UI
- **Browser:** Chromium (headless mode)
- **Viewport:** Fixed at 1280×720 pixels

---

## 📁 Project Structure

```
Playwright_Launch/
├── app/
│   ├── main.py                    # FastAPI routes & endpoints
│   ├── services/
│   │   └── launchWeb.py           # Playwright browser manager (sync)
│   ├── static/
│   │   └── index.html             # Web UI interface
│   └── screenshots/               # Saved screenshots
├── requirements.txt               # Python dependencies
├── .gitignore                     # Git ignore rules
├── start.bat / start.sh           # Launch scripts
└── debug.log                      # Error logs
```

---

## ⚙️ Installation & Setup

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Install Playwright Browsers
```bash
playwright install
```

### 3. Start the Server
```bash
python -m uvicorn app.main:app --reload
```

### 4. Open Web Interface
Navigate to: **http://localhost:8000**

---

## 🚀 Available Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `POST` | `/api/initialize` | Start browser session |
| `POST` | `/api/open-url` | Navigate to URL |
| `POST` | `/api/screenshot` | Capture page screenshot |
| `GET` | `/api/dom` | Fetch page HTML content |
| `POST` | `/api/element-at-coordinates` | Find element at X,Y position |
| `POST` | `/api/close` | Close browser & cleanup |
| `GET` | `/api/screenshots` | List all saved screenshots |
| `GET` | `/api/screenshot-base64` | Get latest screenshot (base64) |
| `GET` | `/api/health` | Health check |

---

## 🔄 Application Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                     WEB INTERFACE (index.html)                  │
│                  User clicks buttons & enters URL               │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
              ┌──────────────────────────────┐
              │   FASTAPI ROUTES (main.py)   │
              │  - Async endpoint functions  │
              │  - Validates input (Pydantic)│
              │  - Comprehensive logging     │
              └──────┬───────────────────────┘
                     │
                     ▼
    ┌─────────────────────────────────────────────────────┐
    │  FASTAPI THREAD POOL                                │
    │  (fastapi.concurrency.run_in_threadpool)            │
    │  - Manages blocking sync operations                 │
    │  - Non-blocking for FastAPI                         │
    │  - Worker thread executes sync code                 │
    └──────────────────┬──────────────────────────────────┘
                       │
                       ▼
    ┌──────────────────────────────────────────────────────┐
    │  PLAYWRIGHT SERVICE (launchWeb.py - Sync API)        │
    │  Pure synchronous functions (NO asyncio)             │
    │                                                      │
    │  ├─ initialize()        → Launch Chromium           │
    │  ├─ open_url(url)       → Navigate page             │
    │  ├─ take_screenshot()   → Capture screenshot        │
    │  ├─ get_dom()           → Extract HTML              │
    │  ├─ get_element_at_coordinates(x, y)               │
    │  └─ close()             → Cleanup                   │
    └──────────────────┬───────────────────────────────────┘
                       │
                       ▼
        ┌──────────────────────────────────────┐
        │   CHROMIUM BROWSER (Headless)        │
        │   - 1280×720 viewport                │
        │   - Executes JavaScript              │
        │   - Generates screenshots            │
        │   - Extracts DOM                     │
        └──────────────────────────────────────┘
```

**Why This Architecture?**
- ✅ Simple synchronous Playwright code (no async/await complexity)
- ✅ Thread pool keeps FastAPI responsive (non-blocking)
- ✅ No asyncio subprocess issues on Windows
- ✅ Clean separation of concerns
- ✅ Easy to debug and maintain

---

## 📚 Key Libraries & Components

### **Backend Framework**
- **FastAPI** (0.104.1) - Modern async web framework
- **Uvicorn** (0.24.0) - ASGI server for running FastAPI
- **Pydantic** (2.5.0) - Data validation & serialization

### **Browser Automation**
- **Playwright** (1.40.0) - Browser control (Synchronous API)
  - `sync_api` - Simple synchronous functions
  - Chromium engine - Fast, reliable automation
  - Headless mode - No visible browser window

### **File Handling**
- **Pillow** (10.1.0) - Image processing
- **PathLib** - Cross-platform file paths

### **Logging**
- **Python logging** - Debug logs to `debug.log`

---

## 💡 How It Works

### **Synchronous Playwright Approach**
```
Why Sync API?
  ✓ Simple, straightforward code (no async/await keywords)
  ✓ No asyncio complexity
  ✓ Better Windows compatibility (no subprocess issues)
  ✓ Works with thread pool (FastAPI stays responsive)
  
Pattern Used:
  FastAPI Route (async)
     ↓
  await run_in_threadpool() 
     ↓
  Sync Playwright service
     ↓
  Returns result to client
```


### **Workflow Example**
```
User clicks "Initialize"
         ↓
Browser: POST /api/initialize
         ↓
FastAPI endpoint receives request
         ↓
Uses threadpool to run: browser_manager.initialize()
         ↓
Playwright launches Chromium
         ↓
Returns viewport config
         ↓
Display success message
```

---

## 🔍 Finding Elements

### Method 1: Click on Screenshot Grid
1. Take a screenshot first
2. Move mouse over the grid image
3. Click where you want to inspect
4. Coordinates auto-fill (X, Y)
5. Click "🔍 Find Element"

### Method 2: Manual Coordinates
1. Enter X (0-1280)
2. Enter Y (0-720)  
3. Click "🔍 Find Element"

### Result: Element Information
```
Tag Name: <input>
ID: search-box
Class: search-input
Selector: #search-box
XPath: /html[1]/body[1]/input[1]
```

---

## 📁 File Organization

| File/Folder | Purpose |
|-------------|---------|
| `app/main.py` | FastAPI routes with logging |
| `app/services/launchWeb.py` | Playwright sync service |
| `app/static/index.html` | Interactive web UI |
| `app/screenshots/` | Saved screenshots |
| `debug.log` | Error & debug logs |
| `requirements.txt` | Python dependencies |

---

## 🛠️ Configuration

### Viewport Size
Default: **1280×720** pixels

Edit in `app/services/launchWeb.py`:
```python
self.viewport = {"width": 1280, "height": 720}
```

### Browser Headless Mode
Always enabled for automation.

---


## 📊 Technology Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| **Web Framework** | FastAPI | 0.104.1 |
| **Server** | Uvicorn | 0.24.0 |
| **Browser Automation** | Playwright (Sync) | 1.40.0 |
| **Validation** | Pydantic | 2.5.0 |
| **Image Processing** | Pillow | 10.1.0 |
| **Python Version** | Python | 3.10+ |

---

## ✨ Key Features

✅ Headless browser automation (Chromium)  
✅ Screenshot capture with auto-naming  
✅ DOM/HTML extraction  
✅ Element locator by X,Y coordinates  
✅ Auto-generate CSS selectors  
✅ Auto-generate XPath expressions  
✅ Real-time element properties  
✅ Interactive web interface  
✅ RESTful API design  
✅ Comprehensive error logging  
✅ Thread-safe operations  
✅ Synchronous Playwright (simple & reliable)  


---

## 📝 Notes

- **Browser Mode:** Headless (no visible window)
- **Page Load:** Waits for network idle
- **Coordinates:** (0,0) = top-left
- **Viewport:** Fixed 1280×720
- **Logs:** Check `debug.log` for errors
- **API:** All endpoints return JSON

---
