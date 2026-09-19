@echo off
cd /d "%~dp0"

echo Starting Pulse - Sentiment Analyzer...
echo.

if not exist "venv\Scripts\activate.bat" (
    echo Virtual environment not found. Run setup first:
    echo   python -m venv venv
    echo   venv\Scripts\activate
    echo   pip install -r requirements.txt
    pause
    exit /b
)

call venv\Scripts\activate.bat

echo Opening browser in 5 seconds once the server is ready...
start "" cmd /c "timeout /t 5 >nul && start http://localhost:5000"

python app.py

pause
