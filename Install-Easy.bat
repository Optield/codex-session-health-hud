@echo off
setlocal
cd /d "%~dp0"
title Codex Session Health HUD - Install

echo.
echo ============================================================
echo   Codex Session Health HUD - Local Installer
echo ============================================================
echo.

if not exist "%~dp0Install.ps1" (
    echo ERROR: Install.ps1 was not found next to this file.
    echo Extract the whole ZIP first, then run Install-Easy.bat again.
    echo.
    pause
    exit /b 1
)

if not exist "%~dp0CodexSessionHealthHUD.exe" (
    echo ERROR: CodexSessionHealthHUD.exe was not found.
    echo Use the prebuilt Windows package, not the source-code ZIP.
    echo.
    pause
    exit /b 1
)

echo Installing from local files only...
echo This installer does not download anything from the Internet.
echo.

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install.ps1"
set "EXITCODE=%ERRORLEVEL%"

echo.
if not "%EXITCODE%"=="0" (
    echo ============================================================
    echo   Installation failed. Error code: %EXITCODE%
    echo ============================================================
    echo.
    echo Take a screenshot of this window and send it to ChatGPT.
    echo.
    pause
    exit /b %EXITCODE%
)

echo ============================================================
echo   Installation completed successfully.
echo ============================================================
echo.
echo Start Codex from the Windows Start menu using:
echo.
echo   Codex with Session Health HUD
echo.
pause
exit /b 0
