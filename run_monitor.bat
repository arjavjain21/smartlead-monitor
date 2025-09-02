@echo off
echo Starting Smartlead Monitor...
echo.

REM Load environment variables from .env file
if exist ".env" (
    for /f "delims=" %%x in (.env) do (
        set "line=%%x"
        setlocal enabledelayedexpansion
        set "line=!line: =!"
        if not "!line:~0,1!"=="#" (
            endlocal
            set "%%x"
        ) else (
            endlocal
        )
    )
)

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Run the monitor with any passed arguments
python smartlead_monitor.py %*

REM Check exit code
if %errorlevel% neq 0 (
    echo.
    echo Monitor execution failed with error code %errorlevel%
    pause
) else (
    echo.
    echo Monitor execution completed successfully
)
