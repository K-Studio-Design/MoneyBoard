@echo off
title MoneyBoard
REM ============================================================
REM  Avvio MoneyBoard
REM  Al primo avvio crea l'ambiente Python (fuori da OneDrive)
REM  e installa i pacchetti; poi apre l'app nel browser.
REM ============================================================
cd /d "%~dp0"
set "VENV=%LOCALAPPDATA%\AppSpese\venv"

if not exist "%VENV%\Scripts\python.exe" (
    echo Prima installazione: creo l'ambiente Python in %VENV% ...
    py -3 -m venv "%VENV%" 2>nul
    if not exist "%VENV%\Scripts\python.exe" python -m venv "%VENV%"
    if not exist "%VENV%\Scripts\python.exe" (
        echo.
        echo Python non trovato. Installalo da https://www.python.org/downloads/
        echo e durante l'installazione spunta "Add python.exe to PATH".
        pause
        exit /b 1
    )
    "%VENV%\Scripts\python.exe" -m pip install --upgrade pip
    "%VENV%\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo Installazione dei pacchetti non riuscita.
        rmdir /s /q "%VENV%"
        pause
        exit /b 1
    )
)

if /i "%1"=="aggiorna" "%VENV%\Scripts\python.exe" -m pip install --upgrade -r requirements.txt

REM Se l'elenco dei pacchetti e' cambiato (nuove funzioni), installa quelli mancanti
fc /b requirements.txt "%VENV%\requirements.installati.txt" >nul 2>&1
if errorlevel 1 (
    echo Installo i pacchetti nuovi richiesti dall'app...
    "%VENV%\Scripts\python.exe" -m pip install -r requirements.txt
    if not errorlevel 1 copy /y requirements.txt "%VENV%\requirements.installati.txt" >nul
)

"%VENV%\Scripts\python.exe" -m streamlit run app.py
pause
