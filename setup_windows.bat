@echo off
echo ========================================
echo Smartlead Monitor - Windows Setup
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8+ from https://www.python.org
    pause
    exit /b 1
)

echo [1/6] Creating virtual environment...
python -m venv venv
if %errorlevel% neq 0 (
    echo ERROR: Failed to create virtual environment
    pause
    exit /b 1
)

echo [2/6] Activating virtual environment...
call venv\Scripts\activate.bat

echo [3/6] Upgrading pip...
python -m pip install --upgrade pip

echo [4/6] Installing dependencies...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo ERROR: Failed to install dependencies
    pause
    exit /b 1
)

echo [5/6] Creating necessary directories...
if not exist "audit_logs" mkdir audit_logs
if not exist "state" mkdir state
if not exist "logs" mkdir logs

echo [6/6] Creating environment file template...
if not exist ".env" (
    (
        echo # Smartlead Monitor Configuration
        echo.
        echo # API Configuration
        echo SMARTLEAD_API_KEY=2fbf4f7d-44af-4ff1-8e25-5655f5483fd0_94zyakr
        echo.
        echo # Slack Configuration
        echo SLACK_BOT_TOKEN=xoxb-your-slack-bot-token
        echo SLACK_CHANNEL_ID=#monitoring
        echo.
        echo # Database Configuration
        echo DATABASE_URL=postgresql://postgres:SB0dailyreporting@db.auzoezucrrhrtmaucbbg.supabase.co:5432/postgres
        echo.
        echo # File paths
        echo CSV_DIR=./audit_logs
        echo STATE_FILE=./state/last_check.json
    ) > .env
    echo Created .env file template. Please update with your actual values.
) else (
    echo .env file already exists. Skipping...
)

echo.
echo ========================================
echo Setup completed successfully!
echo ========================================
echo.
echo Next steps:
echo 1. Edit the .env file with your Slack Bot Token
echo 2. Run 'run_monitor.bat' to test the monitor
echo 3. For first run, use 'run_monitor.bat --first-run'
echo.
echo To schedule hourly runs:
echo - Use Windows Task Scheduler
echo - Or run 'setup_scheduler.bat' for automatic setup
echo.
pause
