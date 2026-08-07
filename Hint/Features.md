## Backend File Structure

```text
backend/
├── run.py                             # Backend runner
├── app/
│   ├── __init__.py                    # Package marker
│   ├── main.py                        # FastAPI app setup + router/ws registration
│   ├── api/
│   │   ├── __init__.py                # Package marker
│   │   ├── recording.py               # Recording REST APIs
│   │   └── play.py                    # Playback session REST APIs
│   ├── websocket/
│   │   ├── __init__.py                # Package marker
│   │   ├── websocket_handler.py       # Recorder WebSocket event router
│   │   ├── playback_handler.py        # Playback WebSocket event router
│   │   ├── websocket_events.py        # Recorder event constants/models
│   │   └── connection_manager.py      # WS connection and client mapping
│   ├── services/
│   │   ├── __init__.py                # Package marker
│   │   ├── session_manager.py         # Recording session lifecycle store
│   │   ├── browser_service.py         # Playwright browser actions
│   │   ├── screenshot_service.py      # Screenshot -> FRAME sender
│   │   ├── capture_manager.py         # Screenshot orchestration/settle logic
│   │   ├── dom_watcher.py             # DOM/load event detector
│   │   ├── playback_service.py        # Step-by-step playback executor
│   │   ├── recording_storage.py       # JSON file backup storage
│   │   └── database.py                # SQLite persistence service
│   ├── models/
│   │   ├── __init__.py                # Package marker
│   │   ├── session.py                 # RecordingSession runtime model
│   │   ├── recording.py               # Recording schema models
│   │   ├── playback.py                # PlaySession and playback status
│   │   └── playback_contracts.py      # Playback request/event contracts
│   └── utils/
│       ├── tab_manager.py             # Multi-tab registration/switch helpers
│       └── selector_builder.py        # Selector/target metadata builder
├── storage/
│   └── recordings/                    # Recording JSON backup files
└── test/
	 ├── conftest.py                    # Test fixtures/config
	 ├── test_*.py                      # Unit tests
	 └── IntegrationTesting/
		  └── test_*.py                  # Integration tests
```

## Frontend File Structure

```text
automation_frontend/
└── src/
	├── main.ts                         # Angular bootstrap
	├── styles.css                      # Global styles/theme tokens
	└── app/
		├── app.ts                       # Root shell component
		├── app.html                     # Root layout markup
		├── app.css                      # Root layout styles
		├── app.routes.ts                # Route definitions
		├── app.config.ts                # App providers config
		├── app.spec.ts                  # Root tests
		├── types/
		│   └── websocket.ts             # Shared TS contracts
		├── directives/
		│   └── tooltip/
		│       └── tooltip.directive.ts # Reusable tooltip directive
		├── services/
		│   ├── websocket.api.ts         # Recorder WebSocket client
		│   ├── navigation.api.ts        # URL navigation state/service
		│   ├── recordings.api.ts        # Recording REST client
		│   ├── playback.api.ts          # Playback REST + WS client
		│   ├── playback-state.api.ts    # Playback signal state store
		│   ├── token-store.api.ts       # Browser storage helper
		│   └── theme.api.ts             # Theme/sidebar state
		├── pages/
		│   ├── browser/                 # Record page container
		│   ├── flows/                   # Flows list/detail container
		│   ├── runs/                    # Run/edit/playback container
		│   └── settings/                # Settings page
		└── components/
			├── navbar/                   # Top bar component
			├── sidebar/                  # Left nav component
			├── toolbar/                  # Browser action bar
			├── status/                   # Connection/recording status
			├── browser-view/             # Live frame interaction view
			├── input-overlay/            # Input capture overlay
			├── recording-modal/          # Start recording modal
			├── tab-bar/                  # Browser tabs strip
			├── step-list/                # Runs step list/editor
			├── run-result-popup/         # Result popup
			├── spinner/                  # Reusable loader
			└── svg-icon/                 # Shared icon renderer
```
