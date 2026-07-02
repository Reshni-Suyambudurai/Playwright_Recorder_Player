@echo off
REM Quick Start Script for Playwright Recorder Player

echo.
echo ====================================================================
echo.   Playwright Recorder Player - FastAPI Backend
echo.   Quick Start Script
echo.
echo ====================================================================
echo.



echo.
echo [OK] Setup complete!
echo.
echo [START] Starting FastAPI server...
echo.
echo Access the application at: http://localhost:8000
echo Server logs will appear below:
echo ====================================================================
echo.

python -m uvicorn app.main:app --reload

pause
