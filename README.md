# Smartlead Account Disconnection Monitor - Complete Setup Guide

## Overview
This monitoring system tracks Smartlead email accounts for disconnections and sends hourly notifications to Slack when new disconnections are detected. It maintains both a database record and CSV audit trail of all disconnection events.

## Features
- ✅ Hourly monitoring of all Smartlead accounts
- ✅ Detects SMTP, IMAP, or both types of disconnections
- ✅ Sends detailed Slack notifications for new disconnections only
- ✅ Tracks reconnection/disconnection cycles
- ✅ Maintains audit trail in CSV format
- ✅ Stores history in Supabase database
- ✅ Automatic retry with exponential backoff
- ✅ Rate limiting compliance (10 requests/2 seconds)
- ✅ 30-day data retention with automatic cleanup

## Prerequisites

### Required Accounts
1. **Smartlead Account** with API access
2. **Slack Workspace** with bot creation permissions
3. **Supabase Database** (already configured as per your requirements)
4. **GitHub Account** for GitHub Actions deployment

### Software Requirements
- **For Local Development**: Python 3.8+ installed
- **For GitHub Actions**: GitHub repository with Actions enabled

## Part 1: Slack Bot Setup

### Step 1: Create Slack App
1. Go to [https://api.slack.com/apps](https://api.slack.com/apps)
2. Click "Create New App" → "From scratch"
3. Name your app: "Smartlead Monitor"
4. Select your workspace
5. Click "Create App"

### Step 2: Configure Bot Permissions
1. In the app settings, go to "OAuth & Permissions"
2. Scroll to "Scopes" → "Bot Token Scopes"
3. Add these scopes:
   - `chat:write` - Send messages
   - `chat:write.public` - Send to public channels
   - `channels:read` - View channel info
   - `groups:read` - View private channel info

### Step 3: Install Bot to Workspace
1. Go to "OAuth & Permissions"
2. Click "Install to Workspace"
3. Authorize the permissions
4. Copy the "Bot User OAuth Token" (starts with `xoxb-`)
5. Save this token securely - you'll need it for `SLACK_BOT_TOKEN`

### Step 4: Get Channel ID
1. Open Slack in your browser
2. Navigate to the channel for notifications
3. The URL will be like: `https://workspace.slack.com/archives/C1234567890`
4. Copy the channel ID (e.g., `C1234567890`)
5. Or use the channel name with # (e.g., `#monitoring`)

### Step 5: Invite Bot to Channel
1. In Slack, go to your notification channel
2. Type: `/invite @Smartlead Monitor`
3. The bot should now have access to post messages

## Part 2: GitHub Actions Setup

### Step 1: Fork or Create Repository
1. Create a new GitHub repository named `smartlead-monitor`
2. Clone it locally:
   ```bash
   git clone https://github.com/YOUR_USERNAME/smartlead-monitor.git
   cd smartlead-monitor
   ```

### Step 2: Add Files to Repository
1. Add all the provided files:
   ```
   smartlead-monitor/
   ├── .github/
   │   └── workflows/
   │       └── smartlead-monitor.yml
   ├── smartlead_monitor.py
   ├── requirements.txt
   ├── setup_windows.bat
   ├── run_monitor.bat
   ├── setup_scheduler.ps1
   └── README.md
   ```

2. Commit and push:
   ```bash
   git add .
   git commit -m "Initial setup for Smartlead monitor"
   git push origin main
   ```

### Step 3: Configure GitHub Secrets
1. Go to your repository on GitHub
2. Navigate to Settings → Secrets and variables → Actions
3. Add these repository secrets:

   | Secret Name | Value |
   |------------|-------|
   | `SMARTLEAD_API_KEY` | `2fbf4` |
   | `SLACK_BOT_TOKEN` | Your bot token from Slack (xoxb-...) |
   | `SLACK_CHANNEL_ID` | Your channel ID (e.g., `C1234567890` or `#monitoring`) |
   | `DATABASE_URL` | `postgr..connection_string` |

### Step 4: Enable GitHub Actions
1. Go to Actions tab in your repository
2. If prompted, enable GitHub Actions
3. The workflow will run automatically every hour

### Step 5: Manual First Run
1. Go to Actions → Smartlead Account Monitor
2. Click "Run workflow"
3. Select "yes" for first_run parameter
4. Click "Run workflow" button
5. Monitor the execution in the Actions tab

## Part 3: Local Windows Setup

### Step 1: Install Python
1. Download Python 3.8+ from [python.org](https://www.python.org/downloads/)
2. During installation, CHECK "Add Python to PATH"
3. Verify installation:
   ```cmd
   python --version
   ```

### Step 2: Download Monitor Files
1. Create a folder: `C:\SmartleadMonitor`
2. Download all files from the repository
3. Place them in the folder

### Step 3: Run Setup Script
1. Open Command Prompt as Administrator
2. Navigate to the folder:
   ```cmd
   cd C:\SmartleadMonitor
   ```
3. Run setup:
   ```cmd
   setup_windows.bat
   ```

### Step 4: Configure Environment
1. Edit the `.env` file created by setup
2. Update these values:
   ```env
   SLACK_BOT_TOKEN=xoxb-your-actual-token
   SLACK_CHANNEL_ID=#your-channel-or-id
   ```

### Step 5: Test the Monitor
1. First run (marks all current disconnections as new):
   ```cmd
   run_monitor.bat --first-run
   ```
2. Regular run:
   ```cmd
   run_monitor.bat
   ```

### Step 6: Schedule Hourly Runs
1. Right-click `setup_scheduler.ps1`
2. Select "Run with PowerShell" (as Administrator)
3. Follow the prompts to set up hourly execution

## Part 4: Database Schema

The system automatically creates the required table in your Supabase database:

```sql
CREATE TABLE disconnected_accounts (
    id SERIAL PRIMARY KEY,
    account_id INTEGER NOT NULL,
    from_name VARCHAR(255),
    from_email VARCHAR(255) NOT NULL,
    account_type VARCHAR(50),
    disconnection_type VARCHAR(20),
    tags TEXT,
    detected_at TIMESTAMP NOT NULL,
    resolved_at TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    check_run_id VARCHAR(50),
    UNIQUE(account_id, detected_at)
);
```

## Part 5: Monitoring and Maintenance

### Check Logs

#### GitHub Actions
1. Go to Actions tab in repository
2. Click on any workflow run
3. Download artifacts for logs

#### Local Windows
- Application logs: `smartlead_monitor.log`
- CSV audit trail: `audit_logs/` folder
- State file: `state/last_check.json`

### Slack Notifications Format
```
🔴 5 New Account Disconnection(s) Detected
Check Time: 2024-01-20 14:05:00 UTC
Run ID: 20240120140500_abc123

• Both SMTP & IMAP: 2 accounts
• SMTP Only: 2 accounts
• IMAP Only: 1 account

[Detailed table of affected accounts]

Recommended Actions:
1. Check affected email accounts in Smartlead dashboard
2. Verify email provider connectivity
3. Re-authenticate affected accounts if needed
```

### Error Handling
- API failures trigger exponential backoff retry (up to 3 attempts)
- After 3 failures, error notification sent to Slack
- Check skipped for that hour, resumes next hour
- All errors logged to `smartlead_monitor.log`

### Data Retention
- Database records: 30 days for resolved disconnections
- CSV files: Kept indefinitely (manual cleanup if needed)
- GitHub artifacts: 30 days for audit logs, 7 days for state

## Troubleshooting

### Common Issues

#### 1. "SLACK_BOT_TOKEN environment variable not set"
- Ensure the token is correctly set in:
  - GitHub Secrets (for Actions)
  - `.env` file (for local)

#### 2. Slack bot can't post to channel
- Verify bot is invited to channel
- Check bot has `chat:write` permission
- Ensure channel ID is correct

#### 3. Database connection errors
- Verify Supabase connection string
- Check network connectivity
- Ensure database is accessible

#### 4. No notifications despite disconnections
- Check if accounts were already marked as disconnected
- Verify Slack configuration
- Review logs for errors

#### 5. Rate limit errors
- The script handles rate limiting automatically
- If persistent, check API key validity

### Testing Individual Components

#### Test Smartlead API
```python
import requests
response = requests.get(
    'https://server.smartlead.ai/api/email-account/get-total-email-accounts',
    params={'api_key': 'YOUR_KEY', 'offset': 0, 'limit': 10}
)
print(response.json())
```

#### Test Slack Connection
```python
from slack_sdk import WebClient
client = WebClient(token="YOUR_BOT_TOKEN")
response = client.chat_postMessage(
    channel="#test",
    text="Test message"
)
```

#### Test Database Connection
```python
import psycopg2
conn = psycopg2.connect("YOUR_DATABASE_URL")
cursor = conn.cursor()
cursor.execute("SELECT version();")
print(cursor.fetchone())
```

## Security Best Practices

1. **Never commit secrets to Git**
   - Use `.gitignore` for `.env` files
   - Use GitHub Secrets for Actions

2. **Rotate API keys regularly**
   - Update Smartlead API key periodically
   - Regenerate Slack bot token if compromised

3. **Limit database permissions**
   - Create specific user for this application
   - Grant only necessary permissions

4. **Monitor access logs**
   - Review GitHub Actions logs
   - Check Slack audit logs
   - Monitor database access

## Support and Updates

### Getting Help
1. Check application logs first
2. Review this documentation
3. Test individual components
4. Check Smartlead API documentation

### Updating the Monitor
1. Pull latest changes from repository
2. Update dependencies: `pip install -r requirements.txt --upgrade`
3. Restart scheduled tasks

### Modifying Behavior
- Adjust check frequency in GitHub workflow cron expression
- Change retention period in `Config.RETENTION_DAYS`
- Modify notification format in `SlackNotifier.send_disconnection_alert()`

## License
This monitoring system is provided as-is for internal use.

## Contact
For issues or questions about this setup, please refer to the documentation or contact your system administrator.
