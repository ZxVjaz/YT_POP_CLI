@echo off
color 0A
chcp 65001 >nul

set "R=[0m"
set "B=[1m"
set "D=[2m"
set "RD=[31m"
set "G=[32m"
set "Y=[33m"
set "BL=[34m"
set "M=[35m"
set "C=[36m"
set "W=[37m"
set "BR=[91m"
set "BG=[92m"
set "BY=[93m"
set "BB=[94m"
set "BM=[95m"
set "BC=[96m"
set "BW=[97m"

set "OK=%BG%[OK]%R%"
set "INFO=%BC%[INFO]%R%"
set "WARN=%BY%[WARNING]%R%"
set "ERR=%BR%%B%[ERROR]%R%"
set "TITLE=%BM%%B%"
set "BORDER=%C%"

title YT POP

cd /d "%~dp0"

echo %BORDER%==========================================%R%
echo %TITLE%   YouTube POP Command Line Downloader   %R%
echo %TITLE%     Queue-based Parallel Downloader     %R%
echo %BORDER%==========================================%R%
echo.

set "VENV_DIR=%CD%\.venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
set "VENV_PIP=%VENV_DIR%\Scripts\pip.exe"

if not exist "%VENV_PYTHON%" (
    echo %INFO% Virtual environment not found. Checking system Python...
    
    python --version > nul 2>&1
    if errorlevel 1 (
        echo %ERR% Python is not installed or not in PATH
        echo.
        echo Please install Python 3.8 or higher
        pause
        exit /b 1
    )
    
    echo %INFO% Creating virtual environment...
    python -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo %ERR% Failed to create virtual environment
        pause
        exit /b 1
    )
    echo %OK% Virtual environment created
    echo.
)

echo %OK% Using virtual environment: %VENV_DIR%

echo %INFO% Updating pip...
"%VENV_PYTHON%" -m pip install --upgrade pip -q

echo %INFO% Installing dependencies...
"%VENV_PIP%" install -q -r requirements.txt
if errorlevel 1 (
    echo %ERR% Failed to install dependencies
    pause
    exit /b 1
)

echo %OK% Dependencies ready
echo.

if not exist "bin\" (
    echo %WARN% bin directory not found!
    echo Please ensure you have yt-dlp.exe and ffmpeg.exe in bin folder
    pause
)

if not exist "downloads\" mkdir downloads

echo.
echo %BORDER%==========================================%R%
echo %TITLE%           Starting Application...        %R%
echo %BORDER%==========================================%R%
echo.

"%VENV_PYTHON%" download.py %*

if errorlevel 1 (
    echo.
    echo %ERR% Application exited with error
    pause
)
 %*

if errorlevel 1 (
    echo.
    echo %ERR% Application exited with error
    pause
)