Frontend Instructions

src/app/
├── components/ # Reusable UI components
│ ├── toolbar/
│ ├── status/
│ └── ...
├── pages/ # Full-page components (containers)
│ ├── browser/
│ ├── home/
│ └── ...
├── services/ # Observable API calls & business logic
├── types/ # All TypeScript models & interfaces
└── app.ts # Router outlet only (no logic)


Generate angular code only in 21 version.
Use the latest Angular 21 features and best practices code
All services MUST use `.api` suffix
All TypeScript interfaces and types go in `types/` folder
Global theme CSS goes in `app.css` (NOT in separate files) use this
All components are standalone** (`standalone: true`)
- Page components go in `pages/` folder (containers with layout)
UI components go in `components/` folder (reusable pieces)
- File structure per component and pages: `component-name.ts`, `.html`, `.css`, `.spec.ts`
- always refer the previous structure for reference
If u r using or creating any svg place it inside components/svg-icon folder and use it as a component


Backend Instructions

├── main.py # FastAPI app factory & server setup
├── api/ # REST endpoints (routes)
├── websocket/ # WebSocket handlers & event routing
├── services/ # Business logic (session mgmt, browser ops)
├── models/ # Data models & schemas (Pydantic)
└── utils/ # Helper functions

- **Framework**: FastAPI (with native async/await)
- **Server**: Uvicorn ASGI
- **Browser Automation**: Playwright (async API)
- **Data Validation**: Pydantic v2
- **Real-time**: WebSocket (native FastAPI support)

Always refer the backend code structure for reference. 