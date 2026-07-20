@echo off
title HealthSync-AgentRAG: Cooperative Multi-Agent Clinical Reconciliation & RAG-Knowledge Base
echo =======================================================================
echo           BOOTSTRAPPING HEALTHSYNC-AGENTRAG CDSS APPLICATION
echo =======================================================================
echo.

:: 1. Check Python installation
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in your system's PATH.
    echo Please download and install Python from https://www.python.org/
    echo Make sure to check the box "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

:: 2. Check for Virtual Environment
set VENV_PATH=
if exist ".venv\Scripts\activate.bat" (
    set VENV_PATH=.venv
) else if exist "venv\Scripts\activate.bat" (
    set VENV_PATH=venv
) else if exist "env\Scripts\activate.bat" (
    set VENV_PATH=env
)

if not "%VENV_PATH%"=="" (
    echo [OK] Found local virtual environment: %VENV_PATH%
    echo Activating environment...
    call "%VENV_PATH%\Scripts\activate.bat"
) else (
    echo [WARN] No local virtual environment found [.venv/venv/env].
    echo Running using global Python environment.
)
echo.

:: 3. Check for dependencies or install them
echo Checking for required packages (FastAPI, Uvicorn, SQLAlchemy, Pydantic)...
python -c "import fastapi, uvicorn, sqlalchemy, pydantic" >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Some required packages are missing. Installing dependencies...
    pip install fastapi uvicorn sqlalchemy crewai pydantic requests
) else (
    echo [OK] Core dependencies are already installed.
)
echo.

:: 4. Check if local Ollama service is running
echo Checking local Ollama service (port 11434)...
powershell -Command "try { $response = Invoke-WebRequest -Uri http://localhost:11434 -UseBasicParsing -TimeoutSec 2; exit 0 } catch { exit 1 }" >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARN] Ollama service is not running or not responding on http://localhost:11434.
    echo        HealthSync-AgentRAG will use its built-in, resilient clinical rule-based fallbacks.
    echo        To use full 3-Agent cooperative clinical reasoning, please launch Ollama
    echo        and pull the 'llama3' model [run: ollama pull llama3].
) else (
    echo [OK] Ollama service is online! Cooperative Clinical AI Crew is ready.
)
echo.

:: 5. Set PYTHONPATH and run server
echo Starting FastAPI application server...
echo Portal URL: http://127.0.0.1:8000
echo.
echo Press Ctrl+C in this terminal to stop the server.
echo.

:: Automatically open browser after 1.5 seconds in background
start "" "http://127.0.0.1:8000"

:: Run FastAPI server with uvicorn
set PYTHONPATH=%cd%\backend
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload

pause
