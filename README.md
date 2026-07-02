# Playwright Recorder & Player

A browser automation tool with a real-time recording and playback interface — built with **FastAPI** (backend) and **Angular 21** (frontend).

---

## Prerequisites

- **Python 3.10+**
- **Node.js 18+** and **npm**
- **Angular CLI** — `npm install -g @angular/cli`

---

## Installation

### 1. Backend

```bash
cd backend
pip install -r ../requirements.txt
playwright install chromium
```

### 2. Frontend

```bash
cd automation_frontend
npm install
```

---

## Running the App

### Start the Backend

```bash
cd backend
python run.py
```

Backend runs at: `http://localhost:8000`

### Start the Frontend

Open a new terminal:

```bash
cd automation_frontend
ng serve
```

Frontend runs at: `http://localhost:4200`

---

## Usage

1. Open `http://localhost:4200` in your browser
2. Click **Connect** to start a browser session
3. Enter a URL and click **Navigate** to load a page
4. Use the **Flows** tab to view recorded flows
5. Use the **Runs** tab to see execution history
6. Click **Disconnect** when done

---

## Project Structure

```
.
├── backend/
│   ├── run.py          # Entry point (sets Windows event loop policy)
│   ├── api/            # REST endpoints
│   ├── websocket/      # Real-time WebSocket handlers
│   ├── services/       # Business logic (browser, session, recorder)
│   ├── models/         # Pydantic data models
│   └── utils/          # Helper functions
│
└── automation_frontend/
    └── src/app/
        ├── components/ # Reusable UI (navbar, sidebar, toolbar, status)
        ├── pages/      # Route pages (browser, flows, runs, settings)
        ├── services/   # API services (websocket, navigation, theme)
        └── types/      # TypeScript interfaces
```
