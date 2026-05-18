@echo off
REM RAG2 Streamlit GUI Launcher for Windows
REM This script activates the virtual environment and runs the Streamlit GUI

echo ========================================================
echo        RAG2 - Streamlit GUI Launcher
echo ========================================================
echo.

REM Check if virtual environment exists
if not exist "venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found!
    echo Please create it first:
    echo   python -m venv venv
    echo   venv\Scripts\activate
    echo   pip install -r requirements.txt
    pause
    exit /b 1
)

REM Activate virtual environment
echo [1/2] Activating virtual environment...
call venv\Scripts\activate.bat

REM Check if .env file exists
if not exist ".env" (
    echo.
    echo [WARNING] .env file not found!
    echo Creating from .env.example...
    copy .env.example .env > nul
    echo.
    echo [IMPORTANT] Please edit .env file and set your configuration:
    echo   - For Cloud Mode: Set MODE=CLOUD and add OPENAI_API_KEY
    echo   - For Local Mode: Set MODE=LOCAL and ensure Ollama is running
    echo.
    echo Press any key to continue (after editing .env)...
    pause
)

REM Run Streamlit GUI
echo.
echo [2/2] Starting Streamlit GUI...
echo.
echo The application will open in your browser at:
echo   http://localhost:8501
echo.
echo Press Ctrl+C in this terminal to stop the server.
echo.

streamlit run app.py

REM Deactivate environment on exit
call deactivate

pause
